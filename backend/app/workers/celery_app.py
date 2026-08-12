"""Celery application, beat schedule, and task autodiscovery."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "insureco",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Prefer visibility over fire-and-forget while demos are short-lived.
    task_track_started=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Specs §9 — times are UTC; fine for a local portfolio demo.
        "check-overdue-premiums": {
            "task": "app.workers.tasks.check_overdue_premiums",
            "schedule": crontab(hour=9, minute=0),
        },
        "cleanup-storage": {
            "task": "app.workers.tasks.cleanup_storage",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)
