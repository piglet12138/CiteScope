"""Perplexity AI monitor — the primary engine for Western B2B GEO monitoring.

Uses the Perplexity API (OpenAI-compatible) with the 'sonar' model which
includes built-in web search and returns a citations array.

Config: set PERPLEXITY_API_KEY in .env
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import BaseMonitor, MonitorError

logger = logging.getLogger("geo.ai_monitor.perplexity")


class PerplexityMonitor(BaseMonitor):
    platform_id = "perplexity"

    def query(
        self, question: str, *, brand_keywords: list[str] | None = None
    ) -> dict[str, Any]:
        api_key = (self.settings.PERPLEXITY_API_KEY or "").strip()
        if not api_key:
            raise MonitorError("PERPLEXITY_API_KEY not configured")

        try:
            resp = self.http.post(
                f"{(self.settings.PERPLEXITY_API_BASE or 'https://api.perplexity.ai').rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.PERPLEXITY_MODEL or "sonar",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a procurement research assistant helping B2B buyers "
                                "evaluate industrial suppliers and manufacturers. When asked, "
                                "recommend 3-5 relevant manufacturers with specific product "
                                "capabilities, certifications, and export experience."
                            ),
                        },
                        {"role": "user", "content": question},
                    ],
                    "temperature": 0.3,
                },
                timeout=60.0,
            )
        except httpx.HTTPError as e:
            raise MonitorError(f"Perplexity network error: {e}") from e

        if resp.status_code >= 400:
            raise MonitorError(
                f"Perplexity API {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        answer = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        ) or "(empty response)"
        usage = data.get("usage") or {}

        # Perplexity native API returns top-level 'citations' array;
        # OpenRouter wraps them as message.annotations with type 'url_citation'
        citations_raw = data.get("citations", [])
        if not citations_raw:
            message = data.get("choices", [{}])[0].get("message", {})
            annotations = message.get("annotations", [])
            if annotations:
                citations_raw = [
                    a.get("url_citation", a) for a in annotations
                    if a.get("type") == "url_citation"
                ]
        search_results = self._parse_citations(citations_raw) if citations_raw else None

        if search_results:
            analysis = self.analyze_mention_with_sources(
                answer, search_results, brand_keywords
            )
        else:
            analysis = self.analyze_mention(answer, brand_keywords)

        screenshot = self.save_answer_text(answer)
        return {
            **analysis,
            "raw_answer": answer,
            "search_results": search_results,
            "screenshot_path": str(screenshot),
            "usage": {
                "model": self.settings.PERPLEXITY_MODEL or "sonar",
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
            },
        }

    @staticmethod
    def _parse_citations(citations: list) -> list[dict] | None:
        """Convert Perplexity citations (list of URL strings) to SearchResultItem format."""
        results = []
        for idx, cite in enumerate(citations, start=1):
            if isinstance(cite, str):
                results.append({
                    "cite_index": idx,
                    "title": cite.split("//")[-1].split("/")[0] if "//" in cite else cite,
                    "url": cite,
                    "snippet": "",
                    "published_at": None,
                    "site_icon": None,
                })
            elif isinstance(cite, dict):
                results.append({
                    "cite_index": idx,
                    "title": cite.get("title", ""),
                    "url": cite.get("url", ""),
                    "snippet": cite.get("snippet", ""),
                    "published_at": None,
                    "site_icon": None,
                })
        return results if results else None
