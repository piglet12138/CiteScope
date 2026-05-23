"""探针题库路由。

重构后纯手工 CRUD,不再依赖 LLM 自动生成。
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Client, Question
from ..modules.m5_clients.service import ClientNotFoundError, get_client_or_raise
from ..schemas import err, ok

logger = logging.getLogger("geo.routers.questions")
router = APIRouter()


# --------- Schemas ---------
VALID_CATEGORIES = {"recommend", "compare", "price", "review", "other"}


class QuestionItem(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    category: str = "other"
    priority: int = Field(5, ge=1, le=10)
    language: str = "zh"


class QuestionsCreateBody(BaseModel):
    items: list[QuestionItem]


class QuestionUpdateBody(BaseModel):
    text: str | None = None
    category: str | None = None
    priority: int | None = Field(None, ge=1, le=10)
    is_active: bool | None = None
    language: str | None = None


def _serialize(q: Question) -> dict[str, Any]:
    return {
        "id": q.id,
        "client_id": q.client_id,
        "text": q.text,
        "category": q.category,
        "priority": q.priority,
        "is_active": q.is_active,
        "language": q.language,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


def _normalize_category(c: str | None) -> str:
    if not c:
        return "other"
    c = c.strip().lower()
    return c if c in VALID_CATEGORIES else "other"


# --------- 列表 ---------
@router.get("/clients/{client_id}/questions")
def list_questions(
    client_id: int,
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    try:
        get_client_or_raise(db, client_id)
    except ClientNotFoundError as e:
        return err(1002, str(e))

    stmt = select(Question).where(Question.client_id == client_id)
    if category:
        stmt = stmt.where(Question.category == category)
    stmt = stmt.order_by(Question.priority.desc(), Question.id.desc())
    total = db.execute(
        select(Question.id).where(Question.client_id == client_id)
        if not category
        else select(Question.id).where(
            Question.client_id == client_id, Question.category == category
        )
    ).all()
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return ok(
        {
            "items": [_serialize(q) for q in items],
            "total": len(total),
            "page": page,
            "page_size": page_size,
        }
    )


# --------- 单条 / 批量录入 ---------
@router.post("/clients/{client_id}/questions")
def create_questions(
    client_id: int,
    body: QuestionsCreateBody,
    db: Session = Depends(get_db),
) -> dict:
    """批量录入题目。同一客户下 text 去重。"""
    try:
        get_client_or_raise(db, client_id)
    except ClientNotFoundError as e:
        return err(1002, str(e))

    existing = {
        t for (t,) in db.execute(
            select(Question.text).where(Question.client_id == client_id)
        ).all()
    }

    created = 0
    skipped = 0
    for item in body.items:
        text = item.text.strip()
        if not text or text in existing:
            skipped += 1
            continue
        q = Question(
            client_id=client_id,
            text=text,
            category=_normalize_category(item.category),
            priority=item.priority,
            language=item.language or "zh",
            is_active=True,
        )
        db.add(q)
        existing.add(text)
        created += 1
    db.commit()
    return ok({"created": created, "skipped": skipped})


# --------- CSV 导入 ---------
@router.post("/clients/{client_id}/questions/import-csv")
async def import_questions_csv(
    client_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """CSV 导入。列: text(必填), category, priority, language。

    宽容处理: 自动跳过空行、注释行 (#开头),重复 text 也跳过。
    """
    try:
        get_client_or_raise(db, client_id)
    except ClientNotFoundError as e:
        return err(1002, str(e))

    raw = await file.read()
    try:
        text_buf = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text_buf = raw.decode("gbk", errors="replace")
    reader = csv.DictReader(io.StringIO(text_buf))

    existing = {
        t for (t,) in db.execute(
            select(Question.text).where(Question.client_id == client_id)
        ).all()
    }

    created = 0
    skipped = 0
    errors: list[str] = []
    for idx, row in enumerate(reader, start=2):  # row 1 is header
        text = (row.get("text") or "").strip()
        if not text or text.startswith("#"):
            skipped += 1
            continue
        if text in existing:
            skipped += 1
            continue
        try:
            priority = int(row.get("priority") or 5)
        except (TypeError, ValueError):
            priority = 5
        priority = max(1, min(10, priority))
        q = Question(
            client_id=client_id,
            text=text,
            category=_normalize_category(row.get("category")),
            priority=priority,
            language=(row.get("language") or "zh").strip() or "zh",
            is_active=True,
        )
        db.add(q)
        existing.add(text)
        created += 1
        if len(errors) > 20:
            break
    db.commit()
    return ok({"created": created, "skipped": skipped, "errors": errors})


# --------- 单条更新 / 删除 ---------
@router.put("/questions/{question_id}")
def update_question(
    question_id: int, body: QuestionUpdateBody, db: Session = Depends(get_db)
) -> dict:
    q = db.get(Question, question_id)
    if not q:
        return err(1002, f"question {question_id} not found")
    if body.text is not None:
        q.text = body.text.strip()
    if body.category is not None:
        q.category = _normalize_category(body.category)
    if body.priority is not None:
        q.priority = body.priority
    if body.is_active is not None:
        q.is_active = body.is_active
    if body.language is not None:
        q.language = body.language
    db.commit()
    db.refresh(q)
    return ok(_serialize(q))


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db)) -> dict:
    q = db.get(Question, question_id)
    if not q:
        return err(1002, f"question {question_id} not found")
    db.delete(q)
    db.commit()
    return ok({"deleted": True, "id": question_id})
