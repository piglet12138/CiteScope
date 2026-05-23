"""AI 监测查询基类。

设计原则:
- 同步接口 (供 APScheduler job 调用)
- 客户品牌名匹配判定 is_mentioned/position
- 真实截图保存到 settings.screenshot_dir
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from ...config import get_settings

logger = logging.getLogger("geo.ai_monitor")


class MonitorError(Exception):
    pass


class BaseMonitor(ABC):
    platform_id: str = ""
    timeout: float = 60.0  # AI 回答可能比较慢

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: httpx.Client | None = None

    @property
    def http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                },
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def load_cookie_string(self, env_name: str) -> str:
        from_env = getattr(self.settings, env_name, "") or ""
        return from_env.strip()

    def require_cookie(self, env_name: str) -> str:
        c = self.load_cookie_string(env_name)
        if not c:
            raise MonitorError(
                f"{self.platform_id} cookie 未配置: 设置 .env 中的 {env_name}"
            )
        return c

    def save_answer_text(self, text: str) -> Path:
        """把 AI 文本回答保存为 .txt (供后续审计 / 替代截图)。"""
        d = self.settings.screenshot_dir / self.platform_id
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{uuid4().hex[:8]}.txt"
        f.write_text(text, encoding="utf-8")
        return f.relative_to(self.settings.screenshot_dir.parent)

    @abstractmethod
    def query(self, question: str, *, brand_keywords: list[str] | None = None) -> dict[str, Any]:
        """查询 AI 平台并返回结构化结果。"""

    # ---------- 共享: 文本分析 ----------

    @staticmethod
    def analyze_mention(
        answer: str, brand_keywords: list[str] | None
    ) -> dict[str, Any]:
        """从 AI 文本回答中分析品牌提及。

        position: 第一个匹配 keyword 出现在第几个段落 (1-based)
        has_link: 是否包含 http(s):// (粗略判断)
        sentiment: 简单关键词法 (正/中/负) — 真实场景可换 LLM 评分
        """
        if not brand_keywords:
            return {
                "is_mentioned": False,
                "position": None,
                "has_link": "http" in answer,
                "sentiment": None,
            }
        paragraphs = [p for p in answer.split("\n") if p.strip()]
        position = None
        for i, p in enumerate(paragraphs, start=1):
            if any(k.lower() in p.lower() for k in brand_keywords):
                position = i
                break

        is_mentioned = position is not None
        sentiment = None
        if is_mentioned:
            negative_words = [
                "poor", "overpriced", "unreliable", "defective", "disappointing",
                "avoid", "complaint", "substandard", "delay", "inconsistent",
            ]
            positive_words = [
                "recommended", "reliable", "cost-effective", "certified", "durable",
                "quality", "trusted", "efficient", "professional", "compliant",
            ]
            n = sum(answer.count(w) for w in negative_words)
            p = sum(answer.count(w) for w in positive_words)
            if p > n:
                sentiment = "positive"
            elif n > p:
                sentiment = "negative"
            else:
                sentiment = "neutral"

        return {
            "is_mentioned": is_mentioned,
            "position": position,
            "has_link": "http" in answer,
            "sentiment": sentiment,
        }

    @classmethod
    def analyze_mention_with_sources(
        cls,
        answer: str,
        sources: list[dict[str, Any]] | None,
        brand_keywords: list[str] | None,
    ) -> dict[str, Any]:
        """在正文分析基础上, 叠加联网搜索结果的品牌命中判定.

        联网模型 (Kimi / DeepSeek) 常出现 "搜索结果里出现了品牌, 但答案正文没复述"
        的场景, 仅分析 raw_answer 会漏掉这种真实曝光. 这里:
        - 只要 sources 里有任一 {title, snippet, url} 命中品牌词, 就标 is_mentioned=True
        - has_link 在有来源时强制 True (本来就是带链接的引用)
        - position: 优先用正文段落位置, 否则用命中的来源在 sources 中的 1-based 下标
        """
        base = cls.analyze_mention(answer, brand_keywords)
        if sources:
            base["has_link"] = True
            if brand_keywords and not base.get("is_mentioned"):
                kws = [k.lower() for k in brand_keywords if k]
                for idx, s in enumerate(sources, start=1):
                    blob = " ".join(
                        [
                            str(s.get("title") or ""),
                            str(s.get("snippet") or ""),
                            str(s.get("url") or ""),
                        ]
                    ).lower()
                    if any(k in blob for k in kws):
                        base["is_mentioned"] = True
                        base["position"] = base.get("position") or idx
                        # 无正文命中时无法做情感, 先给个 neutral 而不是 None
                        if base.get("sentiment") is None:
                            base["sentiment"] = "neutral"
                        break
        return base
