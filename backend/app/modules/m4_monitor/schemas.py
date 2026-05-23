"""M4 监测 Pydantic schemas。"""
from __future__ import annotations

from datetime import datetime, date

from pydantic import BaseModel, Field

DEFAULT_PLATFORMS = ("perplexity", "chatgpt", "google_ai")


class SearchResultItem(BaseModel):
    """AI 回答中引用的搜索来源. cite_index 与 raw_answer 中的 [citation:N] 对齐."""

    cite_index: int | None = None
    title: str = ""
    url: str = ""
    snippet: str = ""
    published_at: float | None = None
    site_icon: str | None = None


class MonitorBody(BaseModel):
    """旧的触发监测 body (保留兼容,新代码请用 RunCreateBody)。"""

    question_ids: list[int] | None = None
    platforms: list[str] | None = None
    max_questions: int | None = None
    extra_question_texts: list[str] | None = None


class RunCreateBody(BaseModel):
    """新建一次「对比实验」运行。"""

    name: str = Field(..., min_length=1, max_length=200)
    note: str | None = None
    question_ids: list[int] | None = None
    extra_question_texts: list[str] | None = None
    platforms: list[str] | None = None
    max_questions: int | None = None


class ReportCreateBody(BaseModel):
    period_start: date
    period_end: date


class MonitorResultOut(BaseModel):
    id: int
    client_id: int
    question_id: int
    run_id: int | None = None
    platform: str
    is_mentioned: bool
    position: int | None
    has_link: bool
    sentiment: str | None
    raw_answer: str | None
    search_results: list[SearchResultItem] | None = None
    screenshot_path: str | None
    checked_at: datetime


class TrendPoint(BaseModel):
    date: str
    mention_rate: float


class PlatformBreakdown(BaseModel):
    platform: str
    mention_rate: float
    sample_size: int


class MetricsOut(BaseModel):
    client_id: int
    period: str
    mention_rate: float = 0.0
    first_mention_rate: float = 0.0
    link_citation_rate: float = 0.0
    sentiment_accuracy: float = 0.0
    trend: list[TrendPoint] = Field(default_factory=list)
    by_platform: list[PlatformBreakdown] = Field(default_factory=list)


class ReportOut(BaseModel):
    id: int
    client_id: int
    period_start: date
    period_end: date
    summary: str
    metrics_snapshot: dict
    created_at: datetime


# ---------- Run / 对比实验 ----------
class RunOut(BaseModel):
    id: int
    client_id: int
    name: str
    note: str | None = None
    platforms: list[str] = Field(default_factory=list)
    question_count: int = 0
    status: str = "running"
    created_at: datetime
    finished_at: datetime | None = None
    # 该 run 的总体提及率,前端列表用
    mention_rate: float = 0.0
    sample_size: int = 0


class RunPlatformCell(BaseModel):
    platform: str
    mention_rate: float
    first_mention_rate: float
    link_citation_rate: float
    sample_size: int


class RunCompareEntry(BaseModel):
    run_id: int
    run_name: str
    created_at: datetime
    overall: RunPlatformCell  # 跨所有平台的合计
    by_platform: list[RunPlatformCell]


class RunCompareOut(BaseModel):
    runs: list[RunCompareEntry]
    platforms: list[str]
