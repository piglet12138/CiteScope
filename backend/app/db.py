"""SQLite 连接 + WAL 模式 + Session 管理。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_engine(
    _settings.db_url,
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """启动时自动建表 + 轻量字段补齐 (替代 Alembic, 仅用于 SQLite MVP)。"""
    # 导入模型以注册到 Base.metadata
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_inplace_migrations()


def _apply_inplace_migrations() -> None:
    """对已存在的旧库做"加列"式补齐。

    SQLite 的 ALTER TABLE 只支持 ADD COLUMN, 这里手动补齐 P1 多账号改造引入的新列。
    幂等: 已存在的列会被 PRAGMA 检查跳过。
    """
    import logging

    log = logging.getLogger("geo.db.migrate")

    pending: list[tuple[str, str, str]] = [
        # (table, column, ddl)
        (
            "monitor_results",
            "search_results",
            "ALTER TABLE monitor_results ADD COLUMN search_results JSON",
        ),
        (
            "monitor_results",
            "run_id",
            "ALTER TABLE monitor_results ADD COLUMN run_id INTEGER REFERENCES monitor_runs(id)",
        ),
    ]

    with engine.begin() as conn:
        from sqlalchemy import text

        for table, column, ddl in pending:
            try:
                rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            except Exception:
                # 表不存在 (新库) → create_all 已建好正确 schema, 跳过
                continue
            existing = {r[1] for r in rows}
            if column in existing:
                continue
            try:
                conn.exec_driver_sql(ddl)
                log.info("migrate: added column %s.%s", table, column)
            except Exception as e:  # noqa: BLE001
                log.warning("migrate: failed to add %s.%s: %s", table, column, e)
