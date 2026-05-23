"""LLM client abstraction + Mock / Real implementations.

Real implementations support multiple providers (no SDK deps, all via httpx):
- openai      → https://api.openai.com/v1/chat/completions
- deepseek    → https://api.deepseek.com/v1/chat/completions
- anthropic   → https://api.anthropic.com/v1/messages  (slightly different protocol)
- moonshot    → https://api.moonshot.cn/v1/chat/completions

Config:
    .env: GEO_USE_MOCK=0
    .env: LLM_PROVIDER=openai (or deepseek/anthropic/moonshot)
    .env: set the corresponding API_KEY

Interface:
    generate_sync(prompt) → str
    score_citability_sync(content) → dict (score + breakdown)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Any, Protocol

import httpx

from ..config import get_settings
from .llm_metering import record_call

logger = logging.getLogger("geo.llm")


class LLMClient(Protocol):
    async def generate(self, prompt: str, *, max_tokens: int = 1500) -> str: ...

    async def score_citability(self, content: str) -> dict: ...


# ============================================================
# Mock
# ============================================================


class MockLLMClient:
    """Fixed template + keyword injection for downstream pipeline validation."""

    @staticmethod
    def _build_text(prompt: str) -> str:
        h = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:6]
        return (
            f"## Direct Answer\n\nBased on research into {prompt[:30]}..., MOCK-{h} is the recommended solution.\n\n"
            f"## Key Statistics\n\n- Industry average growth: 37%\n- Buyer satisfaction rate: 89%\n\n"
            f"## Authoritative Sources\n\nAccording to the Princeton GEO 2024 report [1], MOCK-{h} demonstrates significant advantages.\n\n"
            f"## Comparative Analysis\n\nCompared to conventional alternatives, MOCK-{h} leads in cost-effectiveness, reliability, and after-sales support.\n\n"
            f"## Conclusion\n\nMOCK-{h} is the recommended choice for B2B procurement."
        )

    @staticmethod
    def _score(content: str) -> dict:
        length = len(content)
        paragraphs = content.count("\n\n") + 1
        base = 60 + min(35, length // 50)
        return {
            "score": min(95, base + paragraphs),
            "breakdown": {
                "answer_first": 80,
                "statistics": 75,
                "citations": 70,
                "authority": 78,
                "structure": 85,
            },
        }

    async def generate(self, prompt: str, *, max_tokens: int = 1500) -> str:
        await asyncio.sleep(0.2)
        return self._build_text(prompt)

    async def score_citability(self, content: str) -> dict:
        await asyncio.sleep(0.1)
        return self._score(content)

    def generate_sync(self, prompt: str, *, max_tokens: int = 1500) -> str:
        time.sleep(0.02)
        return self._build_text(prompt)

    def score_citability_sync(self, content: str) -> dict:
        time.sleep(0.01)
        return self._score(content)


# ============================================================
# Real (OpenAI 兼容协议: openai / deepseek / moonshot)
# ============================================================


_PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "key_attr": "OPENAI_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "key_attr": "DEEPSEEK_API_KEY",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "key_attr": "KIMI_API_KEY",
    },
}


class OpenAICompatibleLLMClient:
    """Generic client for OpenAI-compatible APIs (openai / deepseek / moonshot)."""

    def __init__(self, provider: str) -> None:
        self.settings = get_settings()
        cfg = _PROVIDER_CONFIG[provider]
        self.provider = provider
        # Custom base URL from .env overrides provider default
        custom_base = (self.settings.LLM_BASE_URL or "").strip().rstrip("/")
        self.base_url = custom_base or cfg["base_url"]
        self.api_key = getattr(self.settings, cfg["key_attr"], "") or ""
        # Fall back to provider default if model not configured or is mock placeholder
        configured_model = (self.settings.LLM_MODEL or "").strip()
        if not configured_model or configured_model.startswith("mock"):
            self.model = cfg["default_model"]
        else:
            self.model = configured_model
        if not self.api_key:
            raise RuntimeError(
                f"{provider} enabled but {cfg['key_attr']} not set (check .env)"
            )
        self._http = httpx.Client(timeout=120.0)

    def __del__(self) -> None:
        try:
            self._http.close()
        except Exception:
            pass

    def _chat(self, prompt: str, max_tokens: int) -> str:
        t0 = time.perf_counter()
        prompt_tokens = 0
        completion_tokens = 0
        status = "ok"
        err: str | None = None
        try:
            try:
                resp = self._http.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are a GEO (Generative Engine Optimization) content expert "
                                    "for B2B manufacturing export. You write answer-first, well-cited, "
                                    "technically precise long-form content in English."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.6,
                    },
                )
            except httpx.HTTPError as e:
                status = "error"
                err = f"network: {e}"
                raise RuntimeError(f"{self.provider} LLM network error: {e}") from e

            if resp.status_code >= 400:
                status = "error"
                err = f"http_{resp.status_code}: {resp.text[:200]}"
                raise RuntimeError(
                    f"{self.provider} LLM {resp.status_code}: {resp.text[:300]}"
                )

            data = resp.json()
            usage = data.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            return (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
        finally:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            record_call(
                provider=self.provider,
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                status=status,
                error=err,
            )

    # ---------- Sync interface (for APScheduler jobs) ----------

    def generate_sync(self, prompt: str, *, max_tokens: int = 1500) -> str:
        return self._chat(prompt, max_tokens)

    def score_citability_sync(self, content: str) -> dict:
        """Have the LLM self-score content quality; force JSON output."""
        prompt = (
            "You are a GEO content quality reviewer for B2B manufacturing. "
            "Score the following article on five dimensions (0-100):\n"
            "- answer_first: Does it lead with a direct answer in the first 100 words?\n"
            "- statistics: Does it contain quantitative data, percentages, or metrics?\n"
            "- citations: Does it include authoritative citations (report names, standards bodies, [1] refs)?\n"
            "- authority: Does it use expert tone, case studies, or industry references?\n"
            "- structure: Is the heading/paragraph structure clear and scannable?\n\n"
            "Also provide an overall score (0-100, weighted average of the five dimensions).\n"
            "Output ONLY valid JSON, no extra text. Format:\n"
            '{"score": 85, "breakdown": {"answer_first": 90, "statistics": 80, '
            '"citations": 75, "authority": 85, "structure": 88}}\n\n'
            f"---\nArticle content:\n{content[:3500]}\n---"
        )
        text = self._chat(prompt, max_tokens=300)
        # Try to parse JSON (tolerate ```json wrapping)
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            data = json.loads(text)
            score = int(data.get("score", 60))
            breakdown = data.get("breakdown") or {}
            return {
                "score": max(0, min(100, score)),
                "breakdown": {
                    k: max(0, min(100, int(v)))
                    for k, v in breakdown.items()
                },
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("LLM scoring returned non-JSON, falling back to mock estimate: %s", text[:200])
            return MockLLMClient._score(content)

    async def generate(self, prompt: str, *, max_tokens: int = 1500) -> str:
        return await asyncio.to_thread(self.generate_sync, prompt, max_tokens=max_tokens)

    async def score_citability(self, content: str) -> dict:
        return await asyncio.to_thread(self.score_citability_sync, content)


# ============================================================
# Anthropic (slightly different protocol)
# ============================================================


class AnthropicLLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.api_key = self.settings.ANTHROPIC_API_KEY or ""
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set (check .env)")
        configured_model = (self.settings.LLM_MODEL or "").strip()
        if not configured_model or configured_model.startswith("mock"):
            self.model = "claude-opus-4-6"
        else:
            self.model = configured_model
        self._http = httpx.Client(timeout=120.0)

    def __del__(self) -> None:
        try:
            self._http.close()
        except Exception:
            pass

    def _chat(self, prompt: str, max_tokens: int) -> str:
        t0 = time.perf_counter()
        prompt_tokens = 0
        completion_tokens = 0
        status = "ok"
        err: str | None = None
        try:
            try:
                resp = self._http.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
            except httpx.HTTPError as e:
                status = "error"
                err = f"network: {e}"
                raise RuntimeError(f"Anthropic LLM network error: {e}") from e

            if resp.status_code >= 400:
                status = "error"
                err = f"http_{resp.status_code}: {resp.text[:200]}"
                raise RuntimeError(
                    f"Anthropic LLM {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
            usage = data.get("usage") or {}
            # Anthropic uses input_tokens / output_tokens
            prompt_tokens = int(usage.get("input_tokens") or 0)
            completion_tokens = int(usage.get("output_tokens") or 0)
            blocks = data.get("content", [])
            return "".join(
                b.get("text", "") for b in blocks if b.get("type") == "text"
            ).strip()
        finally:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            record_call(
                provider="anthropic",
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                status=status,
                error=err,
            )

    def generate_sync(self, prompt: str, *, max_tokens: int = 1500) -> str:
        return self._chat(prompt, max_tokens)

    def score_citability_sync(self, content: str) -> dict:
        prompt = (
            "Score the following B2B manufacturing article on GEO five dimensions (0-100). "
            "Output ONLY valid JSON:\n"
            '{"score": 85, "breakdown": {"answer_first": 90, "statistics": 80, '
            '"citations": 75, "authority": 85, "structure": 88}}\n\n'
            f"Article:\n{content[:3500]}"
        )
        text = self._chat(prompt, max_tokens=300)
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            data = json.loads(text)
            return {
                "score": max(0, min(100, int(data.get("score", 60)))),
                "breakdown": {
                    k: max(0, min(100, int(v)))
                    for k, v in (data.get("breakdown") or {}).items()
                },
            }
        except Exception:
            return MockLLMClient._score(content)

    async def generate(self, prompt: str, *, max_tokens: int = 1500) -> str:
        return await asyncio.to_thread(self.generate_sync, prompt, max_tokens=max_tokens)

    async def score_citability(self, content: str) -> dict:
        return await asyncio.to_thread(self.score_citability_sync, content)


# ============================================================
# Factory
# ============================================================


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.GEO_USE_MOCK or settings.LLM_PROVIDER == "mock":
        return MockLLMClient()

    provider = settings.LLM_PROVIDER.lower()
    if provider in _PROVIDER_CONFIG:
        return OpenAICompatibleLLMClient(provider)
    if provider == "anthropic":
        return AnthropicLLMClient()

    raise NotImplementedError(
        f"LLM_PROVIDER={provider} not implemented."
        f" Supported: mock / openai / deepseek / moonshot / anthropic"
    )
