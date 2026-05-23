"""SQLAlchemy 模型。

GEO 效果监测实验平台 (重构于 2026-05-22):
    - 6 张核心表: clients / questions / monitor_runs / monitor_results /
      reports / llm_call_logs / diagnosis_results
    - 已废弃的表 (articles / publications / platform_accounts) 由
      scripts/migrate_drop_legacy.py 一次性 DROP
"""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Client(Base):
    """监测对象 (品牌 / 公司 / 产品)。

    历史命名为 Client,本次重构后语义改为「被监测的品牌」,
    表名保持 clients 以避免数据迁移。
    """

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    business_info: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="basic")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    target_markets: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_repo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    questions: Mapped[list["Question"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class Question(Base):
    """探针问题 (Probe Question)。

    监测用的提问语料。原本由 M1 LLM 自动生成,重构后改为「手工录入 +
    CSV 导入」。category 字段保留但语义弱化,仅作为前端分组标签。
    """

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    client: Mapped[Client] = relationship(back_populates="questions")


class MonitorRun(Base):
    """一次「对比实验」运行:同一题集 × 一批 AI 引擎 × 一个时间点。

    每次用户在前端点「开始监测」都会创建一个 Run;后台跑完后,所有
    MonitorResult.run_id 都指向这个 Run。前端的「对比视图」就是按
    run_id 把多个 Run 横向放在一起做矩阵/雷达图对比。
    """

    __tablename__ = "monitor_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    platforms: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MonitorResult(Base):
    __tablename__ = "monitor_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    # 新增:可空。旧数据迁移时 run_id 为 NULL;新写入必填
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitor_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    is_mentioned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_link: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    raw_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LLMCallLog(Base):
    """单次 LLM 调用的成本与 token 计量。

    监测环节仍可能调用 LLM (例如 mention 判定 / 情感分析),所以此表保留。
    历史 article_id 字段在重构后失去意义,由 migrate_drop_legacy.py 一并 DROP。
    """

    __tablename__ = "llm_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    purpose: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usd_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MonitorCitation(Base):
    """规范化 citation:MonitorResult.search_results 的展开,每条引用一行。

    Citation Source Analysis 报表(品类高频引用域名 / 竞品 GEO 资产清单)
    全部基于这张表做 SQL 聚合。client_id / platform 反范式化是为了避免
    跨大表 join。resolved_url / domain 由后台 worker 异步填充
    (resolve_status 标记进度)。supports_brand_mention 在写入时基于
    raw_answer 里 `[citation:N]` 标记和品牌出现位置的共现关系算出。
    """

    __tablename__ = "monitor_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monitor_result_id: Mapped[int] = mapped_column(
        ForeignKey("monitor_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    cite_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    resolved_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    supports_brand_mention: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    resolve_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    resolve_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )


class DiagnosisResult(Base):
    """Website GEO diagnosis report, keyed by (base_url, created_at)."""

    __tablename__ = "diagnosis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    page_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scores_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    checks_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    actions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
