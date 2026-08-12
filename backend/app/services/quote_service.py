"""Quote lifecycle: create/rate, underwriting workflow, and listing."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.customer import Customer
from app.models.enums import (
    NotificationType,
    PolicyType,
    QuoteStatus,
    RiskTier,
    UserRole,
)
from app.models.quote import Quote
from app.models.user import User
from app.schemas.quote import QuoteCreate, QuoteRead, QuoteUpdate
from app.services import audit_service, notification_service
from app.services.rating import (
    AutoRatingInput,
    HomeRatingInput,
    LifeRatingInput,
    rate_quote,
)

QUOTE_VALIDITY_DAYS = 30
# Annual premium above this requires manager (or super_admin) to approve.
LARGE_PREMIUM_THRESHOLD = Decimal("10000")

_ALLOWED_TRANSITIONS: dict[QuoteStatus, set[QuoteStatus]] = {
    QuoteStatus.draft: {QuoteStatus.pending_review},
    QuoteStatus.pending_review: {QuoteStatus.approved, QuoteStatus.rejected},
    QuoteStatus.approved: {QuoteStatus.bound, QuoteStatus.expired},
}


def to_read(quote: Quote) -> QuoteRead:
    factors = None
    if quote.rating_factors is not None:
        factors = quote.rating_factors
    return QuoteRead(
        id=quote.id,
        customer_id=quote.customer_id,
        policy_type=quote.policy_type,
        status=quote.status,
        quoted_premium=quote.quoted_premium,
        monthly_premium=quote.monthly_premium,
        risk_tier=quote.risk_tier,
        rating_inputs=quote.rating_inputs,
        rating_factors=factors,
        policy_details=quote.policy_details,
        decline_reasons=quote.decline_reasons,
        effective_date=quote.effective_date,
        expiry_date=quote.expiry_date,
        agent_id=quote.agent_id,
        underwriter_id=quote.underwriter_id,
        notes=quote.notes,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


def _rating_and_details(
    payload: QuoteCreate | QuoteUpdate, policy_type: PolicyType
) -> tuple[AutoRatingInput | HomeRatingInput | LifeRatingInput, dict[str, Any]]:
    if policy_type == PolicyType.auto:
        assert payload.auto_rating is not None and payload.auto_details is not None
        return payload.auto_rating, payload.auto_details.model_dump(mode="json")
    if policy_type == PolicyType.home:
        assert payload.home_rating is not None and payload.home_details is not None
        return payload.home_rating, payload.home_details.model_dump(mode="json")
    assert payload.life_rating is not None and payload.life_details is not None
    return payload.life_rating, payload.life_details.model_dump(mode="json")


def _apply_rating(quote: Quote, policy_type: PolicyType, rating_input: Any) -> None:
    result = rate_quote(policy_type, rating_input)
    quote.quoted_premium = result.annual_premium
    quote.monthly_premium = result.monthly_premium
    quote.risk_tier = result.risk_tier
    quote.rating_inputs = rating_input.model_dump(mode="json")
    quote.rating_factors = [f.model_dump(mode="json") for f in result.factors]
    quote.decline_reasons = result.decline_reasons or None
    if result.declined:
        quote.status = QuoteStatus.rejected
        quote.risk_tier = RiskTier.declined


async def _resolve_customer_id(
    db: AsyncSession, actor: User, customer_id: uuid.UUID | None
) -> uuid.UUID:
    if actor.role == UserRole.customer:
        customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
        if customer is None:
            raise NotFoundError("Customer profile not found.", code="CUSTOMER_NOT_FOUND")
        if customer_id is not None and customer_id != customer.id:
            raise ForbiddenError("Customers may only create quotes for themselves.")
        return customer.id

    if customer_id is None:
        raise AppError(
            "customer_id is required when creating a quote as staff.",
            code="CUSTOMER_REQUIRED",
        )
    customer = await db.scalar(select(Customer).where(Customer.id == customer_id))
    if customer is None:
        raise NotFoundError("Customer not found.", code="CUSTOMER_NOT_FOUND")
    return customer.id


async def _assert_customer_insurable(db: AsyncSession, customer_id: uuid.UUID) -> Customer:
    customer = await db.scalar(select(Customer).where(Customer.id == customer_id))
    if customer is None:
        raise NotFoundError("Customer not found.", code="CUSTOMER_NOT_FOUND")
    if customer.risk_tier == RiskTier.declined:
        raise AppError(
            "Customer is marked declined and cannot be quoted.",
            code="CUSTOMER_DECLINED",
            status_code=422,
        )
    return customer


async def create_quote(db: AsyncSession, actor: User, payload: QuoteCreate) -> Quote:
    customer_id = await _resolve_customer_id(db, actor, payload.customer_id)
    await _assert_customer_insurable(db, customer_id)

    rating_input, details = _rating_and_details(payload, payload.policy_type)
    today = datetime.now(UTC).date()

    quote = Quote(
        customer_id=customer_id,
        policy_type=payload.policy_type,
        status=QuoteStatus.draft,
        effective_date=payload.effective_date,
        expiry_date=today + timedelta(days=QUOTE_VALIDITY_DAYS),
        agent_id=actor.id if actor.role != UserRole.customer else None,
        notes=payload.notes,
        policy_details=details,
    )
    _apply_rating(quote, payload.policy_type, rating_input)
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote


async def get_quote(db: AsyncSession, quote_id: uuid.UUID) -> Quote:
    quote = await db.scalar(select(Quote).where(Quote.id == quote_id))
    if quote is None:
        raise NotFoundError("Quote not found.", code="QUOTE_NOT_FOUND")
    return quote


async def assert_quote_access(db: AsyncSession, quote: Quote, actor: User) -> None:
    if actor.role in {UserRole.agent, UserRole.manager, UserRole.super_admin}:
        return
    if actor.role == UserRole.customer:
        customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
        if customer is not None and customer.id == quote.customer_id:
            return
    raise ForbiddenError("You do not have access to this quote.")


async def list_quotes(
    db: AsyncSession,
    actor: User,
    *,
    page: int,
    per_page: int,
    status: QuoteStatus | None = None,
    policy_type: PolicyType | None = None,
    customer_id: uuid.UUID | None = None,
) -> tuple[list[Quote], int]:
    stmt = select(Quote)
    count_stmt = select(func.count(Quote.id))

    if actor.role == UserRole.customer:
        customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
        if customer is None:
            return [], 0
        stmt = stmt.where(Quote.customer_id == customer.id)
        count_stmt = count_stmt.where(Quote.customer_id == customer.id)
    elif customer_id is not None:
        stmt = stmt.where(Quote.customer_id == customer_id)
        count_stmt = count_stmt.where(Quote.customer_id == customer_id)

    if status is not None:
        stmt = stmt.where(Quote.status == status)
        count_stmt = count_stmt.where(Quote.status == status)
    if policy_type is not None:
        stmt = stmt.where(Quote.policy_type == policy_type)
        count_stmt = count_stmt.where(Quote.policy_type == policy_type)

    total = await db.scalar(count_stmt) or 0
    stmt = stmt.order_by(Quote.created_at.desc()).offset((page - 1) * per_page).limit(
        per_page
    )
    rows = list((await db.scalars(stmt)).all())
    return rows, total


async def update_quote(
    db: AsyncSession, quote_id: uuid.UUID, payload: QuoteUpdate
) -> Quote:
    quote = await get_quote(db, quote_id)
    if quote.status != QuoteStatus.draft:
        raise AppError(
            "Only draft quotes can be updated.",
            code="QUOTE_NOT_EDITABLE",
            status_code=409,
        )

    data = payload.model_dump(exclude_unset=True)
    if "effective_date" in data:
        quote.effective_date = data["effective_date"]
    if "notes" in data:
        quote.notes = data["notes"]

    # Re-rate when either rating or details for the LOB are supplied.
    if quote.policy_type == PolicyType.auto and (
        payload.auto_rating is not None or payload.auto_details is not None
    ):
        rating = payload.auto_rating or AutoRatingInput.model_validate(quote.rating_inputs)
        if payload.auto_details is not None:
            quote.policy_details = payload.auto_details.model_dump(mode="json")
        _apply_rating(quote, PolicyType.auto, rating)
    elif quote.policy_type == PolicyType.home and (
        payload.home_rating is not None or payload.home_details is not None
    ):
        rating = payload.home_rating or HomeRatingInput.model_validate(quote.rating_inputs)
        if payload.home_details is not None:
            quote.policy_details = payload.home_details.model_dump(mode="json")
        _apply_rating(quote, PolicyType.home, rating)
    elif quote.policy_type == PolicyType.life and (
        payload.life_rating is not None or payload.life_details is not None
    ):
        rating = payload.life_rating or LifeRatingInput.model_validate(quote.rating_inputs)
        if payload.life_details is not None:
            quote.policy_details = payload.life_details.model_dump(mode="json")
        _apply_rating(quote, PolicyType.life, rating)

    await db.commit()
    await db.refresh(quote)
    return quote


def _transition(quote: Quote, target: QuoteStatus) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(quote.status, set())
    if target not in allowed:
        raise AppError(
            f"Cannot transition quote from '{quote.status}' to '{target}'.",
            code="INVALID_QUOTE_TRANSITION",
            status_code=409,
        )
    if (
        quote.expiry_date
        and quote.expiry_date < date.today()
        and target != QuoteStatus.expired
    ):
        raise AppError(
            "Quote has expired.",
            code="QUOTE_EXPIRED",
            status_code=409,
        )
    quote.status = target


async def submit_quote(db: AsyncSession, quote_id: uuid.UUID) -> Quote:
    quote = await get_quote(db, quote_id)
    if quote.risk_tier == RiskTier.declined or quote.decline_reasons:
        raise AppError(
            "Declined quotes cannot be submitted for underwriting.",
            code="QUOTE_DECLINED",
            status_code=422,
        )
    _transition(quote, QuoteStatus.pending_review)
    await db.commit()
    await db.refresh(quote)
    return quote


async def approve_quote(db: AsyncSession, quote_id: uuid.UUID, actor: User) -> Quote:
    quote = await get_quote(db, quote_id)
    premium = quote.quoted_premium or Decimal("0")
    if premium > LARGE_PREMIUM_THRESHOLD and actor.role not in {
        UserRole.manager,
        UserRole.super_admin,
    }:
        raise ForbiddenError(
            f"Quotes with annual premium over ${LARGE_PREMIUM_THRESHOLD} "
            "require manager approval."
        )
    old_status = quote.status.value
    _transition(quote, QuoteStatus.approved)
    quote.underwriter_id = actor.id
    await audit_service.record(
        db,
        action="quote.approved",
        entity_type="quote",
        entity_id=quote.id,
        actor=actor,
        old_value={"status": old_status},
        new_value={"status": QuoteStatus.approved.value},
    )
    notif = await notification_service.notify_customer(
        db,
        quote.customer_id,
        notification_type=NotificationType.quote_ready,
        title="Quote approved",
        body=(
            f"Your {quote.policy_type.value} quote is approved and ready to bind."
        ),
        related_entity_type="quote",
        related_entity_id=quote.id,
    )
    await db.commit()
    await db.refresh(quote)
    if notif:
        notification_service.queue_email(notif.id)
    return quote


async def reject_quote(
    db: AsyncSession, quote_id: uuid.UUID, actor: User, reason: str | None
) -> Quote:
    quote = await get_quote(db, quote_id)
    _transition(quote, QuoteStatus.rejected)
    quote.underwriter_id = actor.id
    if reason:
        note = quote.notes or ""
        quote.notes = f"{note}\n[Rejected] {reason}".strip()
        quote.decline_reasons = (quote.decline_reasons or []) + [reason]
    await db.commit()
    await db.refresh(quote)
    return quote
