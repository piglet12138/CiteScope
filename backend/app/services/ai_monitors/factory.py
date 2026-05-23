"""AI monitor factory."""
from __future__ import annotations

from typing import Type

from .base import BaseMonitor
from .chatgpt import ChatGPTMonitor
from .deepseek import DeepSeekMonitor
from .doubao import DoubaoMonitor
from .google_ai import GoogleAIMonitor
from .kimi import KimiMonitor
from .perplexity import PerplexityMonitor

_REGISTRY: dict[str, Type[BaseMonitor]] = {
    "perplexity": PerplexityMonitor,
    "chatgpt": ChatGPTMonitor,
    "google_ai": GoogleAIMonitor,
    "doubao": DoubaoMonitor,  # 火山方舟 Ark Responses API + web_search
    "deepseek": DeepSeekMonitor,  # chat.deepseek.com 网页 refresh_token 逆向
    "kimi": KimiMonitor,  # Moonshot 官方 API (备用)
    # Aliases
    "openai": ChatGPTMonitor,
    "gpt": ChatGPTMonitor,
}


def get_ai_monitor(platform: str) -> BaseMonitor:
    cls = _REGISTRY.get(platform)
    if cls is None:
        raise KeyError(
            f"Unsupported AI monitor platform: {platform}. Available: {list(_REGISTRY.keys())}"
        )
    return cls()


def list_supported_monitors() -> list[str]:
    return ["perplexity", "chatgpt", "google_ai", "doubao", "deepseek", "kimi"]
