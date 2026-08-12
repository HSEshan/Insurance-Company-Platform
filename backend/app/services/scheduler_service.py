"""Scheduled maintenance jobs: overdue premiums, lapses, storage cleanup.

These functions are plain async services so unit tests (and a future admin
"run now" button) can call them without going through Celery. The worker
tasks in ``app.workers`` are thin wrappers that ``asyncio.run`` them.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import settings
from app.core.storage import Bucket
from app.models.billing import PremiumSchedule
from app.models.document import Document
from app.models.enums import (
    NotificationType,
    PolicyStatus,
    PremiumScheduleStatus,
)
from app.models.notification import Notification
from app.models.policy import Policy
from app.services import billing, notification_service

logger = logging.getLogger(__name__)

_OPEN_INSTALLMENTS = frozenset(
    {
        PremiumScheduleStatus.upcoming,
        PremiumScheduleStatus.due,
        PremiumScheduleStatus.overdue,
    }
)


@dataclass(frozen=True)
class OverdueSweepResult:
    marked_overdue: int
    notifications: int
    lapsed_policies: int


@dataclass(frozen=True)
class CleanupResult:
    temp_deleted: int
    orphan_deleted: int


async def check_overdue_premiums(
    db: AsyncSession, *, today: date | None = None
) -> OverdueSweepResult:
    """Mark past-due installments, notify customers, and lapse stale policies."""
    today = today or date.today()
    marked = 0
    notified = 0
    pending_emails: list[uuid.UUID] = []

    schedules = list(
        (
            await db.scalars(
                select(PremiumSchedule).where(
                    PremiumSchedule.due_date < today,
                    PremiumSchedule.status.in_(
                        [
                            PremiumScheduleStatus.upcoming,
                            PremiumScheduleStatus.due,
                            PremiumScheduleStatus.overdue,
                        ]
                    ),
                )
            )
        ).all()
    )

    for schedule in schedules:
        paid = await billing.paid_to_date(db, schedule.id)
        new_status = billing.resolve_schedule_status(
            amount_due=schedule.amount_due,
            amount_paid=paid,
            due_date=schedule.due_date,
            today=today,
            current=schedule.status,
        )
        if (
            new_status == PremiumScheduleStatus.overdue
            and schedule.status != PremiumScheduleStatus.overdue
        ):
            schedule.status = new_status
            marked += 1
            nid = await _notify_payment_overdue(db, schedule)
            if nid is not None:
                pending_emails.append(nid)
                notified += 1
        elif new_status != schedule.status:
            schedule.status = new_status

    lapsed, lapse_emails = await _lapse_policies_past_grace(db, today=today)
    pending_emails.extend(lapse_emails)
    await db.commit()
    # Email only after commit so the worker can load the rows.
    for notification_id in pending_emails:
        notification_service.queue_email(notification_id)
    return OverdueSweepResult(
        marked_overdue=marked, notifications=notified, lapsed_policies=lapsed
    )


async def _notify_payment_overdue(
    db: AsyncSession, schedule: PremiumSchedule
) -> uuid.UUID | None:
    """Write one in-app notification when an installment first becomes overdue."""
    policy = await db.scalar(select(Policy).where(Policy.id == schedule.policy_id))
    if policy is None:
        return None

    user_id = await notification_service.user_id_for_customer(db, policy.customer_id)
    if user_id is None:
        return None

    # Avoid spamming if the job is re-run after a partial failure.
    already = await db.scalar(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.type == NotificationType.payment_overdue,
            Notification.related_entity_id == schedule.id,
        )
    )
    if already is not None:
        return None

    notification = await notification_service.emit(
        db,
        user_id=user_id,
        notification_type=NotificationType.payment_overdue,
        title="Premium payment overdue",
        body=(
            f"Your premium installment of ${schedule.amount_due:,.2f} for "
            f"policy {policy.policy_number} was due {schedule.due_date.isoformat()} "
            f"and remains unpaid. Please contact your agent to avoid a lapse."
        ),
        related_entity_type="premium_schedule",
        related_entity_id=schedule.id,
    )
    return notification.id


async def _lapse_policies_past_grace(
    db: AsyncSession, *, today: date
) -> tuple[int, list[uuid.UUID]]:
    """Lapse active policies whose oldest unpaid installment is past the grace window."""
    cutoff = today - timedelta(days=settings.PREMIUM_LAPSE_DAYS)
    active = list(
        (await db.scalars(select(Policy).where(Policy.status == PolicyStatus.active))).all()
    )
    lapsed = 0
    emails: list[uuid.UUID] = []
    for policy in active:
        oldest_unpaid = await db.scalar(
            select(PremiumSchedule)
            .where(
                PremiumSchedule.policy_id == policy.id,
                PremiumSchedule.status.in_(list(_OPEN_INSTALLMENTS)),
                PremiumSchedule.due_date <= cutoff,
            )
            .order_by(PremiumSchedule.due_date.asc())
            .limit(1)
        )
        if oldest_unpaid is None:
            continue
        # Confirm there is still a real balance — a status drift shouldn't lapse anyone.
        paid = await billing.paid_to_date(db, oldest_unpaid.id)
        if billing.outstanding_balance(oldest_unpaid.amount_due, paid) <= billing.ZERO:
            continue

        policy.status = PolicyStatus.lapsed
        policy.cancellation_reason = (
            f"Non-payment: installment due {oldest_unpaid.due_date.isoformat()} "
            f"unpaid for {settings.PREMIUM_LAPSE_DAYS}+ days."
        )
        policy.cancelled_at = datetime.now(UTC)
        nid = await _notify_policy_lapsed(db, policy)
        if nid is not None:
            emails.append(nid)
        lapsed += 1
        logger.info("Lapsed policy %s for non-payment", policy.policy_number)
    return lapsed, emails


async def _notify_policy_lapsed(db: AsyncSession, policy: Policy) -> uuid.UUID | None:
    notification = await notification_service.notify_customer(
        db,
        policy.customer_id,
        notification_type=NotificationType.policy_lapsed,
        title="Policy lapsed for non-payment",
        body=(
            f"Policy {policy.policy_number} has lapsed because a premium "
            f"installment remained unpaid past the "
            f"{settings.PREMIUM_LAPSE_DAYS}-day grace period. Contact your "
            f"agent within 30 days to request reinstatement."
        ),
        related_entity_type="policy",
        related_entity_id=policy.id,
    )
    return notification.id if notification else None


async def cleanup_storage(db: AsyncSession) -> CleanupResult:
    """Purge aged temp uploads and objects with no matching documents row."""
    now = datetime.now(UTC)
    temp_cutoff = now - timedelta(hours=24)
    orphan_cutoff = now - timedelta(minutes=settings.ORPHAN_OBJECT_GRACE_MINUTES)

    temp_deleted = await _purge_aged_objects(Bucket.temp_uploads.value, temp_cutoff)

    rows = await db.execute(select(Document.storage_bucket, Document.storage_key))
    known_keys = {(bucket, key) for bucket, key in rows.all()}

    orphan_deleted = 0
    for bucket in (
        Bucket.policy_documents,
        Bucket.claim_documents,
        Bucket.customer_documents,
    ):
        stale = [
            obj.key
            for obj in await storage.list_objects(bucket.value)
            if (bucket.value, obj.key) not in known_keys
            and _is_older_than(obj.last_modified, orphan_cutoff)
        ]
        if stale:
            await storage.remove_objects(bucket.value, stale)
            orphan_deleted += len(stale)
            logger.info(
                "Removed %d orphaned object(s) from %s", len(stale), bucket.value
            )

    return CleanupResult(temp_deleted=temp_deleted, orphan_deleted=orphan_deleted)


async def _purge_aged_objects(bucket: str, cutoff: datetime) -> int:
    stale = [
        obj.key
        for obj in await storage.list_objects(bucket)
        if _is_older_than(obj.last_modified, cutoff)
    ]
    if stale:
        await storage.remove_objects(bucket, stale)
    return len(stale)


def _is_older_than(modified: datetime | None, cutoff: datetime) -> bool:
    if modified is None:
        return False
    if modified.tzinfo is None:
        modified = modified.replace(tzinfo=UTC)
    return modified < cutoff
