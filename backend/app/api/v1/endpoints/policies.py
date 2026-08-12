"""Policy list/detail, cancellation, and endorsement endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AGENT_AND_UP, MANAGER_AND_UP, get_current_user, require_roles
from app.core.database import get_db
from app.models.enums import DocumentOwnerType, PolicyStatus, PolicyType, UserRole
from app.models.user import User
from app.schemas.common import Envelope, Meta, ok
from app.schemas.document import DocumentRead
from app.schemas.endorsement import (
    EndorsementCreate,
    EndorsementRead,
    EndorsementReject,
)
from app.schemas.payment import PaymentRead
from app.schemas.policy import PolicyCancel, PolicyListItem, PolicyRead
from app.services import (
    document_service,
    endorsement_service,
    payment_service,
    policy_service,
)

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=Envelope[list[PolicyListItem]])
async def list_policies(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: PolicyStatus | None = Query(None, alias="status"),
    policy_type: PolicyType | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.role not in {
        UserRole.customer,
        UserRole.agent,
        UserRole.manager,
        UserRole.super_admin,
        UserRole.adjuster,
    }:
        raise HTTPException(status_code=403, detail="Forbidden")

    policies, total = await policy_service.list_policies(
        db,
        current_user,
        page=page,
        per_page=per_page,
        status=status_filter,
        policy_type=policy_type,
        customer_id=customer_id,
    )
    return ok(
        [policy_service.to_list_item(p) for p in policies],
        meta=Meta(page=page, per_page=per_page, total=total),
    )


@router.get("/{policy_id}", response_model=Envelope[PolicyRead])
async def get_policy(
    policy_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    policy = await policy_service.get_policy(db, policy_id)
    await policy_service.assert_policy_access(db, policy, current_user)
    return ok(await policy_service.to_read(db, policy))


@router.post("/{policy_id}/cancel", response_model=Envelope[PolicyRead])
async def cancel_policy(
    policy_id: uuid.UUID,
    payload: PolicyCancel,
    current_user: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    policy = await policy_service.cancel_policy(
        db, policy_id, payload.reason, current_user
    )
    return ok(await policy_service.to_read(db, policy))


@router.post("/{policy_id}/reinstate", response_model=Envelope[PolicyRead])
async def reinstate_policy(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    policy = await policy_service.reinstate_policy(db, policy_id, current_user)
    return ok(await policy_service.to_read(db, policy))


@router.get("/{policy_id}/payments", response_model=Envelope[list[PaymentRead]])
async def list_policy_payments(
    policy_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Premium payment history for one policy."""
    policy = await policy_service.get_policy(db, policy_id)
    await policy_service.assert_policy_access(db, policy, current_user)
    payments, _ = await payment_service.list_payments(
        db, current_user, policy_id=policy_id, limit=200
    )
    return ok(payments)


@router.get("/{policy_id}/documents", response_model=Envelope[list[DocumentRead]])
async def list_policy_documents(
    policy_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    documents = await document_service.list_documents(
        db,
        current_user,
        owner_type=DocumentOwnerType.policy,
        owner_id=policy_id,
    )
    return ok([DocumentRead.model_validate(d) for d in documents])


# --------------------------------------------------------------------------- #
# Endorsements
# --------------------------------------------------------------------------- #
@router.get(
    "/{policy_id}/endorsements",
    response_model=Envelope[list[EndorsementRead]],
)
async def list_endorsements(
    policy_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    policy = await policy_service.get_policy(db, policy_id)
    await policy_service.assert_policy_access(db, policy, current_user)
    rows = await endorsement_service.list_endorsements(db, policy_id)
    return ok([endorsement_service.to_read(e) for e in rows])


@router.post(
    "/{policy_id}/endorsements",
    response_model=Envelope[EndorsementRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_endorsement(
    policy_id: uuid.UUID,
    payload: EndorsementCreate,
    current_user: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    endorsement = await endorsement_service.create_endorsement(
        db, policy_id, current_user, payload
    )
    return ok(endorsement_service.to_read(endorsement))


@router.post(
    "/{policy_id}/endorsements/{endorsement_id}/approve",
    response_model=Envelope[EndorsementRead],
)
async def approve_endorsement(
    policy_id: uuid.UUID,
    endorsement_id: uuid.UUID,
    current_user: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Role gate is agent+; service enforces manager for large premium increases.
    endorsement = await endorsement_service.approve_endorsement(
        db, policy_id, endorsement_id, current_user
    )
    return ok(endorsement_service.to_read(endorsement))


@router.post(
    "/{policy_id}/endorsements/{endorsement_id}/reject",
    response_model=Envelope[EndorsementRead],
)
async def reject_endorsement(
    policy_id: uuid.UUID,
    endorsement_id: uuid.UUID,
    payload: EndorsementReject | None = None,
    current_user: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    reason = payload.reason if payload else None
    endorsement = await endorsement_service.reject_endorsement(
        db, policy_id, endorsement_id, current_user, reason
    )
    return ok(endorsement_service.to_read(endorsement))
