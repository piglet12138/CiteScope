"""内存任务存储 (MVP)。

后期可替换为 SQLite tasks 表。线程安全,使用 threading.Lock 保护。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any
from uuid import uuid4


class TaskStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, dict[str, Any]] = {}

    def create(self, task_type: str, client_id: int | None = None) -> str:
        task_id = uuid4().hex
        now = datetime.utcnow()
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "type": task_type,
                "status": "queued",
                "progress": 0,
                "result": None,
                "error": None,
                "client_id": client_id,
                "created_at": now,
                "updated_at": now,
            }
        return task_id

    def update(
        self,
        task_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            t = self._tasks.get(task_id)
            if not t:
                return
            if status is not None:
                t["status"] = status
            if progress is not None:
                t["progress"] = progress
            if result is not None:
                t["result"] = result
            if error is not None:
                t["error"] = error
            t["updated_at"] = datetime.utcnow()

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            t = self._tasks.get(task_id)
            return dict(t) if t else None

    def list(
        self,
        *,
        status: str | None = None,
        client_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            items = list(self._tasks.values())
        if status:
            items = [t for t in items if t["status"] == status]
        if client_id is not None:
            items = [t for t in items if t["client_id"] == client_id]
        items.sort(key=lambda t: t["created_at"], reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return [dict(t) for t in items[start:end]], total


task_store = TaskStore()
