"""LLM 调用计量 (token / cost) 落库。

设计:
  - 用 contextvars 维护"当前调用归属"(client_id, purpose),
    业务层 (m4_monitor) 在调 LLM 之前 with metering_context(...) 即可。
  - llm_client 在每次真实 HTTP 调用结束 (无论成功失败) 都调 record_call() 落一条 LLMCallLog。
  - 这里开独立 SessionLocal, 不依赖请求生命周期 — 因为监测任务在 APScheduler/worker 里跑。

不引入 asyncio queue / 批量 flush — 单次 LLM 调用本身就是秒级, 一次 INSERT 的开销可忽略。
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

from ..db import SessionLocal
from ..models import LLMCallLog
from .llm_pricing import calc_cost_usd

logger = logging.getLogger("geo.llm.metering")


@dataclass
class MeteringContext:
    client_id: int | None = None
    purpose: str = "unknown"


_ctx: ContextVar[MeteringContext] = ContextVar(
    "llm_metering_ctx", default=MeteringContext()
)


@contextmanager
def metering_context(
    *,
    purpose: str,
    client_id: int | None = None,
) -> Iterator[None]:
    """业务层用 with 包住一段 LLM 调用, 这段时间内的所有 record_call() 都会带上这些归属。

    嵌套行为: purpose 总是覆盖; client_id 若内层未传则继承外层。
    """
    parent = _ctx.get()
    token = _ctx.set(
        MeteringContext(
            client_id=client_id if client_id is not None else parent.client_id,
            purpose=purpose,
        )
    )
    try:
        yield
    finally:
        _ctx.reset(token)


def current_context() -> MeteringContext:
    return _ctx.get()


def record_call(
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status: str = "ok",
    error: str | None = None,
    usd_cost: float | None = None,
) -> None:
    """落一条 LLMCallLog。

    Args:
        usd_cost: 若显式给出 (>=0),直接用;否则按 llm_pricing token 价计算。
                  搜索 API (M4 监测) 应显式传 usd_cost,因为定价模型不只看 token。

    任何异常都被吞掉 (并 warn 日志), 计量永远不能影响主业务流程。
    """
    try:
        ctx = current_context()
        total = (prompt_tokens or 0) + (completion_tokens or 0)
        cost = (
            usd_cost
            if usd_cost is not None
            else calc_cost_usd(provider, model, prompt_tokens or 0, completion_tokens or 0)
        )
        with SessionLocal() as db:
            row = LLMCallLog(
                # 显式 set created_at, 防止某些环境下 server_default 失效
                # (例如 migrate 后表结构丢了 DEFAULT CURRENT_TIMESTAMP 子句)
                created_at=datetime.utcnow(),
                client_id=ctx.client_id,
                purpose=ctx.purpose,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens or 0,
                completion_tokens=completion_tokens or 0,
                total_tokens=total,
                usd_cost=cost,
                latency_ms=latency_ms,
                status=status,
                error=(error[:500] if error else None),
            )
            db.add(row)
            db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM 计量落库失败 (忽略): %s", e)
