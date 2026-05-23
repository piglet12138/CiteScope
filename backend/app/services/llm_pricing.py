"""LLM 价格表 (USD per 1M tokens)。

价格随官方调整, 这里只做近似口径; 真实结算应以 provider 月度账单为准。
更新策略:
  - openai/anthropic: 直接对照官网 pricing 页 (USD)
  - deepseek/moonshot: 官网为人民币计价, 这里按 1 USD ≈ 7.2 CNY 转换
  - 找不到精确匹配的 model 名时, 走 prefix 匹配, 再回落到 provider 默认价

调用方式:
    price = get_price("deepseek", "deepseek-chat")
    cost = (prompt_tokens * price.input_per_mtok + completion_tokens * price.output_per_mtok) / 1_000_000
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float   # USD per 1M input tokens
    output_per_mtok: float  # USD per 1M output tokens


# (provider, model_prefix) → price
# 顺序很重要: 越具体的 prefix 越靠前
_PRICES: list[tuple[str, str, ModelPrice]] = [
    # ----- OpenAI -----
    ("openai", "gpt-4o-mini",      ModelPrice(0.15,  0.60)),
    ("openai", "gpt-4o",           ModelPrice(2.50, 10.00)),
    ("openai", "gpt-4-turbo",      ModelPrice(10.00, 30.00)),
    ("openai", "gpt-4",            ModelPrice(30.00, 60.00)),
    ("openai", "gpt-3.5",          ModelPrice(0.50,  1.50)),
    ("openai", "o1-mini",          ModelPrice(3.00, 12.00)),
    ("openai", "o1",               ModelPrice(15.00, 60.00)),

    # ----- DeepSeek (官网 CNY → USD ≈ /7.2) -----
    # deepseek-chat: 输入 ¥1/M (cache miss), 输出 ¥2/M
    ("deepseek", "deepseek-chat",      ModelPrice(0.14, 0.28)),
    ("deepseek", "deepseek-reasoner",  ModelPrice(0.55, 2.19)),
    ("deepseek", "deepseek-coder",     ModelPrice(0.14, 0.28)),

    # ----- Moonshot / Kimi (官网 CNY → USD) -----
    # moonshot-v1-8k:  ¥12/M     ≈ $1.67/M (输入输出同价)
    # moonshot-v1-32k: ¥24/M     ≈ $3.33/M
    # moonshot-v1-128k: ¥60/M    ≈ $8.33/M
    ("moonshot", "moonshot-v1-8k",   ModelPrice(1.67, 1.67)),
    ("moonshot", "moonshot-v1-32k",  ModelPrice(3.33, 3.33)),
    ("moonshot", "moonshot-v1-128k", ModelPrice(8.33, 8.33)),

    # ----- Anthropic -----
    ("anthropic", "claude-opus-4",      ModelPrice(15.00, 75.00)),
    ("anthropic", "claude-sonnet-4",    ModelPrice(3.00,  15.00)),
    ("anthropic", "claude-haiku-4",     ModelPrice(0.80,   4.00)),
    ("anthropic", "claude-3-5-sonnet",  ModelPrice(3.00,  15.00)),
    ("anthropic", "claude-3-5-haiku",   ModelPrice(0.80,   4.00)),
    ("anthropic", "claude-3-opus",      ModelPrice(15.00, 75.00)),
    ("anthropic", "claude-3-sonnet",    ModelPrice(3.00,  15.00)),
    ("anthropic", "claude-3-haiku",     ModelPrice(0.25,   1.25)),
]

# provider 缺省价 (model 完全不匹配时使用)
_DEFAULT_BY_PROVIDER: dict[str, ModelPrice] = {
    "openai":    ModelPrice(2.50, 10.00),  # 按 gpt-4o
    "deepseek":  ModelPrice(0.14, 0.28),
    "moonshot":  ModelPrice(1.67, 1.67),
    "anthropic": ModelPrice(3.00, 15.00),  # 按 sonnet
    "mock":      ModelPrice(0.0, 0.0),
}


def get_price(provider: str, model: str) -> ModelPrice:
    p = (provider or "").lower()
    m = (model or "").lower()
    for prov, prefix, price in _PRICES:
        if prov == p and m.startswith(prefix):
            return price
    return _DEFAULT_BY_PROVIDER.get(p, ModelPrice(0.0, 0.0))


def calc_cost_usd(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = get_price(provider, model)
    return round(
        (prompt_tokens * price.input_per_mtok + completion_tokens * price.output_per_mtok)
        / 1_000_000,
        6,
    )
