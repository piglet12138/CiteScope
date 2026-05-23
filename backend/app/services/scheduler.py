"""APScheduler 单例 + 内存任务表。

任务表本身在 services/task_store.py;此文件仅暴露 scheduler 实例,
方便其他模块注册定时任务和后台 job。
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler(timezone="UTC")
