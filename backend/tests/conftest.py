"""测试 fixtures: 隔离 SQLite + TestClient。

注意: 必须在导入 app 之前设置环境变量, 否则 db.engine 会用错误路径。
get_settings 是 lru_cache, 但因为我们在导入 app.config 之前就 setenv,
首次调用时即可读取到正确的 GEO_DB_PATH。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


# === 必须在 import app 之前设置环境变量 ===
_TMP_DIR = Path(tempfile.mkdtemp(prefix="geo_test_"))
_DB_PATH = _TMP_DIR / "geo_test.db"
_SCREENSHOT_DIR = _TMP_DIR / "screenshots"

os.environ["GEO_USE_MOCK"] = "1"
os.environ["GEO_DB_PATH"] = str(_DB_PATH)
os.environ["GEO_SCREENSHOT_DIR"] = str(_SCREENSHOT_DIR)
os.environ["GEO_LOG_LEVEL"] = "WARNING"


@pytest.fixture(scope="session")
def app_module():
    """延迟导入 app, 确保上面的环境变量已生效。"""
    from app.main import app  # noqa: WPS433
    from app.db import init_db  # noqa: WPS433

    init_db()
    return app


@pytest.fixture(scope="session")
def client(app_module):
    """同步 TestClient。"""
    from fastapi.testclient import TestClient

    # TestClient 会触发 startup 事件, init_db + scheduler.start()
    with TestClient(app_module) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def _cleanup_after_session():
    yield
    # 关闭 scheduler
    try:
        from app.services.scheduler import scheduler

        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    # 清理 tmp 文件
    try:
        shutil.rmtree(_TMP_DIR, ignore_errors=True)
    except Exception:
        pass
