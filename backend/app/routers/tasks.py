"""任务队列路由。"""
from __future__ import annotations

from fastapi import APIRouter

from ..schemas import err, ok
from ..services.task_store import task_store

router = APIRouter()


def _serialize(t: dict) -> dict:
    return {
        "task_id": t["task_id"],
        "type": t["type"],
        "status": t["status"],
        "progress": t.get("progress", 0),
        "result": t.get("result"),
        "error": t.get("error"),
        "client_id": t.get("client_id"),
        "created_at": t["created_at"].isoformat() + "Z" if t.get("created_at") else None,
        "updated_at": t["updated_at"].isoformat() + "Z" if t.get("updated_at") else None,
    }


@router.get("/tasks")
def list_tasks(
    status: str | None = None,
    client_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    items, total = task_store.list(
        status=status, client_id=client_id, page=page, page_size=page_size
    )
    return ok(
        {
            "items": [_serialize(t) for t in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    t = task_store.get(task_id)
    if not t:
        return err(1002, f"task {task_id} not found")
    return ok(_serialize(t))


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> dict:
    t = task_store.get(task_id)
    if not t:
        return err(1002, f"task {task_id} not found")
    if t["status"] in ("success", "failed"):
        return err(2002, f"task already in terminal state: {t['status']}")
    task_store.update(task_id, status="failed", error="cancelled")
    t = task_store.get(task_id)
    return ok(_serialize(t))
