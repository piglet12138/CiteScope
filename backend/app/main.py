"""FastAPI 入口。

启动顺序:
1. 加载配置 (会校验真实模式下的必需 key)
2. 初始化 SQLite (建表 + WAL)
3. 启动 APScheduler
4. 注册路由
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .config import get_settings
from .db import init_db
from .schemas import err, ok
from .services.scheduler import scheduler
from .routers import (
    citation_reports as citation_reports_router,
    clients as clients_router,
    questions as questions_router,
    monitor as monitor_router,
    tasks as tasks_router,
    settings as settings_router,
    usage as usage_router,
    docs as docs_router,
    diagnosis as diagnosis_router,
)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.assert_real_mode_keys()  # 非 mock 模式下校验

    logging.basicConfig(
        level=getattr(logging, settings.GEO_LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("geo.startup")
    logger.info(
        "Starting GEO backend (mock_mode=%s, db=%s)",
        settings.GEO_USE_MOCK,
        settings.GEO_DB_PATH,
    )

    app = FastAPI(
        title="GEO 效果监测实验平台 API",
        version="0.2.0",
        description="CiteScope · Open-source AI Citation Analysis & GEO Monitoring Platform",
    )

    # CORS:开发期允许 Vite (5173) 跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 启动 / 停止钩子
    @app.on_event("startup")
    def _startup() -> None:
        from datetime import datetime, timedelta
        from .tasks.jobs import resolve_citations_job

        init_db()
        if not scheduler.running:
            scheduler.start()
        # 每 5 分钟跑一次 citation resolver,首次 30s 后执行
        scheduler.add_job(
            resolve_citations_job,
            "interval",
            minutes=5,
            id="resolve_citations",
            replace_existing=True,
            next_run_time=datetime.utcnow() + timedelta(seconds=30),
        )
        logger.info("DB initialized & scheduler started (citation resolver every 5min)")

    @app.on_event("shutdown")
    def _shutdown() -> None:
        if scheduler.running:
            scheduler.shutdown(wait=False)

    # 全局异常 → 包络
    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request, exc: RequestValidationError):
        return JSONResponse(
            status_code=200,
            content=err(1001, f"参数校验失败: {exc.errors()[:3]}"),
        )

    @app.exception_handler(Exception)
    async def _generic_handler(_request, exc: Exception):
        logger.exception("unhandled error")
        return JSONResponse(status_code=200, content=err(5000, str(exc)))

    # 健康检查
    @app.get("/api/health")
    def health() -> dict:
        return ok(
            {
                "status": "ok",
                "mock_mode": settings.GEO_USE_MOCK,
                "version": "0.1.0",
            }
        )

    # 注册业务路由
    app.include_router(clients_router.router, prefix="/api", tags=["clients"])
    app.include_router(questions_router.router, prefix="/api", tags=["questions"])
    app.include_router(monitor_router.router, prefix="/api", tags=["monitor"])
    app.include_router(tasks_router.router, prefix="/api", tags=["tasks"])
    app.include_router(settings_router.router, prefix="/api", tags=["settings"])
    app.include_router(usage_router.router, prefix="/api", tags=["usage"])
    app.include_router(docs_router.router, prefix="/api", tags=["docs"])
    app.include_router(diagnosis_router.router, prefix="/api", tags=["diagnosis"])
    app.include_router(citation_reports_router.router, prefix="/api", tags=["citation-reports"])

    return app


app = create_app()
