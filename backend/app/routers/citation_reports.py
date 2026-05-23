"""Citation Source Analysis 报表路由。

两份报表:
- GET /clients/{client_id}/citation-reports/top-domains
    品类引用域名 Top N。基于 client 在选定时间窗里所有 monitor_citations
    (status='ok'),按 domain 聚合,返回出现次数 + 跨平台数 + 支撑品牌提及的
    citation 数。用来回答"AI 在我这个品类最爱引用哪些站,内容铺过去最划算"。

- GET /clients/{client_id}/citation-reports/competitor-assets
    竞品 GEO 资产清单。给定 competitor 名字列表,找出所有 raw_answer 里
    提到该竞品的 MonitorResult,统计 AI 给这些 answer 引用的域名/URL,从
    AI 输出端反推竞品的"AI 弹药库"。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import MonitorCitation, MonitorResult
from ..schemas import ok

router = APIRouter()


def _period_start(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=max(1, days))


@router.get("/clients/{client_id}/citation-reports/top-domains")
def top_domains(
    client_id: int,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(30, ge=1, le=200),
    platforms: str | None = Query(None, description="逗号分隔过滤,如 'chatgpt,perplexity'"),
    db: Session = Depends(get_db),
) -> dict:
    """Report A:品类引用域名 Top N。"""
    start = _period_start(days)
    plats = [p.strip() for p in platforms.split(",")] if platforms else None

    where = [
        MonitorCitation.client_id == client_id,
        MonitorCitation.resolve_status == "ok",
        MonitorCitation.domain.is_not(None),
        MonitorCitation.created_at >= start,
    ]
    if plats:
        where.append(MonitorCitation.platform.in_(plats))

    # SQLite: BOOLEAN 列存 0/1,SUM 即可统计 True 数
    rows = db.execute(
        select(
            MonitorCitation.domain,
            func.count(MonitorCitation.id).label("appearances"),
            func.count(func.distinct(MonitorCitation.platform)).label("platforms_count"),
            func.sum(
                func.coalesce(MonitorCitation.supports_brand_mention, 0)
            ).label("supports_brand_count"),
        )
        .where(and_(*where))
        .group_by(MonitorCitation.domain)
        .order_by(func.count(MonitorCitation.id).desc())
        .limit(limit)
    ).all()

    items = [
        {
            "domain": d,
            "appearances": int(a),
            "platforms_count": int(p),
            "supports_brand_count": int(s or 0),
        }
        for d, a, p, s in rows
    ]
    return ok(
        {
            "client_id": client_id,
            "period_days": days,
            "platforms_filter": plats,
            "limit": limit,
            "items": items,
        }
    )


@router.get("/clients/{client_id}/citation-reports/competitor-assets")
def competitor_assets(
    client_id: int,
    competitors: str = Query(..., description="逗号分隔,如 'Biorun,CJ Socks,MeetSocks'"),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    platforms: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    """Report B:竞品 GEO 资产清单。

    对每个 competitor,找 raw_answer 包含该竞品名的 MonitorResult,统计这些
    answer 引用了哪些域名/URL。返回 per-competitor 一份清单。
    """
    comp_list = [c.strip() for c in competitors.split(",") if c.strip()]
    if not comp_list:
        return ok({"items": [], "competitors": []})

    plats = [p.strip() for p in platforms.split(",")] if platforms else None
    start = _period_start(days)

    results: list[dict] = []
    for comp in comp_list:
        like = f"%{comp}%"
        where = [
            MonitorCitation.client_id == client_id,
            MonitorCitation.resolve_status == "ok",
            MonitorCitation.domain.is_not(None),
            MonitorCitation.created_at >= start,
            # 联接 monitor_results 做 raw_answer LIKE
            MonitorResult.id == MonitorCitation.monitor_result_id,
            func.lower(MonitorResult.raw_answer).like(like.lower()),
        ]
        if plats:
            where.append(MonitorCitation.platform.in_(plats))

        rows = db.execute(
            select(
                MonitorCitation.domain,
                func.count(MonitorCitation.id).label("cited_times"),
                func.max(MonitorCitation.resolved_url).label("sample_url"),
                func.max(MonitorCitation.title).label("sample_title"),
            )
            .where(and_(*where))
            .group_by(MonitorCitation.domain)
            .order_by(func.count(MonitorCitation.id).desc())
            .limit(limit)
        ).all()

        results.append(
            {
                "competitor": comp,
                "items": [
                    {
                        "domain": d,
                        "cited_times": int(n),
                        "sample_url": url,
                        "sample_title": title,
                    }
                    for d, n, url, title in rows
                ],
            }
        )

    return ok(
        {
            "client_id": client_id,
            "period_days": days,
            "platforms_filter": plats,
            "limit": limit,
            "competitors": comp_list,
            "results": results,
        }
    )


@router.get("/clients/{client_id}/citation-reports/stats")
def stats(
    client_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """快速概览:用于前端显示"已分析 X 条 citation"等。"""
    base = db.query(MonitorCitation).filter(MonitorCitation.client_id == client_id)
    total = base.count()
    by_status = dict(
        db.execute(
            select(MonitorCitation.resolve_status, func.count(MonitorCitation.id))
            .where(MonitorCitation.client_id == client_id)
            .group_by(MonitorCitation.resolve_status)
        ).all()
    )
    by_platform = dict(
        db.execute(
            select(MonitorCitation.platform, func.count(MonitorCitation.id))
            .where(MonitorCitation.client_id == client_id)
            .group_by(MonitorCitation.platform)
        ).all()
    )
    unique_domains = (
        db.query(func.count(func.distinct(MonitorCitation.domain)))
        .filter(
            MonitorCitation.client_id == client_id,
            MonitorCitation.resolve_status == "ok",
            MonitorCitation.domain.is_not(None),
        )
        .scalar()
    )
    return ok(
        {
            "client_id": client_id,
            "total_citations": int(total),
            "by_status": {k: int(v) for k, v in by_status.items()},
            "by_platform": {k: int(v) for k, v in by_platform.items()},
            "unique_domains": int(unique_domains or 0),
        }
    )
