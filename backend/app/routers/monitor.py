"""监测路由 (M4)。

旧 POST /clients/{cid}/monitor 端点保留以兼容历史前端,但内部已经强制
创建一个匿名 Run,新代码请直接走 POST /clients/{cid}/runs。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..modules.m4_monitor import service as svc
from ..modules.m4_monitor.schemas import (
    MonitorBody,
    ReportCreateBody,
    RunCreateBody,
)
from ..modules.m5_clients.service import ClientNotFoundError, get_client_or_raise
from ..schemas import err, ok
from ..services.scheduler import scheduler
from ..services.task_store import task_store
from ..tasks.jobs import run_monitor

router = APIRouter()


def _schedule_run(
    *,
    task_id: str,
    client_id: int,
    question_ids: list[int] | None,
    platforms: list[str] | None,
    max_questions: int | None,
    extra_question_texts: list[str] | None,
    run_id: int | None,
) -> None:
    scheduler.add_job(
        run_monitor,
        "date",
        run_date=datetime.utcnow(),
        kwargs={
            "task_id": task_id,
            "client_id": client_id,
            "question_ids": question_ids,
            "platforms": platforms,
            "max_questions": max_questions,
            "extra_question_texts": extra_question_texts,
            "run_id": run_id,
        },
        misfire_grace_time=60,
    )


# ---------- 新版:对比实验 (Run) ----------
@router.post("/clients/{client_id}/runs")
def create_run(
    client_id: int,
    body: RunCreateBody,
    db: Session = Depends(get_db),
) -> dict:
    try:
        get_client_or_raise(db, client_id)
    except ClientNotFoundError as e:
        return err(1002, str(e))

    platforms = body.platforms or []
    # 题数预估: 显式 question_ids + extra_question_texts;未显式时由后端 cap
    q_count = (len(body.question_ids) if body.question_ids else 0) + (
        len(body.extra_question_texts) if body.extra_question_texts else 0
    )

    try:
        run = svc.create_run(
            db,
            client_id,
            name=body.name,
            note=body.note,
            platforms=platforms,
            question_count=q_count,
        )
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))

    task_id = task_store.create("monitor", client_id=client_id)
    _schedule_run(
        task_id=task_id,
        client_id=client_id,
        question_ids=body.question_ids,
        platforms=body.platforms,
        max_questions=body.max_questions,
        extra_question_texts=body.extra_question_texts,
        run_id=run.id,
    )
    return ok({"task_id": task_id, "run_id": run.id, "status": "queued"})


@router.get("/clients/{client_id}/runs")
def list_runs(
    client_id: int,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
) -> dict:
    try:
        get_client_or_raise(db, client_id)
    except ClientNotFoundError as e:
        return err(1002, str(e))
    items, total = svc.list_runs(db, client_id, page=page, page_size=page_size)
    return ok(
        {
            "items": [r.model_dump(mode="json") for r in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/runs/compare")
def compare_runs(
    ids: str = Query(..., description="逗号分隔的 run_id 列表"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        run_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        return err(1001, f"非法 ids 参数: {ids}")
    if not run_ids:
        return err(1001, "至少指定一个 run_id")
    out = svc.compare_runs(db, run_ids)
    return ok(out.model_dump(mode="json"))


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        r = svc.get_run(db, run_id)
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))
    return ok(r.model_dump(mode="json"))


# ---------- 兼容旧路由 ----------
@router.post("/clients/{client_id}/monitor")
def trigger_monitor(
    client_id: int,
    body: MonitorBody | None = None,
    db: Session = Depends(get_db),
) -> dict:
    try:
        get_client_or_raise(db, client_id)
    except ClientNotFoundError as e:
        return err(1002, str(e))
    body = body or MonitorBody()
    # 兼容路径:也强制创建一个 Run (匿名), 避免数据进库没有 run_id
    auto_name = f"adhoc-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    try:
        run = svc.create_run(
            db,
            client_id,
            name=auto_name,
            note="legacy POST /monitor",
            platforms=body.platforms or [],
            question_count=(len(body.question_ids) if body.question_ids else 0)
            + (len(body.extra_question_texts) if body.extra_question_texts else 0),
        )
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))
    task_id = task_store.create("monitor", client_id=client_id)
    _schedule_run(
        task_id=task_id,
        client_id=client_id,
        question_ids=body.question_ids,
        platforms=body.platforms,
        max_questions=body.max_questions,
        extra_question_texts=body.extra_question_texts,
        run_id=run.id,
    )
    return ok({"task_id": task_id, "run_id": run.id, "status": "queued"})


# ---------- 指标 / 结果 / 报告 (沿用) ----------
@router.get("/clients/{client_id}/metrics")
def get_metrics(
    client_id: int, period: str = "month", db: Session = Depends(get_db)
) -> dict:
    if period not in ("today", "week", "month"):
        return err(1001, f"invalid period {period}; expected today/week/month")
    try:
        metrics = svc.compute_metrics(db, client_id, period)
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))
    return ok(metrics.model_dump(mode="json"))


@router.get("/clients/{client_id}/monitor-results")
def list_monitor_results(
    client_id: int,
    question_id: int | None = None,
    platform: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
) -> dict:
    items, total = svc.list_monitor_results(
        db,
        client_id,
        question_id=question_id,
        platform=platform,
        page=page,
        page_size=page_size,
    )
    return ok(
        {
            "items": [m.model_dump(mode="json") for m in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/clients/{client_id}/reports")
def list_reports(
    client_id: int,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
) -> dict:
    items, total = svc.list_reports(db, client_id, page=page, page_size=page_size)
    return ok(
        {
            "items": [r.model_dump(mode="json") for r in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/clients/{client_id}/reports")
def create_report(
    client_id: int, body: ReportCreateBody, db: Session = Depends(get_db)
) -> dict:
    try:
        get_client_or_raise(db, client_id)
    except ClientNotFoundError as e:
        return err(1002, str(e))
    try:
        report = svc.generate_report(db, client_id, body.period_start, body.period_end)
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))
    return ok(report.model_dump(mode="json"))


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        r = svc.get_report(db, report_id)
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))
    return ok(r.model_dump(mode="json"))
