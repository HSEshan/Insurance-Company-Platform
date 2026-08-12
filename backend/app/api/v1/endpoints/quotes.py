"""Quote endpoints: rating previews + persisted quote underwriting workflow."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AGENT_AND_UP, get_current_user, require_roles
from app.core.database import get_db
from app.models.enums import PaymentFrequency, PolicyType, QuoteStatus, UserRole
from app.models.user import User
from app.schemas.common import Envelope, Meta, ok
from app.schemas.policy import PolicyBindRequest, PolicyRead
from app.schemas.quote import (
    QuoteCreate,
    QuoteListItem,
    QuoteRead,
    QuoteReject,
    QuoteUpdate,
)
from app.services import policy_service, quote_service
from app.services.rating import (
    AutoRatingInput,
    HomeRatingInput,
    LifeRatingInput,
    RatingResult,
    rate_auto,
    rate_home,
    rate_life,
)
from app.workers import tasks as worker_tasks

router = APIRouter(prefix="/quotes", tags=["quotes"])

_QUOTERS = (UserRole.customer, UserRole.agent, UserRole.super_admin)
_UNDERWRITERS = (UserRole.agent, UserRole.manager, UserRole.super_admin)
_QUOTE_READERS = {
    UserRole.customer,
    UserRole.agent,
    UserRole.manager,
    UserRole.super_admin,
}


# --------------------------------------------------------------------------- #
# Stateless rating previews
# --------------------------------------------------------------------------- #
@router.post("/rate/auto", response_model=Envelope[RatingResult])
async def rate_auto_quote(
    payload: AutoRatingInput,
    _: User = Depends(require_roles(*_QUOTERS)),
) -> dict:
    return ok(rate_auto(payload))


@router.post("/rate/home", response_model=Envelope[RatingResult])
async def rate_home_quote(
    payload: HomeRatingInput,
    _: User = Depends(require_roles(*_QUOTERS)),
) -> dict:
    return ok(rate_home(payload))


@router.post("/rate/life", response_model=Envelope[RatingResult])
async def rate_life_quote(
    payload: LifeRatingInput,
    _: User = Depends(require_roles(*_QUOTERS)),
) -> dict:
    return ok(rate_life(payload))


# --------------------------------------------------------------------------- #
# Persisted quotes
# --------------------------------------------------------------------------- #
@router.get("", response_model=Envelope[list[QuoteListItem]])
async def list_quotes(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: QuoteStatus | None = Query(None, alias="status"),
    policy_type: PolicyType | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.role not in _QUOTE_READERS:
        raise HTTPException(status_code=403, detail="Forbidden")

    quotes, total = await quote_service.list_quotes(
        db,
        current_user,
        page=page,
        per_page=per_page,
        status=status_filter,
        policy_type=policy_type,
        customer_id=customer_id,
    )
    return ok(
        [QuoteListItem.model_validate(q) for q in quotes],
        meta=Meta(page=page, per_page=per_page, total=total),
    )


@router.post(
    "",
    response_model=Envelope[QuoteRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_quote(
    payload: QuoteCreate,
    current_user: User = Depends(require_roles(*_QUOTERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    quote = await quote_service.create_quote(db, current_user, payload)
    return ok(quote_service.to_read(quote))


@router.get("/{quote_id}", response_model=Envelope[QuoteRead])
async def get_quote(
    quote_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    quote = await quote_service.get_quote(db, quote_id)
    await quote_service.assert_quote_access(db, quote, current_user)
    return ok(quote_service.to_read(quote))


@router.patch("/{quote_id}", response_model=Envelope[QuoteRead])
async def update_quote(
    quote_id: uuid.UUID,
    payload: QuoteUpdate,
    current_user: User = Depends(require_roles(*_UNDERWRITERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    quote = await quote_service.get_quote(db, quote_id)
    await quote_service.assert_quote_access(db, quote, current_user)
    updated = await quote_service.update_quote(db, quote_id, payload)
    return ok(quote_service.to_read(updated))


@router.post("/{quote_id}/submit", response_model=Envelope[QuoteRead])
async def submit_quote(
    quote_id: uuid.UUID,
    current_user: User = Depends(require_roles(*_UNDERWRITERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    quote = await quote_service.get_quote(db, quote_id)
    await quote_service.assert_quote_access(db, quote, current_user)
    updated = await quote_service.submit_quote(db, quote_id)
    return ok(quote_service.to_read(updated))


@router.post("/{quote_id}/approve", response_model=Envelope[QuoteRead])
async def approve_quote(
    quote_id: uuid.UUID,
    current_user: User = Depends(require_roles(*_UNDERWRITERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    quote = await quote_service.get_quote(db, quote_id)
    await quote_service.assert_quote_access(db, quote, current_user)
    updated = await quote_service.approve_quote(db, quote_id, current_user)
    return ok(quote_service.to_read(updated))


@router.post("/{quote_id}/reject", response_model=Envelope[QuoteRead])
async def reject_quote(
    quote_id: uuid.UUID,
    payload: QuoteReject | None = None,
    current_user: User = Depends(require_roles(*_UNDERWRITERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    quote = await quote_service.get_quote(db, quote_id)
    await quote_service.assert_quote_access(db, quote, current_user)
    reason = payload.reason if payload else None
    updated = await quote_service.reject_quote(db, quote_id, current_user, reason)
    return ok(quote_service.to_read(updated))


@router.post("/{quote_id}/bind", response_model=Envelope[PolicyRead])
async def bind_quote(
    quote_id: uuid.UUID,
    payload: PolicyBindRequest | None = None,
    current_user: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    frequency = (
        payload.payment_frequency if payload else PaymentFrequency.monthly
    )
    policy = await policy_service.bind_quote(
        db, quote_id, current_user, payment_frequency=frequency
    )
    # Declaration PDF is a side effect — enqueue so bind stays fast, with an
    # inline fallback when Redis/Celery is unavailable.
    worker_tasks.enqueue(
        worker_tasks.generate_policy_declaration,
        str(policy.id),
        str(current_user.id),
        description=f"declaration for {policy.policy_number}",
    )
    return ok(await policy_service.to_read(db, policy))
