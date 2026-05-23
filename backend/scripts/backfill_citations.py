"""把历史 MonitorResult.search_results 展开到 monitor_citations。

幂等:对每条 MonitorResult,pipeline 内部会先 delete 现有 citations 再写入。
可以反复跑。

用法:
    cd backend && .venv/bin/python -m scripts.backfill_citations [--limit N] [--client-id ID] [--since YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from sqlalchemy import select

# 让 `.venv/bin/python -m scripts.backfill_citations` 在 backend/ 目录下能找到 app
sys.path.insert(0, ".")

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Client, MonitorResult  # noqa: E402
from app.services.citation_analysis.pipeline import ingest_citations_from_result  # noqa: E402


def _resolve_brand_keywords(client: Client) -> list[str]:
    """复用 m4_monitor.service 的逻辑(但避免引入 m4 包级依赖)。"""
    if not client:
        return []
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
    seen: set[str] = set()
    out: list[str] = []
    for k in kws:
        key = k.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(k)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 条")
    parser.add_argument("--client-id", type=int, default=None)
    parser.add_argument("--since", type=str, default=None, help="YYYY-MM-DD,只回填该日期之后的")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("backfill")

    init_db()  # 保险:确保 monitor_citations 表存在
    db = SessionLocal()
    try:
        stmt = select(MonitorResult).where(MonitorResult.search_results.is_not(None))
        if args.client_id is not None:
            stmt = stmt.where(MonitorResult.client_id == args.client_id)
        if args.since:
            since_dt = datetime.fromisoformat(args.since)
            stmt = stmt.where(MonitorResult.checked_at >= since_dt)
        stmt = stmt.order_by(MonitorResult.id.asc())
        if args.limit:
            stmt = stmt.limit(args.limit)

        mrs = list(db.execute(stmt).scalars())
        log.info("backfill candidates: %d MonitorResults", len(mrs))

        # 缓存 client → brand_keywords
        kw_cache: dict[int, list[str]] = {}

        total_citations = 0
        for i, mr in enumerate(mrs, 1):
            if mr.client_id not in kw_cache:
                c = db.get(Client, mr.client_id)
                kw_cache[mr.client_id] = _resolve_brand_keywords(c)
            try:
                n = ingest_citations_from_result(db, mr, kw_cache[mr.client_id])
            except Exception:  # noqa: BLE001
                log.exception("ingest failed mr=%s", mr.id)
                continue
            total_citations += n
            if i % 50 == 0 or i == len(mrs):
                log.info("  progress %d/%d (cumulative citations=%d)", i, len(mrs), total_citations)

        log.info("backfill done: %d MonitorResults → %d citations", len(mrs), total_citations)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
