"""通用 Pydantic Schema:响应包络、分页、任务。

业务模型 schema 由各模块自己定义,放在 modules/*/schemas.py。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None
    trace_id: str = Field(default_factory=lambda: uuid4().hex[:12])


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20


class TaskRef(BaseModel):
    """异步任务的轻量返回。"""

    task_id: str
    status: str = "queued"
    extra: dict[str, Any] | None = None


class TaskInfo(BaseModel):
    task_id: str
    type: str
    status: str  # queued / running / success / failed
    progress: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    client_id: int | None = None
    created_at: datetime
    updated_at: datetime


def ok(data: Any = None) -> dict[str, Any]:
    """快速构造成功响应包络 (在 router 中可直接 return)。"""
    return {"code": 0, "message": "ok", "data": data, "trace_id": uuid4().hex[:12]}


def err(code: int, message: str) -> dict[str, Any]:
    return {"code": code, "message": message, "data": None, "trace_id": uuid4().hex[:12]}
