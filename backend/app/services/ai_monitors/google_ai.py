"""Google AI (Gemini) monitor with Google Search grounding.

Uses the Gemini API with built-in Google Search grounding to simulate
Google AI Overviews behavior. Returns grounding chunks as search_results.

Config: set GOOGLE_AI_API_KEY in .env (get from https://aistudio.google.com/apikey)
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import BaseMonitor, MonitorError

logger = logging.getLogger("geo.ai_monitor.google_ai")

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_MODEL = "gemini-2.5-flash"


class GoogleAIMonitor(BaseMonitor):
    platform_id = "google_ai"

    def query(
        self, question: str, *, brand_keywords: list[str] | None = None
    ) -> dict[str, Any]:
        api_key = (self.settings.GOOGLE_AI_API_KEY or "").strip()
        if not api_key:
            raise MonitorError("GOOGLE_AI_API_KEY not configured")

        url = f"{_API_BASE}/{_MODEL}:generateContent?key={api_key}"

        try:
            resp = self.http.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": question}]}],
                    "tools": [{"google_search": {}}],
                },
                timeout=60.0,
            )
        except httpx.HTTPError as e:
            raise MonitorError(f"Google AI network error: {e}") from e

        if resp.status_code >= 400:
            raise MonitorError(
                f"Google AI API {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()

        # Extract answer text
        candidates = data.get("candidates", [])
        if not candidates:
            return self._empty_result("(no candidates returned)")

        candidate = candidates[0]
        parts = candidate.get("content", {}).get("parts", [])
        answer = " ".join(p.get("text", "") for p in parts).strip() or "(empty response)"

        # Extract grounding sources
        grounding = candidate.get("groundingMetadata", {})
        chunks = grounding.get("groundingChunks", [])
        search_results = self._parse_grounding(chunks) if chunks else None

        if search_results:
            analysis = self.analyze_mention_with_sources(
                answer, search_results, brand_keywords
            )
        else:
            analysis = self.analyze_mention(answer, brand_keywords)

        # Gemini usage 在 usageMetadata 字段
        um = data.get("usageMetadata") or {}
        screenshot = self.save_answer_text(answer)
        return {
            **analysis,
            "raw_answer": answer,
            "search_results": search_results,
            "screenshot_path": str(screenshot),
            "usage": {
                "model": _MODEL,
                "prompt_tokens": int(um.get("promptTokenCount") or 0),
                "completion_tokens": int(um.get("candidatesTokenCount") or 0),
            },
        }

    @staticmethod
    def _parse_grounding(chunks: list) -> list[dict] | None:
        """Convert Gemini groundingChunks to SearchResultItem format."""
        results = []
        for idx, chunk in enumerate(chunks, start=1):
            web = chunk.get("web", {})
            if not web:
                continue
            results.append({
                "cite_index": idx,
                "title": web.get("title", ""),
                "url": web.get("uri", ""),
                "snippet": "",
                "published_at": None,
                "site_icon": None,
            })
        return results if results else None

    def _empty_result(self, msg: str) -> dict[str, Any]:
        screenshot = self.save_answer_text(msg)
        return {
            "is_mentioned": False,
            "position": None,
            "has_link": False,
            "sentiment": None,
            "raw_answer": msg,
            "search_results": None,
            "screenshot_path": str(screenshot),
        }
