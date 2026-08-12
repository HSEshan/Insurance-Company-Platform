"""Append-only audit trail: record, query, and CSV export.

Entries are written explicitly from the service layer (not via SQLAlchemy
``after_flush`` listeners). That keeps async sessions simple, avoids recursive
auditing of the audit table itself, and makes the audited actions intentional
and searchable by namespaced verbs (``claim.approved``, ``payment.voided``).
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core import request_context
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.audit import AuditLogRead

# Used when a login fails for an email that has no account — entity_id is NOT
# NULL on the table, so we need a stable sentinel rather than inventing rows.
ANONYMOUS_ENTITY_ID = uuid.UUID(int=0)

# Word-boundary match so a key like ``tokens`` (a list of objects) is still
# walked, while ``access_token`` / ``ssn_last4`` are redacted.
_SENSITIVE_KEY_RE = re.compile(
    r"(^|_)(ssn|password|secret|token|encryption|hashed)(_|$)",
    re.IGNORECASE,
)


def _is_sensitive_key(key: str) -> bool:
    return _SENSITIVE_KEY_RE.search(key) is not None


def scrub_value(value: Any) -> Any:
    """Recursively redact PII-ish keys before persisting JSON diffs."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = scrub_value(item)
        return cleaned
    if isinstance(value, list):
        return [scrub_value(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _serialize_ip(ip_address: str | None) -> str | None:
    """INET columns reject empty/garbage strings; drop anything unusable."""
    if not ip_address:
        return None
    candidate = ip_address.strip()
    if not candidate or candidate.lower() == "unknown":
        return None
    # X-Forwarded-For may contain a chain; keep the left-most hop.
    candidate = candidate.split(",")[0].strip()
    return candidate or None


async def record(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    actor: User | None = None,
    actor_role: UserRole | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    commit: bool = False,
) -> AuditLog:
    """Append an audit row. Callers usually leave ``commit=False`` so the entry
    lands in the same transaction as the business write; pass ``commit=True``
    when recording a failure path that will not otherwise commit (e.g. bad login).
    """
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_role=actor_role or (actor.role if actor else None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=scrub_value(old_value) if old_value is not None else None,
        new_value=scrub_value(new_value) if new_value is not None else None,
        ip_address=_serialize_ip(request_context.current_ip_address()),
        user_agent=request_context.current_user_agent(),
        request_id=request_context.current_request_id(),
    )
    db.add(entry)
    if commit:
        await db.commit()
        await db.refresh(entry)
    else:
        await db.flush()
    return entry


def _filters(
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(AuditLog.entity_id == entity_id)
    if actor_id is not None:
        conditions.append(AuditLog.actor_id == actor_id)
    if action:
        # Prefix match lets managers filter ``claim.*`` or exact verbs.
        conditions.append(AuditLog.action.ilike(f"{action}%"))
    if date_from is not None:
        conditions.append(AuditLog.created_at >= date_from)
    if date_to is not None:
        conditions.append(AuditLog.created_at <= date_to)
    return conditions


def _list_stmt(
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Select:
    stmt = (
        select(AuditLog, User.email, User.first_name, User.last_name)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .order_by(AuditLog.created_at.desc())
    )
    for condition in _filters(
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
    ):
        stmt = stmt.where(condition)
    return stmt


def to_read(
    entry: AuditLog,
    *,
    actor_email: str | None = None,
    actor_first: str | None = None,
    actor_last: str | None = None,
) -> AuditLogRead:
    name = None
    if actor_first or actor_last:
        name = f"{actor_first or ''} {actor_last or ''}".strip() or None
    ip = str(entry.ip_address) if entry.ip_address is not None else None
    return AuditLogRead(
        id=entry.id,
        actor_id=entry.actor_id,
        actor_role=entry.actor_role,
        actor_email=actor_email,
        actor_name=name,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        old_value=entry.old_value,
        new_value=entry.new_value,
        ip_address=ip,
        user_agent=entry.user_agent,
        request_id=entry.request_id,
        created_at=entry.created_at,
    )


async def list_logs(
    db: AsyncSession,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[AuditLogRead], int]:
    filters = dict(
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    count_stmt = select(func.count()).select_from(AuditLog)
    for condition in _filters(**filters):
        count_stmt = count_stmt.where(condition)
    total = int(await db.scalar(count_stmt) or 0)

    rows = (
        await db.execute(
            _list_stmt(**filters).offset((page - 1) * per_page).limit(per_page)
        )
    ).all()
    items = [
        to_read(entry, actor_email=email, actor_first=first, actor_last=last)
        for entry, email, first, last in rows
    ]
    return items, total


async def export_csv(
    db: AsyncSession,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 10_000,
) -> str:
    """Return a CSV string for compliance download (capped for safety)."""
    rows = (
        await db.execute(
            _list_stmt(
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor_id,
                action=action,
                date_from=date_from,
                date_to=date_to,
            ).limit(limit)
        )
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "created_at",
            "actor_id",
            "actor_email",
            "actor_role",
            "action",
            "entity_type",
            "entity_id",
            "old_value",
            "new_value",
            "ip_address",
            "user_agent",
            "request_id",
        ]
    )
    for entry, email, _first, _last in rows:
        writer.writerow(
            [
                str(entry.id),
                entry.created_at.isoformat() if entry.created_at else "",
                str(entry.actor_id) if entry.actor_id else "",
                email or "",
                entry.actor_role.value if entry.actor_role else "",
                entry.action,
                entry.entity_type,
                str(entry.entity_id),
                entry.old_value if entry.old_value is not None else "",
                entry.new_value if entry.new_value is not None else "",
                str(entry.ip_address) if entry.ip_address is not None else "",
                entry.user_agent or "",
                str(entry.request_id) if entry.request_id else "",
            ]
        )
    return buffer.getvalue()
