"""AI 平台查询适配器 (M4 监测模块用)。

每个适配器实现 BaseMonitor.query(question) → dict, 返回:
    {
      "is_mentioned": bool,
      "position": int | None,
      "has_link": bool,
      "sentiment": str | None,
      "raw_answer": str,
      "screenshot_path": str,
    }

支持平台:
- doubao  (cookie)
- kimi    (cookie)
- chatgpt (API key)
"""
from __future__ import annotations

from .base import BaseMonitor, MonitorError
from .factory import get_ai_monitor, list_supported_monitors

__all__ = [
    "get_ai_monitor",
    "list_supported_monitors",
    "BaseMonitor",
    "MonitorError",
]
