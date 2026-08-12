"""Customer management business logic."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import encrypt_pii, hash_password
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate


def _mask_ssn(last4: str | None) -> str | None:
    return f"***-**-{last4}" if last4 else None


def to_read(customer: Customer) -> CustomerRead:
    """Build a masked, user-enriched read model from a Customer ORM object."""
    user = customer.user
    return CustomerRead(
        id=customer.id,
        user_id=customer.user_id,
        first_name=user.first_name if user else None,
        last_name=user.last_name if user else None,
        email=user.email if user else None,
        phone=user.phone if user else None,
        date_of_birth=customer.date_of_birth,
        ssn_masked=_mask_ssn(customer.ssn_last4),
        dl_number=customer.dl_number,
        dl_state=customer.dl_state,
        dl_expiry=customer.dl_expiry,
        address_line1=customer.address_line1,
        address_line2=customer.address_line2,
        city=customer.city,
        state=customer.state,
        zip=customer.zip,
        country=customer.country,
        credit_score=customer.credit_score,
        risk_tier=customer.risk_tier,
        created_at=customer.created_at,
    )


async def create_customer(db: AsyncSession, payload: CustomerCreate) -> Customer:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise ConflictError(
            "An account with this email already exists.", code="EMAIL_TAKEN"
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        role=UserRole.customer,
    )
    customer = Customer(
        date_of_birth=payload.date_of_birth,
        ssn_last4=payload.ssn[-4:] if payload.ssn else None,
        ssn_encrypted=encrypt_pii(payload.ssn),
        dl_number=payload.dl_number,
        dl_state=payload.dl_state,
        dl_expiry=payload.dl_expiry,
        address_line1=payload.address_line1,
        address_line2=payload.address_line2,
        city=payload.city,
        state=payload.state,
        zip=payload.zip,
        country=payload.country,
    )
    user.customer = customer
    db.add(user)
    await db.commit()

    return await get_customer(db, customer.id)


async def list_customers(
    db: AsyncSession, *, page: int, per_page: int, search: str | None
) -> tuple[list[Customer], int]:
    stmt = select(Customer).join(User, Customer.user_id == User.id).options(
        selectinload(Customer.user)
    )
    count_stmt = select(func.count(Customer.id)).join(User, Customer.user_id == User.id)

    if search:
        pattern = f"%{search.lower()}%"
        condition = or_(
            func.lower(User.first_name).like(pattern),
            func.lower(User.last_name).like(pattern),
            func.lower(User.email).like(pattern),
        )
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = await db.scalar(count_stmt) or 0
    stmt = stmt.order_by(Customer.created_at.desc()).offset((page - 1) * per_page).limit(
        per_page
    )
    result = await db.scalars(stmt)
    return list(result.all()), total


async def get_customer(db: AsyncSession, customer_id: uuid.UUID) -> Customer:
    customer = await db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .options(selectinload(Customer.user))
    )
    if customer is None:
        raise NotFoundError("Customer not found.", code="CUSTOMER_NOT_FOUND")
    return customer


async def get_customer_by_user(db: AsyncSession, user_id: uuid.UUID) -> Customer:
    customer = await db.scalar(
        select(Customer)
        .where(Customer.user_id == user_id)
        .options(selectinload(Customer.user))
    )
    if customer is None:
        raise NotFoundError("Customer profile not found.", code="CUSTOMER_NOT_FOUND")
    return customer


async def update_customer(
    db: AsyncSession, customer_id: uuid.UUID, payload: CustomerUpdate
) -> Customer:
    customer = await get_customer(db, customer_id)

    data = payload.model_dump(exclude_unset=True)
    phone = data.pop("phone", None)
    for field, value in data.items():
        setattr(customer, field, value)
    if phone is not None and customer.user is not None:
        customer.user.phone = phone

    await db.commit()
    return await get_customer(db, customer_id)


async def deactivate_customer(db: AsyncSession, customer_id: uuid.UUID) -> None:
    customer = await get_customer(db, customer_id)
    if customer.user is not None:
        customer.user.is_active = False
    await db.commit()
