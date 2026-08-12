"""Celery task entry points.

Each task opens a fresh async session, runs the matching service function, and
returns a JSON-serializable summary for the result backend / logs.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.database import AsyncSessionLocal, engine
from app.services import pdf_service, scheduler_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro_factory: Callable[[], Awaitable[Any]]) -> Any:
    """Run an async coroutine from a sync Celery worker process.

    Celery workers are synchronous. Each task gets a fresh asyncio loop, so the
    shared async engine must be disposed afterwards — otherwise the next task
    finds connection Futures still attached to the closed loop.
    """

    async def _runner() -> Any:
        try:
            return await coro_factory()
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


async def _with_session(work: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
    async with AsyncSessionLocal() as db:
        return await work(db, *args, **kwargs)


@celery_app.task(name="app.workers.tasks.check_overdue_premiums")
def check_overdue_premiums() -> dict[str, int]:
    result = _run(lambda: _with_session(scheduler_service.check_overdue_premiums))
    logger.info(
        "Overdue sweep: marked=%s notifications=%s lapsed=%s",
        result.marked_overdue,
        result.notifications,
        result.lapsed_policies,
    )
    return {
        "marked_overdue": result.marked_overdue,
        "notifications": result.notifications,
        "lapsed_policies": result.lapsed_policies,
    }


@celery_app.task(name="app.workers.tasks.cleanup_storage")
def cleanup_storage() -> dict[str, int]:
    result = _run(lambda: _with_session(scheduler_service.cleanup_storage))
    logger.info(
        "Storage cleanup: temp=%s orphans=%s",
        result.temp_deleted,
        result.orphan_deleted,
    )
    return {
        "temp_deleted": result.temp_deleted,
        "orphan_deleted": result.orphan_deleted,
    }


@celery_app.task(name="app.workers.tasks.send_notification_email")
def send_notification_email(notification_id: str) -> bool:
    """Deliver one notification by email and mark ``sent_via_email``."""
    from app.services import notification_service

    return bool(
        _run(
            lambda: _with_session(
                notification_service.deliver_email, uuid.UUID(notification_id)
            )
        )
    )


@celery_app.task(name="app.workers.tasks.generate_policy_declaration")
def generate_policy_declaration(policy_id: str, actor_id: str | None = None) -> str | None:
    """Render and file a declaration page after bind."""

    async def _job():
        from sqlalchemy import select

        from app.models.policy import Policy

        async with AsyncSessionLocal() as db:
            policy = await db.scalar(
                select(Policy).where(Policy.id == uuid.UUID(policy_id))
            )
            if policy is None:
                logger.warning("Declaration task: policy %s not found", policy_id)
                return None
            document = await pdf_service.try_generate(
                pdf_service.generate_policy_declaration(
                    db,
                    policy,
                    uuid.UUID(actor_id) if actor_id else None,
                ),
                description=f"declaration for {policy.policy_number}",
            )
            return str(document.id) if document else None

    return _run(_job)


@celery_app.task(name="app.workers.tasks.generate_claim_decision_letter")
def generate_claim_decision_letter(
    claim_id: str, decision: str, actor_id: str | None = None
) -> str | None:
    """Render and file an approval/rejection letter after adjudication."""

    async def _job():
        from sqlalchemy import select

        from app.models.claim import Claim

        async with AsyncSessionLocal() as db:
            claim = await db.scalar(select(Claim).where(Claim.id == uuid.UUID(claim_id)))
            if claim is None:
                logger.warning("Decision letter task: claim %s not found", claim_id)
                return None
            document = await pdf_service.try_generate(
                pdf_service.generate_claim_decision_letter(
                    db,
                    claim,
                    decision=decision,
                    actor_id=uuid.UUID(actor_id) if actor_id else None,
                ),
                description=f"{decision} letter for {claim.claim_number}",
            )
            return str(document.id) if document else None

    return _run(_job)


def enqueue(task, *args, description: str, **kwargs) -> None:
    """Send a task to the broker; fall back to running it inline if Redis is down.

    PDF generation and similar side effects must not fail the HTTP request when
    the worker stack is unavailable — the portfolio demo should still bind a
    policy on a laptop with only ``backend`` running.
    """
    try:
        task.delay(*args, **kwargs)
    except Exception:
        logger.exception(
            "Could not enqueue %s; running inline as a fallback", description
        )
        try:
            task.apply(args=args, kwargs=kwargs)
        except Exception:
            logger.exception("Inline fallback for %s also failed", description)
