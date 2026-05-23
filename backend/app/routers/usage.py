"""LLM 调用成本与用量查询 (M-cost)。

接口:
  GET /api/usage/summary?period=day|week|month|all&client_id=...
    → 全量聚合 (按 provider/model/purpose) + 总成本/总 token

  GET /api/usage/calls?client_id=...&limit=50
    → 最近 N 条调用明细 (用于排查具体哪步贵了)

  GET /api/usage/by-client
    → 各客户的累计成本排行 (运营视角)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Client, LLMCallLog
from ..schemas import ok

router = APIRouter()


def _period_start(period: str) -> datetime | None:
    now = datetime.utcnow()
    if period == "day":
        return now - timedelta(days=1)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    return None  # all


@router.get("/usage/summary")
def usage_summary(
    period: str = Query("month", pattern="^(day|week|month|all)$"),
    client_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """聚合视图: 按 provider / model / purpose 分组的 token 与成本。"""
    base_filters = []
    start = _period_start(period)
    if start is not None:
        base_filters.append(LLMCallLog.created_at >= start)
    if client_id is not None:
        base_filters.append(LLMCallLog.client_id == client_id)

    # 总览
    total_stmt = (
        select(
            func.count().label("calls"),
            func.coalesce(func.sum(LLMCallLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LLMCallLog.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(LLMCallLog.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(LLMCallLog.usd_cost), 0.0).label("usd_cost"),
            func.coalesce(func.avg(LLMCallLog.latency_ms), 0).label("avg_latency_ms"),
            func.coalesce(
                func.sum(case((LLMCallLog.status == "error", 1), else_=0)),
                0,
            ).label("error_calls"),
        )
        .where(*base_filters)
    )
    total_row = db.execute(total_stmt).one()._mapping

    # 按 provider/model
    by_model_stmt = (
        select(
            LLMCallLog.provider,
            LLMCallLog.model,
            func.count().label("calls"),
            func.coalesce(func.sum(LLMCallLog.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(LLMCallLog.usd_cost), 0.0).label("usd_cost"),
        )
        .where(*base_filters)
        .group_by(LLMCallLog.provider, LLMCallLog.model)
        .order_by(desc("usd_cost"))
    )
    by_model = [dict(r._mapping) for r in db.execute(by_model_stmt)]

    # 按 purpose
    by_purpose_stmt = (
        select(
            LLMCallLog.purpose,
            func.count().label("calls"),
            func.coalesce(func.sum(LLMCallLog.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(LLMCallLog.usd_cost), 0.0).label("usd_cost"),
        )
        .where(*base_filters)
        .group_by(LLMCallLog.purpose)
        .order_by(desc("usd_cost"))
    )
    by_purpose = [dict(r._mapping) for r in db.execute(by_purpose_stmt)]

    return ok(
        {
            "period": period,
            "client_id": client_id,
            "total": {
                "calls": int(total_row["calls"] or 0),
                "prompt_tokens": int(total_row["prompt_tokens"] or 0),
                "completion_tokens": int(total_row["completion_tokens"] or 0),
                "total_tokens": int(total_row["total_tokens"] or 0),
                "usd_cost": round(float(total_row["usd_cost"] or 0), 6),
                "avg_latency_ms": int(total_row["avg_latency_ms"] or 0),
                "error_calls": int(total_row["error_calls"] or 0),
            },
            "by_model": by_model,
            "by_purpose": by_purpose,
        }
    )


@router.get("/usage/calls")
def usage_calls(
    client_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """最近 N 条 LLM 调用明细 (倒序)。"""
    stmt = select(LLMCallLog).order_by(desc(LLMCallLog.id)).limit(limit)
    if client_id is not None:
        stmt = (
            select(LLMCallLog)
            .where(LLMCallLog.client_id == client_id)
            .order_by(desc(LLMCallLog.id))
            .limit(limit)
        )
    rows = db.execute(stmt).scalars().all()
    items = [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "client_id": r.client_id,
            "purpose": r.purpose,
            "provider": r.provider,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
            "usd_cost": round(r.usd_cost, 6),
            "latency_ms": r.latency_ms,
            "status": r.status,
            "error": r.error,
        }
        for r in rows
    ]
    return ok({"items": items})


@router.get("/usage/by-client")
def usage_by_client(
    period: str = Query("month", pattern="^(day|week|month|all)$"),
    db: Session = Depends(get_db),
) -> dict:
    """各客户的成本排行 (运营视角)。"""
    filters = []
    start = _period_start(period)
    if start is not None:
        filters.append(LLMCallLog.created_at >= start)

    stmt = (
        select(
            LLMCallLog.client_id,
            Client.name,
            Client.plan,
            func.count().label("calls"),
            func.coalesce(func.sum(LLMCallLog.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(LLMCallLog.usd_cost), 0.0).label("usd_cost"),
        )
        .join(Client, Client.id == LLMCallLog.client_id, isouter=True)
        .where(*filters)
        .group_by(LLMCallLog.client_id, Client.name, Client.plan)
        .order_by(desc("usd_cost"))
    )
    items = []
    for r in db.execute(stmt):
        m = r._mapping
        items.append(
            {
                "client_id": m["client_id"],
                "client_name": m["name"] or "(未知/已删除)",
                "plan": m["plan"] or "-",
                "calls": int(m["calls"] or 0),
                "total_tokens": int(m["total_tokens"] or 0),
                "usd_cost": round(float(m["usd_cost"] or 0), 6),
            }
        )
    return ok({"period": period, "items": items})
