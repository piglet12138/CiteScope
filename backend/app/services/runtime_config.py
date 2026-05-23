"""运行时配置存储 (前端可编辑)。

存储位置: data/runtime_config.json
覆盖优先级: runtime_config.json > .env > Settings 默认值

线程安全: 用 threading.Lock 包裹读写, 避免并发写损坏。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("geo.runtime_config")

# 允许通过 runtime_config.json 覆盖的字段白名单
# (避免用户误改 GEO_DB_PATH 之类的关键路径)
ALLOWED_KEYS: set[str] = {
    # 全局
    "GEO_LOG_LEVEL",
    # AI 搜索 / 监测 — 优先官方 API,DeepSeek 无 search API 走逆向
    "OPENAI_API_KEY",
    "OPENAI_OFFICIAL_API_KEY",
    "OPENAI_MONITOR_MODEL",
    "PERPLEXITY_API_KEY",
    "PERPLEXITY_API_BASE",
    "PERPLEXITY_MODEL",
    "GOOGLE_AI_API_KEY",
    "KIMI_API_KEY",
    # 火山方舟 Ark Web Search (Doubao 官方)
    "ARK_API_KEY",
    "DOUBAO_MODEL",
    "ARK_API_BASE",
    # DeepSeek (官方无 search API,走 chat.deepseek.com 网页 refresh_token 逆向)
    "DEEPSEEK_REFRESH_TOKEN",
}

# 这些字段在 GET 时被 mask, PUT 时空字符串=不修改
SECRET_KEYS: set[str] = {
    "OPENAI_API_KEY",
    "OPENAI_OFFICIAL_API_KEY",
    "PERPLEXITY_API_KEY",
    "GOOGLE_AI_API_KEY",
    "KIMI_API_KEY",
    "ARK_API_KEY",
    "DEEPSEEK_REFRESH_TOKEN",
}

_lock = threading.Lock()


def _config_path() -> Path:
    # 与 GEO_DB_PATH 同目录, 但不依赖 get_settings (避免循环 import)
    import os

    db_path = os.environ.get("GEO_DB_PATH", "./data/geo.db")
    return Path(db_path).resolve().parent / "runtime_config.json"


def load_runtime_config() -> dict[str, Any]:
    """从 JSON 文件读取覆盖配置。文件不存在返回空 dict。"""
    path = _config_path()
    if not path.exists():
        return {}
    with _lock:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                logger.warning("runtime_config.json 顶层不是 dict, 忽略")
                return {}
            # 过滤白名单外的 key
            return {k: v for k, v in data.items() if k in ALLOWED_KEYS}
        except json.JSONDecodeError as e:
            logger.error("runtime_config.json 解析失败: %s", e)
            return {}


def save_runtime_config(updates: dict[str, Any]) -> dict[str, Any]:
    """合并并写回。空字符串 = 删除该 key (恢复 .env / 默认值)。

    返回写入后的完整配置 (用于响应)。
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with _lock:
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8")) or {}
            except json.JSONDecodeError:
                logger.warning("旧 runtime_config 损坏, 覆盖")

        for k, v in updates.items():
            if k not in ALLOWED_KEYS:
                logger.warning("忽略未授权字段: %s", k)
                continue
            if isinstance(v, str):
                if v == "":
                    # 空字符串 = 删除 key, 恢复 .env / 默认值
                    existing.pop(k, None)
                    continue
                # 自动清洗 token / cookie / curl 粘贴
                if k.endswith("_REFRESH_TOKEN") or k.endswith("_API_KEY"):
                    v = clean_token_value(v)
                elif k in SECRET_KEYS or k.endswith("_COOKIE"):
                    v = clean_cookie_value(v)
            existing[k] = v

        path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        logger.info("runtime_config.json 已更新, 当前 keys: %s", list(existing.keys()))
        return existing


def delete_runtime_keys(keys: list[str]) -> list[str]:
    """从 runtime_config.json 中删除指定 key, 返回被实际删除的 key 列表。"""
    path = _config_path()
    if not path.exists():
        return []
    with _lock:
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            logger.warning("runtime_config 损坏, 视为空")
            existing = {}
        removed: list[str] = []
        for k in keys:
            if k in existing:
                del existing[k]
                removed.append(k)
        if removed:
            path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            logger.info("runtime_config.json 删除字段: %s", removed)
        return removed


def clean_cookie_value(raw: str) -> str:
    """从用户的各种粘贴格式中提取干净的 cookie 字符串。

    支持:
    - curl 命令: ``-b 'a=1; b=2'`` 或 ``-H 'Cookie: a=1'``
    - 整段 curl: 提取其中的 -b / Cookie header
    - HTTP header 风格: ``Cookie: a=1; b=2``
    - 已经干净的字符串
    """
    import re

    s = raw.strip()
    if not s:
        return ""

    # 整段 curl: 优先抓 -b 'xxx' 或 --cookie 'xxx'
    m = re.search(r"(?:-b|--cookie)\s+(['\"])(.*?)\1", s, re.DOTALL)
    if m:
        return _clean_cookie_inner(m.group(2))

    # Cookie header (-H 'Cookie: xxx' 或 'cookie: xxx')
    m = re.search(r"(?:-H\s+['\"])?[Cc]ookie:\s*([^'\"\n]+)", s)
    if m:
        return _clean_cookie_inner(m.group(1))

    # 用户直接粘了 "-b '...'" 而没带 curl 前缀
    m = re.match(r"^-b\s+(['\"])(.*)\1$", s, re.DOTALL)
    if m:
        return _clean_cookie_inner(m.group(2))

    return _clean_cookie_inner(s)


def clean_token_value(raw: str) -> str:
    """从用户的各种粘贴格式中提取 Bearer token / refresh_token 字符串。

    支持的输入:
    - 整段 curl: 抓 ``-H 'authorization: Bearer XXX'`` 或 ``-H 'Authorization: Bearer XXX'``
    - 单独的 header 行: ``Authorization: Bearer XXX``
    - 浏览器 localStorage 的 JSON 串: ``{"value":"XXX","__version":1}``
    - 直接粘的纯 token (不带任何前缀)

    专门为 DeepSeek 这类 refresh_token 设计 (不像 cookie 那样有 ``name=value;`` 结构)。
    """
    import json as _json
    import re

    s = raw.strip()
    if not s:
        return ""

    # 1) 完整 curl 或 -H 行: authorization: Bearer XXX
    m = re.search(
        r"[Aa]uthorization\s*:\s*Bearer\s+([A-Za-z0-9_.\-+/=]+)",
        s,
    )
    if m:
        return m.group(1).strip()

    # 2) localStorage JSON: {"value":"...","__version":1} 或 {"token":"..."} 等
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = _json.loads(s)
        except _json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            for key in ("value", "token", "access_token", "refresh_token", "userToken"):
                v = obj.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()

    # 3) 已经是干净 token (单行, 仅由 token 合法字符组成)
    one_line = s.replace("\n", " ").strip().strip("'\"")
    if re.fullmatch(r"[A-Za-z0-9_.\-+/=]+", one_line):
        return one_line

    # 4) 否则放弃, 原样返回 (让用户自己判断)
    return one_line


def _clean_cookie_inner(s: str) -> str:
    s = s.strip().strip("'\"")
    # 去掉行尾的反斜杠续行符
    s = s.replace("\\\n", " ").replace("\n", " ")
    # 多空格归一
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()


def mask_secret(value: Any) -> str:
    """敏感字段展示用掩码: sk-1***xxxx"""
    if not value:
        return ""
    s = str(value)
    if len(s) <= 8:
        return "***"
    return s[:4] + "***" + s[-4:]
