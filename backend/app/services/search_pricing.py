"""AI 搜索引擎(M4 监测)调用成本估算。

GEO 监测会大量调用各 AI 引擎的「搜索接口」(ChatGPT search-preview /
Perplexity sonar / Gemini grounding / Kimi web / 豆包 / DeepSeek 等)。
这部分调用 *不是* 普通 LLM 推理,定价模型差异较大:

- **有 token 计价的**(OpenAI 兼容协议):chatgpt, perplexity, google_ai
  使用 llm_pricing 表 + per-search 加价
- **网页态(无官方 token 计费)**:kimi, doubao, deepseek
  按 per-query 估算成本(基于运营时段消耗推算)

不同平台 per-search 附加费(USD/call,搜索使用费,不含 LLM token):
"""
from __future__ import annotations

from .llm_pricing import calc_cost_usd

# per-call 搜索使用费(USD),不含 LLM token
_PER_SEARCH_FEE: dict[str, float] = {
    "chatgpt": 0.025,      # OpenAI search-preview 含搜索 ~$25/1k queries
    "perplexity": 0.005,   # sonar 基础 $5/1k requests
    "google_ai": 0.035,    # Gemini grounding $35/1k requests
    "kimi": 0.002,         # 估算:运营成本摊销
    "doubao": 0.002,
    "deepseek": 0.002,
}

# 各 platform 在 llm_pricing 里对应的 (provider, model) — 用来算 token 成本
_TOKEN_PRICE_MAP: dict[str, tuple[str, str]] = {
    "chatgpt": ("openai", "gpt-4o-mini"),
    "perplexity": ("openai", "gpt-4o-mini"),
    "google_ai": ("openai", "gpt-4o-mini"),
    "kimi": ("moonshot", "moonshot-v1-8k"),
    "doubao": ("deepseek", "deepseek-chat"),
    "deepseek": ("deepseek", "deepseek-chat"),
}


def estimate_search_cost_usd(
    platform: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> float:
    """估算一次搜索调用的成本(USD)。

    = per-search 附加费 + (token 成本如果有 token 数据)
    """
    fee = _PER_SEARCH_FEE.get(platform.lower(), 0.0)
    if prompt_tokens or completion_tokens:
        provider, model = _TOKEN_PRICE_MAP.get(platform.lower(), ("mock", ""))
        token_cost = calc_cost_usd(provider, model, prompt_tokens, completion_tokens)
        fee += token_cost
    return round(fee, 6)
