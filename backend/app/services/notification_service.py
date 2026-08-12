"""In-app notifications: persist first, email second.

The timeline decision for Phase 4: write the row synchronously in the service
layer so the bell is always correct, and hand email off to Celery. A dropped
broker message must never lose a user-visible notification.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.customer import Customer
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationRead

logger = logging.getLogger(__name__)


async def emit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    notification_type: NotificationType,
    title: str,
    body: str,
    related_entity_type: str | None = None,
    related_entity_id: uuid.UUID | None = None,
) -> Notification:
    """Persist an in-app notification. Caller commits, then ``queue_email``."""
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        body=body,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)
    return notification


def queue_email(notification_id: uuid.UUID) -> None:
    """Enqueue email delivery after the surrounding transaction has committed."""
    from app.workers import tasks as worker_tasks

    worker_tasks.enqueue(
        worker_tasks.send_notification_email,
        str(notification_id),
        description=f"email for notification {notification_id}",
    )


async def emit_and_queue(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    notification_type: NotificationType,
    title: str,
    body: str,
    related_entity_type: str | None = None,
    related_entity_id: uuid.UUID | None = None,
) -> Notification:
    """Write the row, commit is caller's job — queue email after commit yourself.

    Prefer the two-step ``emit`` + commit + ``queue_email`` pattern. This helper
    only exists for call sites that already committed and open a short session.
    """
    return await emit(
        db,
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )


async def user_id_for_customer(
    db: AsyncSession, customer_id: uuid.UUID
) -> uuid.UUID | None:
    return await db.scalar(select(Customer.user_id).where(Customer.id == customer_id))


async def notify_customer(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    notification_type: NotificationType,
    title: str,
    body: str,
    related_entity_type: str | None = None,
    related_entity_id: uuid.UUID | None = None,
) -> Notification | None:
    """Emit a notification to the user account behind a customer profile."""
    user_id = await user_id_for_customer(db, customer_id)
    if user_id is None:
        logger.warning("No user for customer %s; skipping notification", customer_id)
        return None
    return await emit(
        db,
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )


# --------------------------------------------------------------------------- #
# Read API
# --------------------------------------------------------------------------- #
async def list_notifications(
    db: AsyncSession,
    actor: User,
    *,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[NotificationRead], int]:
    stmt = select(Notification).where(Notification.user_id == actor.id)
    count_stmt = select(func.count(Notification.id)).where(
        Notification.user_id == actor.id
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
        count_stmt = count_stmt.where(Notification.is_read.is_(False))

    total = int(await db.scalar(count_stmt) or 0)
    rows = list(
        (
            await db.scalars(
                stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
            )
        ).all()
    )
    return [NotificationRead.model_validate(n) for n in rows], total


async def unread_count(db: AsyncSession, actor: User) -> int:
    count = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == actor.id,
            Notification.is_read.is_(False),
        )
    )
    return int(count or 0)


async def mark_read(
    db: AsyncSession, notification_id: uuid.UUID, actor: User
) -> Notification:
    notification = await db.scalar(
        select(Notification).where(Notification.id == notification_id)
    )
    if notification is None:
        raise NotFoundError("Notification not found.", code="NOTIFICATION_NOT_FOUND")
    if notification.user_id != actor.id:
        raise ForbiddenError("You do not have access to this notification.")
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification


async def mark_all_read(db: AsyncSession, actor: User) -> int:
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == actor.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await db.commit()
    return int(result.rowcount or 0)


async def get_notification(db: AsyncSession, notification_id: uuid.UUID) -> Notification:
    notification = await db.scalar(
        select(Notification).where(Notification.id == notification_id)
    )
    if notification is None:
        raise NotFoundError("Notification not found.", code="NOTIFICATION_NOT_FOUND")
    return notification


async def deliver_email(db: AsyncSession, notification_id: uuid.UUID) -> bool:
    """Load a notification + recipient and send the email. Idempotent."""
    from app.services import email_service

    notification = await get_notification(db, notification_id)
    if notification.sent_via_email:
        return True

    user = await db.scalar(select(User).where(User.id == notification.user_id))
    if user is None or not user.email:
        logger.warning("No email for user %s", notification.user_id)
        return False

    sent = await email_service.send_email(
        to=user.email,
        subject=notification.title or "InsureCo notification",
        body=notification.body or "",
    )
    if sent:
        notification.sent_via_email = True
        await db.commit()
    return sent
