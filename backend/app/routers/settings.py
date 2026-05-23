"""设置路由 - 完整可写配置中心。

GET  /api/settings/runtime         → 当前配置 (敏感字段已 mask)
PUT  /api/settings/runtime         → 写入配置 (空字符串 = 删除该 key)
POST /api/settings/test/llm        → 用当前 LLM 配置 ping 一次
POST /api/settings/test/monitor/{platform}   → 测试 AI 监测平台凭证

GET  /api/settings/llm             → LLM 配置概览
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import get_settings, reload_settings
from ..schemas import err, ok
from ..services.runtime_config import (
    ALLOWED_KEYS,
    SECRET_KEYS,
    clean_cookie_value,
    clean_token_value,
    delete_runtime_keys,
    load_runtime_config,
    mask_secret,
    save_runtime_config,
)

logger = logging.getLogger("geo.routers.settings")
router = APIRouter()

# 字段元数据 — 前端用此渲染表单
FIELD_SCHEMA: list[dict[str, Any]] = [
    # === 通用 ===
    {
        "key": "GEO_LOG_LEVEL",
        "label": "日志级别",
        "type": "select",
        "options": ["DEBUG", "INFO", "WARNING", "ERROR"],
        "category": "general",
    },
    # === AI 搜索 (citation 分析三家 + Kimi 国产备用,全部走官方 API key) ===
    {
        "key": "OPENAI_OFFICIAL_API_KEY",
        "label": "OpenAI Official API Key (ChatGPT)",
        "type": "password",
        "category": "monitor",
        "platform": "chatgpt",
        "help": (
            "用 Responses API + web_search_preview 工具跑 ChatGPT 监测。\n"
            "也能用 OPENAI_API_KEY 兜底(两个都填时优先 OPENAI_OFFICIAL_API_KEY)。\n"
            "申请: https://platform.openai.com/api-keys"
        ),
    },
    {
        "key": "OPENAI_API_KEY",
        "label": "OpenAI API Key (兜底)",
        "type": "password",
        "category": "monitor",
        "platform": "chatgpt",
        "help": "OPENAI_OFFICIAL_API_KEY 没填时用这个。一般两个填同一个 key 即可。",
    },
    {
        "key": "OPENAI_MONITOR_MODEL",
        "label": "ChatGPT 监测模型",
        "type": "text",
        "placeholder": "gpt-4o-mini",
        "category": "monitor",
        "platform": "chatgpt",
        "help": "默认 gpt-4o-mini,够用且便宜。要更高质量可改 gpt-4o / gpt-5。",
    },
    {
        "key": "PERPLEXITY_API_KEY",
        "label": "Perplexity Sonar API Key",
        "type": "password",
        "category": "monitor",
        "platform": "perplexity",
        "help": (
            "Sonar API key,跑 Perplexity 监测必需。citations 在响应顶层 citations[] 字段。\n"
            "申请: https://www.perplexity.ai/settings/api"
        ),
    },
    {
        "key": "PERPLEXITY_MODEL",
        "label": "Perplexity 模型",
        "type": "text",
        "category": "monitor",
        "platform": "perplexity",
        "placeholder": "sonar / sonar-pro / perplexity/sonar-pro-search (OpenRouter)",
        "help": (
            "直连 Perplexity 时填 sonar / sonar-pro / sonar-reasoning。\n"
            "走 OpenRouter 代理时填 perplexity/sonar-pro-search 这种 slug。"
        ),
    },
    {
        "key": "PERPLEXITY_API_BASE",
        "label": "Perplexity API Base",
        "type": "text",
        "category": "monitor",
        "platform": "perplexity",
        "placeholder": "https://api.perplexity.ai",
        "help": (
            "直连官方填 https://api.perplexity.ai;走 OpenRouter 填 https://openrouter.ai/api/v1。\n"
            "留空 = 用默认官方端点。"
        ),
    },
    {
        "key": "GOOGLE_AI_API_KEY",
        "label": "Google AI (Gemini) API Key",
        "type": "password",
        "category": "monitor",
        "platform": "google_ai",
        "help": (
            "Google AI Studio 的 key,跑 Gemini 监测(google_search 工具)必需。\n"
            "grounding metadata 的 URL 是 vertexaisearch.cloud.google.com 重定向,后台 worker 自动解析。\n"
            "申请: https://aistudio.google.com/apikey"
        ),
    },
    {
        "key": "KIMI_API_KEY",
        "label": "Moonshot / Kimi API Key",
        "type": "password",
        "category": "monitor",
        "platform": "kimi",
        "help": (
            "Moonshot 官方付费 API。中文/国内场景的备用监测渠道。\n"
            "申请: https://platform.moonshot.cn/console/api-keys"
        ),
    },
    {
        "key": "ARK_API_KEY",
        "label": "火山方舟 Ark API Key (Doubao web_search)",
        "type": "password",
        "category": "monitor",
        "platform": "doubao",
        "help": (
            "豆包 web 搜索走火山方舟 Responses API + 内置 web_search 工具。\n"
            "在火山引擎控制台 → 方舟 → API Key 管理创建。\n"
            "申请: https://www.volcengine.com/product/ark"
        ),
    },
    {
        "key": "DOUBAO_MODEL",
        "label": "Doubao 模型 endpoint id",
        "type": "text",
        "category": "monitor",
        "platform": "doubao",
        "placeholder": "doubao-seed-1-6-250615",
        "help": (
            "模型 endpoint id。常见:\n"
            "- doubao-seed-1-6-250615 (推荐,通用)\n"
            "- doubao-seed-1-6-thinking-* (含思考链)\n"
            "- doubao-seed-1-6-flash-* (更快更便宜)"
        ),
    },
    {
        "key": "ARK_API_BASE",
        "label": "Ark API Base (可选)",
        "type": "text",
        "category": "monitor",
        "platform": "doubao",
        "placeholder": "https://ark.cn-beijing.volces.com/api/v3",
        "help": "通常留空。海外/国际版主体可改 base url。",
    },
    {
        "key": "DEEPSEEK_REFRESH_TOKEN",
        "label": "DeepSeek Refresh Token (网页逆向)",
        "type": "password",
        "category": "monitor",
        "platform": "deepseek",
        "help": (
            "⚠️ DeepSeek 官方 API 目前没有 web search 工具,DeepSeek monitor 只能走\n"
            "chat.deepseek.com 网页 refresh_token + WASM POW 逆向。\n"
            "获取步骤:\n"
            "1) 浏览器打开 https://chat.deepseek.com 并登录\n"
            "2) F12 → Application → Local Storage → chat.deepseek.com\n"
            "3) 找 key=userToken,复制 value 字段里的 JSON ({\"value\":\"RWXtg...\"})\n"
            "4) 粘到输入框,点「从粘贴提取 token」自动解析\n"
            "或:网页发一条消息 → Network 抓任意请求 → 复制 curl → 粘过来自动抽 Bearer。"
        ),
    },
]


# ============================================================
# 新版: 完整可写配置
# ============================================================


@router.get("/settings/schema")
def get_schema() -> dict:
    """返回字段元数据, 前端用于动态渲染表单。"""
    return ok(
        {
            "fields": FIELD_SCHEMA,
            "categories": [
                {"key": "monitor", "label": "AI 搜索 / 监测平台"},
                {"key": "general", "label": "其他"},
            ],
        }
    )


@router.get("/settings/runtime")
def get_runtime_config() -> dict:
    """读取当前生效配置, 敏感字段已掩码 (sk-1***xxxx)。

    返回的字段同时包含来自 .env 的值和来自 runtime_config.json 的覆盖。
    """
    settings = get_settings()
    overlay = load_runtime_config()
    out: dict[str, Any] = {}
    for key in ALLOWED_KEYS:
        value = getattr(settings, key, None)
        if key in SECRET_KEYS:
            out[key] = {
                "configured": bool(value),
                "masked": mask_secret(value),
                "from_runtime": key in overlay,
            }
        else:
            out[key] = {
                "value": value,
                "from_runtime": key in overlay,
            }
    return ok(out)


class RuntimeConfigBody(BaseModel):
    updates: dict[str, Any]


@router.put("/settings/runtime")
def put_runtime_config(body: RuntimeConfigBody) -> dict:
    """写入运行时配置。

    规则:
    - 仅 ALLOWED_KEYS 内的字段会被保存
    - 敏感字段空字符串 = 不修改 (而不是清空)
    - 非敏感字段空字符串 = 清空 (恢复 .env / 默认)
    - 写入后立即调用 reload_settings(), 工厂会拿到新值
    """
    cleaned: dict[str, Any] = {}
    for k, v in body.updates.items():
        if k not in ALLOWED_KEYS:
            continue
        # 敏感字段: 空字符串视为"不修改", 跳过
        if k in SECRET_KEYS and isinstance(v, str) and v.strip() == "":
            continue
        # 布尔字段
        if k == "GEO_USE_MOCK":
            v = bool(v)
        cleaned[k] = v

    save_runtime_config(cleaned)
    reload_settings()  # 让下次 get_settings() 拿到新值
    return ok({"updated": list(cleaned.keys()), "count": len(cleaned)})


@router.delete("/settings/runtime/{key}")
def delete_runtime_key(key: str) -> dict:
    """从 runtime_config.json 中清除指定字段, 恢复 .env / 默认值。"""
    if key not in ALLOWED_KEYS:
        return err(1001, f"未知或受保护的字段: {key}")
    removed = delete_runtime_keys([key])
    if not removed:
        return err(1002, f"字段 {key} 不在 runtime 配置中 (本来就用 .env / 默认值)")
    reload_settings()
    return ok({"deleted": removed})


class CookieCleanBody(BaseModel):
    raw: str


@router.post("/settings/clean-cookie")
def clean_cookie(body: CookieCleanBody) -> dict:
    """工具接口: 把用户粘的 curl / -b / Cookie header 提取为干净 cookie 字符串。

    前端可在用户粘贴时实时调用, 帮助预览将要保存的值。
    """
    return ok({"cookie": clean_cookie_value(body.raw)})


@router.post("/settings/clean-token")
def clean_token(body: CookieCleanBody) -> dict:
    """工具接口: 把用户粘的 curl / Authorization header / localStorage JSON 提取为
    干净的 Bearer token 字符串。专门服务 DeepSeek refresh_token 这类字段。

    支持的输入:
    - 完整 curl: 自动抓 ``-H 'authorization: Bearer XXX'``
    - 单独 header 行: ``Authorization: Bearer XXX``
    - localStorage JSON: ``{"value":"XXX","__version":1}``
    - 直接粘的纯 token
    """
    return ok({"token": clean_token_value(body.raw)})


# ============================================================
# 测试连接
# ============================================================


@router.post("/settings/test/llm")
def test_llm() -> dict:
    """用当前 LLM 配置发一次 ping prompt, 返回 OK / 错误信息。"""
    try:
        from ..services.llm_client import get_llm_client

        llm = get_llm_client()
        text = llm.generate_sync("请用一句话说: 测试连通", max_tokens=50)
        return ok(
            {
                "ok": True,
                "preview": text[:120],
            }
        )
    except Exception as e:
        return ok({"ok": False, "error": str(e)[:300]})


@router.post("/settings/test/monitor/{platform}")
def test_monitor(platform: str) -> dict:
    try:
        from ..services.ai_monitors import get_ai_monitor
        from ..services.ai_monitors.base import MonitorError

        mon = get_ai_monitor(platform)
        s = mon.settings
        if platform == "chatgpt":
            if not s.OPENAI_API_KEY:
                raise MonitorError("OPENAI_API_KEY 未配置")
            return ok({"ok": True, "message": "ChatGPT 已配置"})
        if platform == "doubao":
            if not s.ARK_API_KEY:
                raise MonitorError("ARK_API_KEY 未配置(火山方舟 API key)")
            return ok({
                "ok": True,
                "message": f"Doubao Ark 已配置 (model={s.DOUBAO_MODEL or 'doubao-seed-1-6-250615'})",
            })
        if platform == "kimi":
            has_api = bool(s.KIMI_API_KEY)
            has_bearer = bool(s.KIMI_BEARER)
            has_cookie = bool(s.KIMI_COOKIE)
            if not (has_api or has_bearer or has_cookie):
                raise MonitorError(
                    "Kimi 未配置 (需要 KIMI_API_KEY / KIMI_BEARER / KIMI_COOKIE 任一)"
                )
            if has_api:
                return ok({"ok": True, "message": "已配置, 模式=api_key"})
            # 走 web 链路: 真请求一发, 验证 bearer 是否过期
            try:
                r = mon.query("你好", brand_keywords=None)  # type: ignore[attr-defined]
            except MonitorError as e:
                return ok({"ok": False, "error": str(e)[:300]})
            mode = "web_bearer" if has_bearer else "web_cookie"
            return ok({
                "ok": True,
                "message": f"已配置, 模式={mode}, 实测对话成功 ({len(r.get('raw_answer',''))} 字)",
            })
        if platform == "deepseek":
            if not s.DEEPSEEK_REFRESH_TOKEN:
                raise MonitorError("DEEPSEEK_REFRESH_TOKEN 未配置")
            # 走真实链路: refresh → access_token, 验证 token 有效
            try:
                access = mon._acquire_access_token(s.DEEPSEEK_REFRESH_TOKEN)  # type: ignore[attr-defined]
            except MonitorError as e:
                return ok({"ok": False, "error": str(e)[:300]})
            return ok({"ok": True, "message": f"DeepSeek refresh_token 有效, access_token={access[:8]}***"})
        if platform == "perplexity":
            if not s.PERPLEXITY_API_KEY:
                raise MonitorError("PERPLEXITY_API_KEY 未配置")
            return ok({
                "ok": True,
                "message": f"Perplexity 已配置 (model={s.PERPLEXITY_MODEL or 'sonar'})",
            })
        if platform == "google_ai":
            if not s.GOOGLE_AI_API_KEY:
                raise MonitorError("GOOGLE_AI_API_KEY 未配置")
            return ok({"ok": True, "message": "Google AI (Gemini) 已配置"})
        return ok({"ok": True, "message": "已配置"})
    except Exception as e:
        return ok({"ok": False, "error": str(e)[:300]})


# ============================================================
# LLM 配置概览
# ============================================================


@router.get("/settings/llm")
def get_llm_settings() -> dict:
    settings = get_settings()
    return ok(
        {
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            "configured": settings.GEO_USE_MOCK
            or bool(
                settings.OPENAI_API_KEY
                or settings.DEEPSEEK_API_KEY
                or settings.ANTHROPIC_API_KEY
                or settings.KIMI_API_KEY
            ),
        }
    )
