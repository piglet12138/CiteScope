"""Document management router for knowledge base."""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from ..schemas import ok, err

router = APIRouter()

DOCS_DIR = Path("data/docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Simple JSON-based metadata store (no DB table needed for now)
import json

META_FILE = DOCS_DIR / "_meta.json"


def _load_meta() -> list[dict]:
    if META_FILE.exists():
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    return []


def _save_meta(items: list[dict]):
    META_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_id(items: list[dict]) -> int:
    return max((i["id"] for i in items), default=0) + 1


@router.get("/docs")
def list_docs():
    items = _load_meta()
    return ok(items)


@router.post("/docs/upload")
async def upload_doc(file: UploadFile = File(...)):
    items = _load_meta()
    doc_id = _next_id(items)

    # Sanitize filename
    original = file.filename or f"doc_{doc_id}"
    ext = Path(original).suffix
    stored_name = f"{doc_id}_{int(time.time())}{ext}"
    dest = DOCS_DIR / stored_name

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size = dest.stat().st_size
    mime = file.content_type or "application/octet-stream"

    item = {
        "id": doc_id,
        "filename": stored_name,
        "original_name": original,
        "size": size,
        "mime_type": mime,
        "uploaded_at": datetime.utcnow().isoformat(),
        "description": "",
    }
    items.append(item)
    _save_meta(items)

    return ok(item)


@router.get("/docs/{doc_id}/download")
def download_doc(doc_id: int):
    items = _load_meta()
    doc = next((i for i in items if i["id"] == doc_id), None)
    if not doc:
        return err(404, "Document not found")

    path = DOCS_DIR / doc["filename"]
    if not path.exists():
        return err(404, "File not found on disk")

    return FileResponse(
        path=str(path),
        filename=doc["original_name"],
        media_type=doc["mime_type"],
    )


@router.delete("/docs/{doc_id}")
def delete_doc(doc_id: int):
    items = _load_meta()
    doc = next((i for i in items if i["id"] == doc_id), None)
    if not doc:
        return err(404, "Document not found")

    path = DOCS_DIR / doc["filename"]
    if path.exists():
        path.unlink()

    items = [i for i in items if i["id"] != doc_id]
    _save_meta(items)

    return ok({"deleted": True, "id": doc_id})
