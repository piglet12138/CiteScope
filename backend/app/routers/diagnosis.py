"""Website GEO diagnosis API endpoints."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DiagnosisResult
from ..modules.m7_diagnosis.schemas import (
    DiagnosisRequest,
    GenerateSchemaRequest,
    GenerateLlmsTxtRequest,
)
from ..modules.m7_diagnosis.service import run_diagnosis
from ..modules.m7_diagnosis.generator import generate_schema, generate_llms_txt
from ..schemas import ok, err

logger = logging.getLogger("geo.router.diagnosis")

router = APIRouter()


@router.post("/diagnosis/run")
async def run_diagnosis_endpoint(
    req: DiagnosisRequest,
    db: Session = Depends(get_db),
):
    """Run a full GEO diagnosis on a website URL, save result to DB."""
    url = req.url.strip()
    if not url:
        return err(400, "URL is required")

    try:
        result = await asyncio.to_thread(run_diagnosis, url)
    except Exception as e:
        logger.exception("Diagnosis failed for %s", url)
        return err(500, f"Diagnosis failed: {e}")

    # Persist to DB
    try:
        record = DiagnosisResult(
            base_url=result.get("base_url", url),
            page_url=result.get("url", url),
            client_id=req.client_id,
            overall_score=result.get("overall_score", 0),
            scores_json=json.dumps(result.get("scores", {}), ensure_ascii=False),
            checks_json=json.dumps(result.get("checks", {}), ensure_ascii=False),
            actions_json=json.dumps(result.get("action_items", []), ensure_ascii=False),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        result["id"] = record.id
        result["saved_at"] = record.created_at.isoformat() if record.created_at else None
    except Exception as e:
        logger.warning("Failed to persist diagnosis result: %s", e)
        db.rollback()

    return ok(result)


@router.get("/diagnosis/history")
def list_diagnosis_history(
    base_url: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """List saved diagnosis reports. Optionally filter by base_url."""
    query = select(DiagnosisResult).order_by(DiagnosisResult.created_at.desc())
    count_query = select(func.count(DiagnosisResult.id))

    if base_url:
        base_url = base_url.strip().rstrip("/")
        query = query.where(DiagnosisResult.base_url == base_url)
        count_query = count_query.where(DiagnosisResult.base_url == base_url)

    total = db.execute(count_query).scalar() or 0
    rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).scalars().all()

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "base_url": r.base_url,
            "page_url": r.page_url,
            "client_id": r.client_id,
            "overall_score": r.overall_score,
            "scores": json.loads(r.scores_json) if r.scores_json else {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/diagnosis/{diagnosis_id}")
def get_diagnosis_detail(
    diagnosis_id: int,
    db: Session = Depends(get_db),
):
    """Get full diagnosis report by ID."""
    r = db.get(DiagnosisResult, diagnosis_id)
    if not r:
        return err(404, "Diagnosis report not found")

    return ok({
        "id": r.id,
        "base_url": r.base_url,
        "page_url": r.page_url,
        "url": r.page_url,
        "client_id": r.client_id,
        "overall_score": r.overall_score,
        "scores": json.loads(r.scores_json) if r.scores_json else {},
        "checks": json.loads(r.checks_json) if r.checks_json else {},
        "action_items": json.loads(r.actions_json) if r.actions_json else [],
        "timestamp": r.created_at.isoformat() if r.created_at else None,
    })


@router.get("/diagnosis/sites")
def list_diagnosed_sites(db: Session = Depends(get_db)):
    """List all unique sites that have been diagnosed, with latest score and count."""
    rows = db.execute(
        select(
            DiagnosisResult.base_url,
            func.count(DiagnosisResult.id).label("scan_count"),
            func.max(DiagnosisResult.overall_score).label("best_score"),
            func.max(DiagnosisResult.created_at).label("last_scan"),
        )
        .group_by(DiagnosisResult.base_url)
        .order_by(func.max(DiagnosisResult.created_at).desc())
    ).all()

    items = [
        {
            "base_url": r.base_url,
            "scan_count": r.scan_count,
            "best_score": r.best_score,
            "last_scan": r.last_scan.isoformat() if r.last_scan else None,
        }
        for r in rows
    ]
    return ok(items)


# ---------------------------------------------------------------------------
# GEO Asset Generators
# ---------------------------------------------------------------------------


@router.post("/diagnosis/generate/schema")
async def generate_schema_endpoint(req: GenerateSchemaRequest):
    """Auto-generate Schema JSON-LD for a website URL."""
    url = req.url.strip()
    if not url:
        return err(400, "URL is required")

    try:
        result = await asyncio.to_thread(generate_schema, url)
    except Exception as e:
        logger.exception("Schema generation failed for %s", url)
        return err(500, f"Schema generation failed: {e}")

    return ok(result)


@router.post("/diagnosis/generate/llms-txt")
async def generate_llms_txt_endpoint(req: GenerateLlmsTxtRequest):
    """Auto-generate llms.txt for a website URL."""
    url = req.url.strip()
    if not url:
        return err(400, "URL is required")

    try:
        result = await asyncio.to_thread(
            generate_llms_txt,
            url,
            company_name=req.company_name,
            description=req.description,
            services=req.services,
        )
    except Exception as e:
        logger.exception("llms.txt generation failed for %s", url)
        return err(500, f"llms.txt generation failed: {e}")

    return ok(result)
