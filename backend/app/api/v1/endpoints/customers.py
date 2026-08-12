"""Customer management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AGENT_AND_UP,
    MANAGER_AND_UP,
    get_current_user,
    require_roles,
)
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import Envelope, Meta, ok
from app.schemas.customer import (
    CustomerCreate,
    CustomerListItem,
    CustomerRead,
    CustomerUpdate,
)
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/me", response_model=Envelope[CustomerRead])
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    customer = await customer_service.get_customer_by_user(db, current_user.id)
    return ok(customer_service.to_read(customer))


@router.patch("/me", response_model=Envelope[CustomerRead])
async def update_my_profile(
    payload: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    customer = await customer_service.get_customer_by_user(db, current_user.id)
    updated = await customer_service.update_customer(db, customer.id, payload)
    return ok(customer_service.to_read(updated))


@router.get("", response_model=Envelope[list[CustomerListItem]])
async def list_customers(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=100),
    _: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    customers, total = await customer_service.list_customers(
        db, page=page, per_page=per_page, search=search
    )
    # Name/email live on the related user record, so build list items explicitly.
    enriched = [
        CustomerListItem(
            id=c.id,
            first_name=c.user.first_name if c.user else None,
            last_name=c.user.last_name if c.user else None,
            email=c.user.email if c.user else None,
            city=c.city,
            state=c.state,
            risk_tier=c.risk_tier,
            created_at=c.created_at,
        )
        for c in customers
    ]
    return ok(enriched, meta=Meta(page=page, per_page=per_page, total=total))


@router.post(
    "",
    response_model=Envelope[CustomerRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_customer(
    payload: CustomerCreate,
    _: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    customer = await customer_service.create_customer(db, payload)
    return ok(customer_service.to_read(customer))


@router.get("/{customer_id}", response_model=Envelope[CustomerRead])
async def get_customer(
    customer_id: uuid.UUID,
    _: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    customer = await customer_service.get_customer(db, customer_id)
    return ok(customer_service.to_read(customer))


@router.patch("/{customer_id}", response_model=Envelope[CustomerRead])
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    _: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    customer = await customer_service.update_customer(db, customer_id, payload)
    return ok(customer_service.to_read(customer))


@router.delete("/{customer_id}", response_model=Envelope[dict])
async def deactivate_customer(
    customer_id: uuid.UUID,
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await customer_service.deactivate_customer(db, customer_id)
    return ok({"message": "Customer deactivated."})
