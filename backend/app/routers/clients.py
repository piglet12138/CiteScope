"""客户管理路由 (M5)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_db
from ..modules.m5_clients import service as svc
from ..modules.m5_clients.schemas import ClientCreate, ClientUpdate
from ..schemas import err, ok

router = APIRouter()


@router.get("/clients")
def list_clients(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    items, total = svc.list_clients(db, page=page, page_size=page_size, status=status)
    return ok(
        {
            "items": [c.model_dump(mode="json") for c in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/clients")
def create_client(body: ClientCreate, db: Session = Depends(get_db)) -> dict:
    try:
        c = svc.create_client(db, body)
    except svc.ClientConflictError as e:
        return err(1003, str(e))
    return ok(c.model_dump(mode="json"))


@router.get("/clients/{client_id}")
def get_client(client_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        c = svc.get_client(db, client_id)
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))
    return ok(c.model_dump(mode="json"))


@router.put("/clients/{client_id}")
def update_client(
    client_id: int, body: ClientUpdate, db: Session = Depends(get_db)
) -> dict:
    try:
        c = svc.update_client(db, client_id, body)
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))
    return ok(c.model_dump(mode="json"))


@router.post("/clients/{client_id}/regenerate-keywords")
def regenerate_client_keywords(client_id: int, db: Session = Depends(get_db)) -> dict:
    """调 LLM 重新生成客户的品牌识别关键词 (用于存量客户或描述更新后)。"""
    try:
        c = svc.regenerate_keywords(db, client_id)
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))
    return ok(c.model_dump(mode="json"))


@router.delete("/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        result = svc.delete_client(db, client_id)
    except svc.ClientNotFoundError as e:
        return err(1002, str(e))
    return ok(result)
