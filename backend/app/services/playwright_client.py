"""AI 引擎查询客户端抽象 + Mock / Real 实现。

Mock 用于 M4 AI 监测: query_ai_sync() 返回伪造的 AI 回答 + 截图路径。

Real 实现 (GEO_USE_MOCK=0) 委派给 services.ai_monitors.factory.get_ai_monitor(platform)。

⚠️ 文件名保留 "playwright_client" 以兼容现有 import,但实际走 httpx,
   不依赖 Playwright 浏览器自动化 (Wechatsync 模式: HTTP + cookies + 平台官方 web API)。
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from ..config import get_settings

logger = logging.getLogger("geo.client")


class PlaywrightClient(Protocol):
    async def query_ai(self, platform: str, question: str) -> dict: ...

    def query_ai_sync(
        self, platform: str, question: str, brand_keywords: list[str] | None = None
    ) -> dict: ...


class MockPlaywrightClient:
    async def query_ai(self, platform: str, question: str) -> dict:
        await asyncio.sleep(0.5)
        return self._fake_query(platform, question)

    def query_ai_sync(
        self,
        platform: str,
        question: str,
        brand_keywords: list[str] | None = None,
    ) -> dict:
        time.sleep(0.02)
        return self._fake_query(platform, question)

    def _fake_query(self, platform: str, question: str) -> dict:
        is_mentioned = random.random() > 0.35  # ~65% 提及率
        position = random.randint(1, 5) if is_mentioned else None
        screenshot = self._save_fake_screenshot(platform)
        return {
            "is_mentioned": is_mentioned,
            "position": position,
            "has_link": is_mentioned and random.random() > 0.5,
            "sentiment": random.choice(["positive", "neutral", "negative"]) if is_mentioned else None,
            "raw_answer": f"[MOCK {platform}] Response for '{question[:40]}...'",
            "screenshot_path": str(screenshot),
        }

    @staticmethod
    def _save_fake_screenshot(platform: str) -> Path:
        settings = get_settings()
        d = settings.screenshot_dir / platform
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{uuid4().hex[:8]}.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        return f.relative_to(settings.screenshot_dir.parent)


class RealPlaywrightClient:
    """Real mode: delegates to ai_monitors."""

    async def query_ai(self, platform: str, question: str) -> dict:
        return self.query_ai_sync(platform, question)

    def query_ai_sync(
        self,
        platform: str,
        question: str,
        brand_keywords: list[str] | None = None,
    ) -> dict:
        from .ai_monitors import get_ai_monitor
        from .ai_monitors.base import MonitorError

        monitor = get_ai_monitor(platform)
        try:
            return monitor.query(question, brand_keywords=brand_keywords)
        except MonitorError as e:
            logger.warning("[%s] AI query failed: %s", platform, e)
            return {
                "is_mentioned": False,
                "position": None,
                "has_link": False,
                "sentiment": None,
                "raw_answer": f"[ERROR {platform}] {e}",
                "screenshot_path": "",
            }
        finally:
            monitor.close()


def get_playwright_client() -> PlaywrightClient:
    settings = get_settings()
    if settings.GEO_USE_MOCK:
        return MockPlaywrightClient()
    return RealPlaywrightClient()
