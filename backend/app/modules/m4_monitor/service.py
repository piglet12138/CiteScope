"""M4 监测服务层。

- run_monitor: 对(question x platform)矩阵跑真实 AI 查询, 写入 monitor_results。
- compute_metrics: 简单聚合 (mention/first/link/sentiment), by_platform, trend。
- generate_report: 构造 markdown 摘要 + metrics 快照, 入库 reports。

🚧 防封号设计 (重要):
- DEFAULT_MAX_QUESTIONS: 默认一次最多查 5 个问题, 必须显式传 max_questions 才能突破
- DAILY_PLATFORM_LIMIT: 单平台每天硬上限 30 次, 超过的直接跳过 (用 SQLite COUNT 判断)
- INTER_QUERY_DELAY: 每次查询之间随机 sleep 8-20 秒, 模拟人类阅读间隔
- task_id 传入时, 每完成一个 (question, platform) 上报真实 progress
"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import Client, MonitorResult, MonitorRun, Question, Report
from ...services.citation_analysis.pipeline import ingest_citations_from_result
from ...services.llm_metering import metering_context, record_call
from ...services.playwright_client import get_playwright_client
from ...services.search_pricing import estimate_search_cost_usd
from ...services.task_store import task_store
from .schemas import (
    DEFAULT_PLATFORMS,
    MetricsOut,
    MonitorResultOut,
    PlatformBreakdown,
    ReportOut,
    RunCompareEntry,
    RunCompareOut,
    RunOut,
    RunPlatformCell,
    TrendPoint,
)

logger = logging.getLogger("geo.monitor")

# 防封号常量 — 不要轻易调高
DEFAULT_MAX_QUESTIONS = 5
HARD_MAX_QUESTIONS = 20  # 即使前端传更大也截断到这里
DAILY_PLATFORM_LIMIT = 30  # 单平台每天硬上限
MIN_DELAY_SEC = 8.0
MAX_DELAY_SEC = 20.0


class ClientNotFoundError(Exception):
    pass


def _resolve_brand_keywords(client: Client) -> list[str]:
    """从 Client 里抠出用于品牌提及判定的关键词列表.

    规则:
    - client.name 永远算一个 (例如 "鄂尔多斯羊绒衫")
    - business_info.keywords: 用户在客户资料里显式配置的别名/关键词
    - business_info.brand_aliases: 备选字段, 兼容旧资料
    去空、去重、保持原顺序.
    """
    kws: list[str] = []
    if client.name:
        kws.append(client.name.strip())
    try:
        bi = json.loads(client.business_info) if client.business_info else {}
    except (json.JSONDecodeError, TypeError):
        bi = {}
    for field in ("keywords", "brand_aliases", "aliases"):
        raw = bi.get(field)
        if isinstance(raw, list):
            kws.extend(str(k).strip() for k in raw if str(k).strip())
        elif isinstance(raw, str) and raw.strip():
            kws.append(raw.strip())
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for k in kws:
        key = k.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(k)
    return out


def _platform_used_today(db: Session, platform: str) -> int:
    """返回 platform 今天 (UTC 自然日) 已经发起的查询次数。"""
    today_start = datetime(
        datetime.utcnow().year, datetime.utcnow().month, datetime.utcnow().day
    )
    return int(
        db.execute(
            select(func.count())
            .select_from(MonitorResult)
            .where(
                MonitorResult.platform == platform,
                MonitorResult.checked_at >= today_start,
            )
        ).scalar_one()
    )


def run_monitor_sync(
    db: Session,
    client_id: int,
    *,
    question_ids: list[int] | None = None,
    platforms: list[str] | None = None,
    max_questions: int | None = None,
    extra_question_texts: list[str] | None = None,
    task_id: str | None = None,
    run_id: int | None = None,
) -> dict:
    client = db.get(Client, client_id)
    if not client:
        raise ClientNotFoundError(f"client {client_id} not found")

    run: MonitorRun | None = None
    if run_id is not None:
        run = db.get(MonitorRun, run_id)
        if run is None:
            logger.warning("monitor: run_id=%s 不存在,降级为无 run 模式", run_id)

    settings = get_settings()
    mock_mode = bool(settings.GEO_USE_MOCK)
    pw = get_playwright_client()
    platforms = list(platforms) if platforms else list(DEFAULT_PLATFORMS)
    brand_keywords = _resolve_brand_keywords(client)
    logger.info(
        "monitor: client=%s brand_keywords=%s", client.name, brand_keywords
    )

    user_picked = bool(question_ids) or bool(extra_question_texts)

    questions: list[Question] = []
    if question_ids:
        stmt = select(Question).where(
            Question.client_id == client_id, Question.id.in_(question_ids)
        )
        questions.extend(db.execute(stmt).scalars().all())

    # 临时提问: 写入 is_active=False 的 adhoc Question, 这样 MonitorResult
    # 的外键约束能满足, 同时不污染主问题库默认视图。
    if extra_question_texts:
        for text in extra_question_texts:
            t = (text or "").strip()
            if not t:
                continue
            adhoc = Question(
                client_id=client_id,
                text=t,
                category="adhoc",
                priority=0,
                is_active=False,
            )
            db.add(adhoc)
            db.flush()  # 拿到 id
            questions.append(adhoc)
        db.commit()

    if not user_picked:
        # 用户没选 → 取 active 库前 N 个 (按 priority 降序)
        stmt = (
            select(Question)
            .where(Question.client_id == client_id, Question.is_active == True)  # noqa: E712
            .order_by(Question.priority.desc(), Question.id.asc())
        )
        questions = list(db.execute(stmt).scalars().all())
        cap = max_questions if max_questions and max_questions > 0 else DEFAULT_MAX_QUESTIONS
        cap = min(cap, HARD_MAX_QUESTIONS)
        if len(questions) > cap:
            logger.info(
                "monitor: 截断问题数 %d → %d (防封号默认上限)", len(questions), cap
            )
            questions = questions[:cap]
    else:
        # 用户显式选了 (question_ids 或 extra_question_texts) → 不再 cap, 但仍受 HARD_MAX
        if len(questions) > HARD_MAX_QUESTIONS:
            logger.warning(
                "monitor: 用户选了 %d 个问题, 截断到硬上限 %d",
                len(questions),
                HARD_MAX_QUESTIONS,
            )
            questions = questions[:HARD_MAX_QUESTIONS]

    # 预先算每个平台的"今日剩余配额" (mock 模式不限额)
    quota: dict[str, int] = {}
    for p in platforms:
        if mock_mode:
            quota[p] = 10**9
            continue
        used = _platform_used_today(db, p)
        quota[p] = max(0, DAILY_PLATFORM_LIMIT - used)
        if quota[p] == 0:
            logger.warning(
                "monitor: %s 今日已用 %d/%d, 本轮跳过", p, used, DAILY_PLATFORM_LIMIT
            )

    total_steps = sum(min(len(questions), quota[p]) for p in platforms)
    if total_steps == 0:
        return {
            "checked": 0,
            "questions": len(questions),
            "platforms": platforms,
            "skipped_quota": True,
            "message": "所有平台今日配额已用完",
        }

    if task_id:
        task_store.update(task_id, progress=10)

    inserted = 0
    skipped_quota: list[str] = []
    errors: list[str] = []
    done = 0

    for q in questions:
        for platform in platforms:
            if quota[platform] <= 0:
                if platform not in skipped_quota:
                    skipped_quota.append(platform)
                continue

            t_start = time.time()
            try:
                with metering_context(client_id=client_id, purpose=f"search.{platform}"):
                    res = pw.query_ai_sync(platform, q.text, brand_keywords=brand_keywords)
            except Exception as e:  # noqa: BLE001
                # 单个查询失败不中断整批 (常见: 429 / 网络)
                logger.exception("monitor query failed: q=%s p=%s", q.id, platform)
                errors.append(f"q{q.id}/{platform}: {e}")
                # 失败也落一条 search-call 记录,用于统计失败率
                if not mock_mode:
                    with metering_context(client_id=client_id, purpose=f"search.{platform}"):
                        record_call(
                            provider=platform,
                            model="search",
                            prompt_tokens=0,
                            completion_tokens=0,
                            latency_ms=int((time.time() - t_start) * 1000),
                            status="error",
                            error=str(e),
                            usd_cost=0.0,
                        )
                done += 1
                if task_id:
                    task_store.update(
                        task_id, progress=10 + int(85 * done / total_steps)
                    )
                # 失败也吃间隔, 防止持续撞 429 (mock 模式跳过)
                if not mock_mode:
                    time.sleep(random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC))
                continue

            # 成功:从 res.usage 抽 token,按 platform 估算成本,落计量
            if not mock_mode:
                u = (res.get("usage") or {}) if isinstance(res, dict) else {}
                p_tok = int(u.get("prompt_tokens") or 0)
                c_tok = int(u.get("completion_tokens") or 0)
                model_name = str(u.get("model") or "search")
                cost = estimate_search_cost_usd(platform, p_tok, c_tok)
                with metering_context(client_id=client_id, purpose=f"search.{platform}"):
                    record_call(
                        provider=platform,
                        model=model_name,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        latency_ms=int((time.time() - t_start) * 1000),
                        status="ok",
                        usd_cost=cost,
                    )

            # 联网搜索型平台 (如 DeepSeek) 会返回结构化搜索来源列表
            search_results = res.get("search_results")
            if search_results is not None and not isinstance(search_results, list):
                search_results = None
            mr = MonitorResult(
                client_id=client_id,
                question_id=q.id,
                run_id=run.id if run else None,
                platform=platform,
                is_mentioned=bool(res.get("is_mentioned")),
                position=res.get("position"),
                has_link=bool(res.get("has_link")),
                sentiment=res.get("sentiment"),
                # 完整保留正文 (含 [citation:N] 标记), SQLite Text 没有硬上限
                raw_answer=res.get("raw_answer") or "",
                search_results=search_results,
                screenshot_path=res.get("screenshot_path"),
            )
            db.add(mr)
            db.commit()  # 立刻提交, 让前端轮询能看到增量

            # 同事务后把 citation 展开到 monitor_citations。失败不阻断主流程
            # (citation 是衍生数据,丢一两行不影响监测本身)。
            try:
                ingest_citations_from_result(db, mr, brand_keywords)
            except Exception:  # noqa: BLE001
                logger.exception("citation ingest failed mr=%s p=%s", mr.id, platform)

            inserted += 1
            quota[platform] -= 1
            done += 1
            if task_id:
                task_store.update(
                    task_id, progress=10 + int(85 * done / total_steps)
                )

            # 还有后续步骤就睡一下, 模拟人类阅读 (mock 模式跳过)
            if done < total_steps and not mock_mode:
                delay = random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)
                logger.debug("monitor sleep %.1fs (防封号)", delay)
                time.sleep(delay)

    if run is not None:
        run.status = "completed" if not errors else "completed_with_errors"
        run.finished_at = datetime.utcnow()
        run.question_count = len(questions)
        try:
            run.platforms = json.dumps(platforms, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            pass
        db.commit()

    return {
        "checked": inserted,
        "questions": len(questions),
        "platforms": platforms,
        "skipped_quota": skipped_quota or False,
        "errors": errors or None,
        "daily_limit": DAILY_PLATFORM_LIMIT,
        "run_id": run.id if run else None,
    }


# ---------- Run / 对比实验 ----------
def _platforms_to_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(x) for x in v]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def create_run(
    db: Session,
    client_id: int,
    *,
    name: str,
    note: str | None,
    platforms: list[str],
    question_count: int,
) -> MonitorRun:
    """新建一个 Run 记录,后台 job 跑完后会把 status / finished_at 写回。"""
    client = db.get(Client, client_id)
    if not client:
        raise ClientNotFoundError(f"client {client_id} not found")
    run = MonitorRun(
        client_id=client_id,
        name=name.strip()[:200],
        note=note,
        platforms=json.dumps(platforms, ensure_ascii=False),
        question_count=question_count,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _run_overview(
    db: Session, run: MonitorRun
) -> tuple[float, int]:
    """返回 (mention_rate, sample_size)。"""
    rows = (
        db.execute(
            select(MonitorResult.is_mentioned).where(MonitorResult.run_id == run.id)
        )
        .scalars()
        .all()
    )
    if not rows:
        return 0.0, 0
    mentioned = sum(1 for r in rows if r)
    return mentioned / len(rows), len(rows)


def _run_to_out(db: Session, run: MonitorRun) -> RunOut:
    rate, size = _run_overview(db, run)
    return RunOut(
        id=run.id,
        client_id=run.client_id,
        name=run.name,
        note=run.note,
        platforms=_platforms_to_list(run.platforms),
        question_count=run.question_count,
        status=run.status,
        created_at=run.created_at,
        finished_at=run.finished_at,
        mention_rate=round(rate, 4),
        sample_size=size,
    )


def list_runs(
    db: Session, client_id: int, *, page: int = 1, page_size: int = 20
) -> tuple[list[RunOut], int]:
    stmt = select(MonitorRun).where(MonitorRun.client_id == client_id)
    count_stmt = select(func.count()).select_from(MonitorRun).where(
        MonitorRun.client_id == client_id
    )
    total = db.execute(count_stmt).scalar_one()
    stmt = stmt.order_by(MonitorRun.id.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).scalars().all()
    return [_run_to_out(db, r) for r in rows], int(total)


def get_run(db: Session, run_id: int) -> RunOut:
    r = db.get(MonitorRun, run_id)
    if not r:
        raise ClientNotFoundError(f"run {run_id} not found")
    return _run_to_out(db, r)


def compare_runs(db: Session, run_ids: list[int]) -> RunCompareOut:
    """对比多个 Run。返回每个 run × platform 的 (mention/first/link) 矩阵。"""
    if not run_ids:
        return RunCompareOut(runs=[], platforms=[])
    rows = (
        db.execute(select(MonitorRun).where(MonitorRun.id.in_(run_ids)))
        .scalars()
        .all()
    )
    by_id = {r.id: r for r in rows}
    if not rows:
        return RunCompareOut(runs=[], platforms=[])

    results_by_run: dict[int, list[MonitorResult]] = {rid: [] for rid in by_id}
    for r in (
        db.execute(
            select(MonitorResult).where(MonitorResult.run_id.in_(list(by_id.keys())))
        )
        .scalars()
        .all()
    ):
        results_by_run.setdefault(r.run_id, []).append(r)

    # 联合 platform 集合(并集)用于矩阵列
    platform_union: list[str] = []
    seen: set[str] = set()
    for r_list in results_by_run.values():
        for x in r_list:
            if x.platform and x.platform not in seen:
                seen.add(x.platform)
                platform_union.append(x.platform)
    platform_union.sort()

    entries: list[RunCompareEntry] = []
    # 保持输入顺序
    for rid in run_ids:
        run = by_id.get(rid)
        if not run:
            continue
        items = results_by_run.get(rid, [])
        # overall
        if items:
            total = len(items)
            mentioned = sum(1 for x in items if x.is_mentioned)
            first = sum(1 for x in items if x.is_mentioned and x.position == 1)
            link = sum(1 for x in items if x.is_mentioned and x.has_link)
        else:
            total = mentioned = first = link = 0
        overall = RunPlatformCell(
            platform="ALL",
            mention_rate=round(mentioned / total, 4) if total else 0.0,
            first_mention_rate=round(first / total, 4) if total else 0.0,
            link_citation_rate=round(link / total, 4) if total else 0.0,
            sample_size=total,
        )
        # by platform
        by_plat: list[RunPlatformCell] = []
        grouped: dict[str, list[MonitorResult]] = {p: [] for p in platform_union}
        for x in items:
            grouped.setdefault(x.platform, []).append(x)
        for plat in platform_union:
            arr = grouped.get(plat, [])
            t = len(arr)
            m = sum(1 for x in arr if x.is_mentioned)
            f = sum(1 for x in arr if x.is_mentioned and x.position == 1)
            l = sum(1 for x in arr if x.is_mentioned and x.has_link)
            by_plat.append(
                RunPlatformCell(
                    platform=plat,
                    mention_rate=round(m / t, 4) if t else 0.0,
                    first_mention_rate=round(f / t, 4) if t else 0.0,
                    link_citation_rate=round(l / t, 4) if t else 0.0,
                    sample_size=t,
                )
            )
        entries.append(
            RunCompareEntry(
                run_id=run.id,
                run_name=run.name,
                created_at=run.created_at,
                overall=overall,
                by_platform=by_plat,
            )
        )
    return RunCompareOut(runs=entries, platforms=platform_union)


def _period_window(period: str) -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    if period == "today":
        start = datetime(now.year, now.month, now.day)
    elif period == "week":
        start = now - timedelta(days=7)
    else:  # month / default
        start = now - timedelta(days=30)
    return start, now


def compute_metrics(db: Session, client_id: int, period: str = "month") -> MetricsOut:
    client = db.get(Client, client_id)
    if not client:
        raise ClientNotFoundError(f"client {client_id} not found")

    start, end = _period_window(period)
    rows = (
        db.execute(
            select(MonitorResult).where(
                MonitorResult.client_id == client_id,
                MonitorResult.checked_at >= start,
                MonitorResult.checked_at <= end,
            )
        )
        .scalars()
        .all()
    )

    total = len(rows)
    if total == 0:
        return MetricsOut(client_id=client_id, period=period)

    mentioned = [r for r in rows if r.is_mentioned]
    first_mentions = [r for r in mentioned if r.position == 1]
    with_link = [r for r in mentioned if r.has_link]
    # sentiment_accuracy: 把 positive 视为"准确" 的占比(简化)
    positive = [r for r in mentioned if r.sentiment == "positive"]

    mention_rate = len(mentioned) / total
    first_mention_rate = len(first_mentions) / total
    link_citation_rate = len(with_link) / total
    sentiment_accuracy = (len(positive) / len(mentioned)) if mentioned else 0.0

    # by_platform
    platforms: dict[str, list[MonitorResult]] = {}
    for r in rows:
        platforms.setdefault(r.platform, []).append(r)
    by_platform = [
        PlatformBreakdown(
            platform=plat,
            mention_rate=(sum(1 for x in items if x.is_mentioned) / len(items)) if items else 0.0,
            sample_size=len(items),
        )
        for plat, items in sorted(platforms.items())
    ]

    # trend: 按天聚合
    by_day: dict[str, list[bool]] = {}
    for r in rows:
        d = r.checked_at.strftime("%Y-%m-%d")
        by_day.setdefault(d, []).append(r.is_mentioned)
    trend = [
        TrendPoint(
            date=d,
            mention_rate=(sum(1 for x in flags if x) / len(flags)) if flags else 0.0,
        )
        for d, flags in sorted(by_day.items())
    ]

    return MetricsOut(
        client_id=client_id,
        period=period,
        mention_rate=round(mention_rate, 4),
        first_mention_rate=round(first_mention_rate, 4),
        link_citation_rate=round(link_citation_rate, 4),
        sentiment_accuracy=round(sentiment_accuracy, 4),
        trend=trend,
        by_platform=by_platform,
    )


def list_monitor_results(
    db: Session,
    client_id: int,
    *,
    question_id: int | None = None,
    platform: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[MonitorResultOut], int]:
    stmt = select(MonitorResult).where(MonitorResult.client_id == client_id)
    count_stmt = select(func.count()).select_from(MonitorResult).where(
        MonitorResult.client_id == client_id
    )
    if question_id is not None:
        stmt = stmt.where(MonitorResult.question_id == question_id)
        count_stmt = count_stmt.where(MonitorResult.question_id == question_id)
    if platform:
        stmt = stmt.where(MonitorResult.platform == platform)
        count_stmt = count_stmt.where(MonitorResult.platform == platform)
    total = db.execute(count_stmt).scalar_one()
    stmt = stmt.order_by(MonitorResult.id.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).scalars().all()
    out = [
        MonitorResultOut(
            id=r.id,
            client_id=r.client_id,
            question_id=r.question_id,
            run_id=r.run_id,
            platform=r.platform,
            is_mentioned=r.is_mentioned,
            position=r.position,
            has_link=r.has_link,
            sentiment=r.sentiment,
            raw_answer=r.raw_answer,
            search_results=r.search_results,
            screenshot_path=r.screenshot_path,
            checked_at=r.checked_at,
        )
        for r in rows
    ]
    return out, int(total)


def generate_report(
    db: Session, client_id: int, period_start: date, period_end: date
) -> ReportOut:
    client = db.get(Client, client_id)
    if not client:
        raise ClientNotFoundError(f"client {client_id} not found")

    metrics = compute_metrics(db, client_id, "month")

    summary_lines = [
        f"# {client.name} 月度 GEO 监测报告",
        f"周期: {period_start} ~ {period_end}",
        "",
        f"- 提及率: {metrics.mention_rate * 100:.1f}%",
        f"- 首位提及率: {metrics.first_mention_rate * 100:.1f}%",
        f"- 链接引用率: {metrics.link_citation_rate * 100:.1f}%",
        f"- 情感准确性: {metrics.sentiment_accuracy * 100:.1f}%",
        "",
        "## 平台分布",
    ]
    for bp in metrics.by_platform:
        summary_lines.append(
            f"- {bp.platform}: 提及率 {bp.mention_rate * 100:.1f}% (样本 {bp.sample_size})"
        )
    summary = "\n".join(summary_lines)

    snapshot_json = metrics.model_dump()
    report = Report(
        client_id=client_id,
        period_start=period_start,
        period_end=period_end,
        summary=summary,
        metrics_snapshot=json.dumps(snapshot_json, ensure_ascii=False, default=str),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _report_to_out(report)


def _report_to_out(r: Report) -> ReportOut:
    try:
        snap = json.loads(r.metrics_snapshot) if r.metrics_snapshot else {}
    except json.JSONDecodeError:
        snap = {}
    return ReportOut(
        id=r.id,
        client_id=r.client_id,
        period_start=r.period_start,
        period_end=r.period_end,
        summary=r.summary,
        metrics_snapshot=snap,
        created_at=r.created_at,
    )


def list_reports(
    db: Session, client_id: int, *, page: int = 1, page_size: int = 20
) -> tuple[list[ReportOut], int]:
    stmt = select(Report).where(Report.client_id == client_id)
    count_stmt = select(func.count()).select_from(Report).where(Report.client_id == client_id)
    total = db.execute(count_stmt).scalar_one()
    stmt = stmt.order_by(Report.id.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).scalars().all()
    return [_report_to_out(r) for r in rows], int(total)


def get_report(db: Session, report_id: int) -> ReportOut:
    r = db.get(Report, report_id)
    if not r:
        raise ClientNotFoundError(f"report {report_id} not found")
    return _report_to_out(r)
