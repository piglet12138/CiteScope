"""全局配置。

通过 pydantic-settings 从环境变量加载,支持 .env 文件。

切换 mock → real 操作步骤:
1. 复制 .env.example → .env
2. 设置 GEO_USE_MOCK=0
3. 至少配置 LLM_PROVIDER + 对应 API_KEY (如 deepseek + DEEPSEEK_API_KEY)
4. 配置至少一个 AI 监测凭证 (如 OPENAI_API_KEY 用于 ChatGPT, 或 DOUBAO_COOKIE)
5. 启动时 assert_real_mode_keys() 会校验是否至少有 LLM key
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === 全局开关 ===
    GEO_USE_MOCK: bool = True
    GEO_LOG_LEVEL: str = "INFO"
    GEO_DB_PATH: str = "./data/geo.db"
    GEO_SCREENSHOT_DIR: str = "./data/screenshots"

    # === LLM (M4 监测内部可能用于 mention 判定 / 情感分析) ===
    LLM_PROVIDER: str = "mock"
    LLM_MODEL: str = ""  # empty → llm_client uses provider default model
    LLM_BASE_URL: str = ""  # custom base URL for relay/proxy (overrides provider default)
    OPENAI_API_KEY: str = ""
    OPENAI_OFFICIAL_API_KEY: str = ""  # Official OpenAI key for ChatGPT monitor (web search)
    OPENAI_MONITOR_MODEL: str = "gpt-4o-mini"  # ChatGPT 监测用模型
    ANTHROPIC_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    KIMI_API_KEY: str = ""  # Moonshot official key
    PERPLEXITY_API_KEY: str = ""  # Perplexity sonar API
    PERPLEXITY_API_BASE: str = "https://api.perplexity.ai"  # or https://openrouter.ai/api/v1
    PERPLEXITY_MODEL: str = "sonar"  # or perplexity/sonar-pro-search via OpenRouter
    GOOGLE_AI_API_KEY: str = ""  # Google AI (Gemini) API key

    # === AI 监测平台 (M4) ===
    # 豆包 / 火山方舟 Ark Responses API + web_search 内置工具。
    # 在火山引擎控制台 → 方舟 → API Key 管理 创建,Bearer 直接用。
    # 调用 https://ark.cn-beijing.volces.com/api/v3/responses,模型 endpoint id 如 doubao-seed-1-6-250615
    ARK_API_KEY: str = ""
    DOUBAO_MODEL: str = "doubao-seed-1-6-250615"
    ARK_API_BASE: str = "https://ark.cn-beijing.volces.com/api/v3"
    # === 历史/逆向 字段(2026-05 重构后不再展示在 UI,但保留兼容)===
    DOUBAO_REFRESH_TOKEN: str = ""
    DOUBAO_COOKIE: str = ""
    KIMI_COOKIE: str = ""
    # Kimi web 监测: 实际只需要 JWT Bearer (可从浏览器抓包 authorization 头获取,
    # 或 Cookie 里的 kimi-auth 字段). 有效期通常 ~30 天.
    # device_id / ssid / traffic_id 都编码在 JWT 的 payload 里, 程序会自动解析.
    KIMI_BEARER: str = ""
    # DeepSeek web 监测: 走 chat.deepseek.com 内部 API + POW.
    # 不是 LLM API key, 是浏览器 localStorage 里那个长字符串 token, 在 F12 → Application
    # → Local Storage → chat.deepseek.com → userToken (字段名 value) 里。
    DEEPSEEK_REFRESH_TOKEN: str = ""
    # ChatGPT 走 OPENAI_API_KEY (上面已定义)

    # === 可选 ===
    DATAFORSEO_LOGIN: str = ""
    DATAFORSEO_PASSWORD: str = ""

    @property
    def db_url(self) -> str:
        path = Path(self.GEO_DB_PATH).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"

    @property
    def screenshot_dir(self) -> Path:
        d = Path(self.GEO_SCREENSHOT_DIR).resolve()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def assert_real_mode_keys(self) -> None:
        """非 mock 模式下校验必需 key (仅强制 LLM, 平台凭证按需校验)。

        策略: LLM 是 GEO 流水线的核心, 缺失则系统无法生成内容, 必须报错。
        发布平台和监测平台是按需调用的, 可以一次只接入一个,
        所以这里只警告不阻塞 — 调用具体接口时再抛 PublishError/MonitorError。
        """
        if self.GEO_USE_MOCK:
            return

        provider = self.LLM_PROVIDER.lower()
        if provider == "mock":
            raise RuntimeError(
                "GEO_USE_MOCK=0 但 LLM_PROVIDER=mock。"
                " 请将 LLM_PROVIDER 改为 openai/deepseek/moonshot/anthropic 之一,"
                " 或保持 GEO_USE_MOCK=1。"
            )

        provider_to_key = {
            "openai": ("OPENAI_API_KEY", self.OPENAI_API_KEY),
            "deepseek": ("DEEPSEEK_API_KEY", self.DEEPSEEK_API_KEY),
            "moonshot": ("KIMI_API_KEY", self.KIMI_API_KEY),
            "anthropic": ("ANTHROPIC_API_KEY", self.ANTHROPIC_API_KEY),
        }
        if provider not in provider_to_key:
            raise RuntimeError(
                f"未知 LLM_PROVIDER={provider};"
                f" 支持: {list(provider_to_key.keys())}"
            )
        key_name, key_value = provider_to_key[provider]
        if not key_value:
            raise RuntimeError(
                f"GEO_USE_MOCK=0 且 LLM_PROVIDER={provider} 但 {key_name} 为空。"
                f" 请填写 .env 中的 {key_name}。"
            )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # 运行时配置覆盖 (前端可编辑, 优先级高于 .env)
    try:
        from .services.runtime_config import load_runtime_config

        overlay = load_runtime_config()
        for k, v in overlay.items():
            if hasattr(s, k):
                # Pydantic v2: 允许通过 __dict__ 直接设置 (BaseSettings 默认 mutable)
                try:
                    setattr(s, k, v)
                except Exception:
                    pass
    except Exception as e:
        import logging

        logging.getLogger("geo.config").warning("runtime_config 加载失败: %s", e)
    return s


def reload_settings() -> Settings:
    """前端写入新配置后调用, 强制下次 get_settings() 重新加载。"""
    get_settings.cache_clear()
    return get_settings()
