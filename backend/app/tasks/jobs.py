"""APScheduler 后台 job 函数。

重构后仅保留监测 (M4) 任务;M1/M2/M3 的 generate/distribute 任务已删除。

每个 job:
1. 自己创建 SessionLocal 实例(因为 scheduler 线程外的 db session 不能跨线程共享)
2. 更新 task_store 状态
3. 异常时把 error 写入 task_store
"""
from __future__ import annotations

import logging

from ..db import SessionLocal
from ..services.task_store import task_store

logger = logging.getLogger("geo.tasks")


def _start(task_id: str) -> None:
    task_store.update(task_id, status="running", progress=10)


def _success(task_id: str, result: dict | None = None) -> None:
    task_store.update(task_id, status="success", progress=100, result=result or {})


def _fail(task_id: str, e: Exception) -> None:
    logger.exception("task %s failed", task_id)
    task_store.update(task_id, status="failed", error=str(e))


# ---------- M4 监测 ----------
def run_monitor(
    task_id: str,
    client_id: int,
    question_ids: list[int] | None,
    platforms: list[str] | None,
    max_questions: int | None = None,
    extra_question_texts: list[str] | None = None,
    run_id: int | None = None,
) -> None:
    from ..modules.m4_monitor.service import run_monitor_sync

    db = SessionLocal()
    try:
        _start(task_id)
        result = run_monitor_sync(
            db,
            client_id,
            question_ids=question_ids,
            platforms=platforms,
            max_questions=max_questions,
            extra_question_texts=extra_question_texts,
            task_id=task_id,
            run_id=run_id,
        )
        _success(task_id, result)
    except Exception as e:  # noqa: BLE001
        _fail(task_id, e)
    finally:
        db.close()


# ---------- Citation 后台解析 ----------
def resolve_citations_job(batch_size: int = 50, timeout: float = 10.0) -> None:
    """周期把 monitor_citations 里 status=pending 的行送到 resolver。

    主要消化 Gemini 的 grounding-api-redirect URL,普通域名在写入时就
    已经 resolve_status='ok' 不会进这里。空跑 (无 pending) 也不报错。
    """
    from ..services.citation_analysis.pipeline import resolve_pending_citations

    db = SessionLocal()
    try:
        stats = resolve_pending_citations(db, batch_size=batch_size, timeout=timeout)
        if stats.get("resolved") or stats.get("failed"):
            logger.info("citation resolver: %s", stats)
    except Exception:  # noqa: BLE001
        logger.exception("citation resolver job failed")
    finally:
        db.close()
