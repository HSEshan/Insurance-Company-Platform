"""Premium payment recording, listing, and voiding."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGER_AND_UP, get_current_user, require_roles
from app.core.database import get_db
from app.models.enums import PaymentStatus, PaymentType
from app.models.user import User
from app.schemas.common import Envelope, Meta, ok
from app.schemas.payment import PaymentCreate, PaymentRead, PaymentVoid
from app.services import payment_service

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=Envelope[list[PaymentRead]])
async def list_payments(
    policy_id: uuid.UUID | None = Query(None),
    payment_type: PaymentType | None = Query(None),
    payment_status: PaymentStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Customers see only their own ledger; staff see everything."""
    payments, total = await payment_service.list_payments(
        db,
        current_user,
        policy_id=policy_id,
        payment_type=payment_type,
        status=payment_status,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return ok(payments, meta=Meta(page=page, per_page=per_page, total=total))


@router.post(
    "",
    response_model=Envelope[PaymentRead],
    status_code=status.HTTP_201_CREATED,
)
async def record_payment(
    payload: PaymentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Post a premium payment against one installment."""
    payment = await payment_service.record_premium_payment(db, current_user, payload)
    return ok(await payment_service.get_payment_read(db, payment.id, current_user))


@router.get("/{payment_id}", response_model=Envelope[PaymentRead])
async def get_payment(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok(await payment_service.get_payment_read(db, payment_id, current_user))


@router.post("/{payment_id}/void", response_model=Envelope[PaymentRead])
async def void_payment(
    payment_id: uuid.UUID,
    payload: PaymentVoid,
    current_user: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reverse a payment; the installment it settled reopens automatically."""
    payment = await payment_service.void_payment(
        db, payment_id, current_user, payload.reason
    )
    return ok(await payment_service.get_payment_read(db, payment.id, current_user))
