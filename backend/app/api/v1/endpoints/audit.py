"""Audit log query and CSV export (manager+)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGER_AND_UP, require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.audit import AuditLogRead
from app.schemas.common import Envelope, Meta, ok
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Envelope[list[AuditLogRead]])
async def list_audit_logs(
    entity_type: str | None = Query(None),
    entity_id: uuid.UUID | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None, description="Exact verb or prefix, e.g. claim."),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await audit_service.list_logs(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )
    return ok(items, meta=Meta(page=page, per_page=per_page, total=total))


@router.get("/export")
async def export_audit_logs(
    entity_type: str | None = Query(None),
    entity_id: uuid.UUID | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    csv_body = await audit_service.export_csv(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    return StreamingResponse(
        iter([csv_body]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="audit-log-export.csv"'
        },
    )
