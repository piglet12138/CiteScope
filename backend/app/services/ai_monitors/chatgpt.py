"""ChatGPT (OpenAI) monitor with web search.

Uses the official OpenAI API with gpt-4o-mini-search-preview model
and web_search_options for real-time web search results.

Config:
  - OPENAI_OFFICIAL_API_KEY: Official OpenAI API key (required for web search)
  - OPENAI_MONITOR_MODEL: defaults to gpt-4o-mini-search-preview
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import BaseMonitor, MonitorError

logger = logging.getLogger("geo.ai_monitor.chatgpt")


class ChatGPTMonitor(BaseMonitor):
    platform_id = "chatgpt"

    def query(
        self, question: str, *, brand_keywords: list[str] | None = None
    ) -> dict[str, Any]:
        # Prefer official key for web search; fall back to generic OPENAI_API_KEY
        api_key = (
            getattr(self.settings, "OPENAI_OFFICIAL_API_KEY", "") or ""
        ).strip() or (self.settings.OPENAI_API_KEY or "").strip()

        if not api_key:
            raise MonitorError("OPENAI_OFFICIAL_API_KEY / OPENAI_API_KEY not configured")

        model = self.settings.OPENAI_MONITOR_MODEL or "gpt-4o-mini-search-preview"
        is_search_model = "search" in model

        body: dict[str, Any] = {
            "model": model,
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
        }

        # search-preview models don't support temperature
        if not is_search_model:
            body["temperature"] = 0.4

        if is_search_model:
            body["web_search_options"] = {"search_context_size": "medium"}

        try:
            resp = self.http.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=60.0,
            )
        except httpx.HTTPError as e:
            raise MonitorError(f"ChatGPT network error: {e}") from e

        if resp.status_code >= 400:
            raise MonitorError(
                f"ChatGPT API {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        message = data.get("choices", [{}])[0].get("message", {})
        answer = message.get("content", "").strip() or "(empty response)"
        usage = data.get("usage") or {}

        # Extract web search annotations as search_results
        annotations = message.get("annotations", [])
        search_results = None
        if annotations:
            search_results = [
                {
                    "cite_index": idx,
                    "title": (a.get("url_citation", {}) or a).get("title", ""),
                    "url": (a.get("url_citation", {}) or a).get("url", ""),
                    "snippet": "",
                }
                for idx, a in enumerate(annotations, 1)
                if a.get("type") == "url_citation"
            ]
            if not search_results:
                search_results = None

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
                "model": model,
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
            },
        }
