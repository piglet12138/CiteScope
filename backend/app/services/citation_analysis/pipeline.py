"""Citation pipeline:把 MonitorResult.search_results 展开到 monitor_citations。

两个入口:
- ingest_citations_from_result(db, mr, brand_keywords) — 在 monitor run 写完
  一条 MonitorResult 之后立刻调,同事务里展平。普通域名直接抽 domain 标
  resolve_status='ok';platform internal (google maps placeholder) 标
  'skipped';redirect wrapper (Gemini vertexai) 留 'pending' 等后台 worker。

- resolve_pending_citations(db, batch_size=50) — apscheduler 定时跑,把所有
  pending 行送到 resolver,落 resolved_url + domain。
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import MonitorCitation, MonitorResult
from .normalizer import clean_url, extract_domain, is_platform_internal, is_redirect_wrapper
from .resolver import resolve_batch_sync
from .span_attribution import compute_supports_brand_mention

logger = logging.getLogger("geo.citation.pipeline")


def ingest_citations_from_result(
    db: Session,
    mr: MonitorResult,
    brand_keywords: Iterable[str],
) -> int:
    """展开一条 MonitorResult.search_results 到 monitor_citations。

    幂等:如果该 monitor_result_id 已经有 citations 了,先全删再重写
    (避免回填脚本反复跑导致重复行)。返回写入行数。
    """
    items = mr.search_results or []
    if not isinstance(items, list):
        return 0

    # 收集 cite_index 用来跑 supports_brand_mention 一次
    cite_indices: list[int] = []
    normalized_items: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        url = (it.get("url") or "").strip()
        if not url:
            continue
        try:
            ci = it.get("cite_index")
            ci = int(ci) if ci is not None else None
        except (ValueError, TypeError):
            ci = None
        if ci is not None:
            cite_indices.append(ci)
        normalized_items.append(
            {
                "cite_index": ci,
                "url": url,
                "title": (it.get("title") or "")[:500] or None,
                "snippet": it.get("snippet") or None,
            }
        )

    if not normalized_items:
        return 0

    supports = compute_supports_brand_mention(
        mr.raw_answer or "",
        list(brand_keywords),
        list({n for n in cite_indices if n is not None}),
    )

    # 幂等清空
    db.query(MonitorCitation).filter(
        MonitorCitation.monitor_result_id == mr.id
    ).delete(synchronize_session=False)

    rows: list[MonitorCitation] = []
    for it in normalized_items:
        url = it["url"]
        supports_flag = supports.get(it["cite_index"], False) if it["cite_index"] is not None else None

        if is_redirect_wrapper(url):
            # 需要后台 worker 跑 resolve
            status = "pending"
            resolved = None
            domain = None
        elif is_platform_internal(url):
            # 平台占位,不计入聚合
            status = "skipped"
            resolved = clean_url(url)
            domain = None
        else:
            # 直接抽 domain
            status = "ok"
            resolved = clean_url(url)
            domain = extract_domain(resolved)

        rows.append(
            MonitorCitation(
                monitor_result_id=mr.id,
                client_id=mr.client_id,
                platform=mr.platform,
                cite_index=it["cite_index"],
                raw_url=url[:2000],
                resolved_url=(resolved[:2000] if resolved else None),
                domain=domain,
                title=it["title"],
                snippet=it["snippet"],
                supports_brand_mention=supports_flag,
                resolve_status=status,
            )
        )

    db.add_all(rows)
    db.commit()
    return len(rows)


def resolve_pending_citations(
    db: Session,
    *,
    batch_size: int = 50,
    timeout: float = 10.0,
) -> dict[str, int]:
    """把 resolve_status='pending' 的 citation 跑 resolver,落 resolved_url + domain。

    返回 {"resolved": int, "failed": int, "remaining": int} 统计。
    """
    pending = list(
        db.execute(
            select(MonitorCitation)
            .where(MonitorCitation.resolve_status == "pending")
            .limit(batch_size)
        ).scalars()
    )
    if not pending:
        return {"resolved": 0, "failed": 0, "remaining": 0}

    raw_urls = [c.raw_url for c in pending]
    out = resolve_batch_sync(raw_urls, timeout=timeout)

    resolved_n = 0
    failed_n = 0
    for c in pending:
        resolved, err = out.get(c.raw_url, (None, "missing"))
        if err or not resolved:
            c.resolve_status = "failed"
            c.resolve_error = (err or "unknown")[:500]
            failed_n += 1
        else:
            c.resolved_url = resolved[:2000]
            c.domain = extract_domain(resolved)
            c.resolve_status = "ok"
            c.resolve_error = None
            resolved_n += 1
    db.commit()

    remaining = (
        db.query(MonitorCitation)
        .filter(MonitorCitation.resolve_status == "pending")
        .count()
    )
    logger.info(
        "citation.resolve: batch=%d ok=%d fail=%d remaining=%d",
        len(pending), resolved_n, failed_n, remaining,
    )
    return {"resolved": resolved_n, "failed": failed_n, "remaining": remaining}
