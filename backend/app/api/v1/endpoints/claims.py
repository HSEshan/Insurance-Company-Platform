"""Claims lifecycle endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ADJUSTER_AND_UP,
    MANAGER_AND_UP,
    get_current_user,
    require_roles,
)
from app.core.database import get_db
from app.models.enums import ClaimStatus, ClaimType, DocumentOwnerType, UserRole
from app.models.user import User
from app.schemas.claim import (
    ClaimApprove,
    ClaimAssign,
    ClaimCreate,
    ClaimDispute,
    ClaimListItem,
    ClaimNoteCreate,
    ClaimNoteRead,
    ClaimRead,
    ClaimReject,
    ClaimResolveDispute,
)
from app.schemas.common import Envelope, Meta, ok
from app.schemas.document import DocumentRead
from app.schemas.user import UserRead
from app.services import claim_service, document_service
from app.workers import tasks as worker_tasks

router = APIRouter(prefix="/claims", tags=["claims"])

_SUBMITTERS = (UserRole.customer, UserRole.agent, UserRole.super_admin)
_CLAIM_READERS = {
    UserRole.customer,
    UserRole.agent,
    UserRole.adjuster,
    UserRole.manager,
    UserRole.super_admin,
}


@router.get("/adjusters", response_model=Envelope[list[UserRead]])
async def list_adjusters(
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Directory of adjusters for the assign-claim UI."""
    rows = await db.scalars(
        select(User)
        .where(User.role == UserRole.adjuster, User.is_active.is_(True))
        .order_by(User.last_name, User.first_name)
    )
    return ok(list(rows.all()))


@router.get("", response_model=Envelope[list[ClaimListItem]])
async def list_claims(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: ClaimStatus | None = Query(None, alias="status"),
    claim_type: ClaimType | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.role not in _CLAIM_READERS:
        raise HTTPException(status_code=403, detail="Forbidden")
    claims, total = await claim_service.list_claims(
        db,
        current_user,
        page=page,
        per_page=per_page,
        status=status_filter,
        claim_type=claim_type,
    )
    return ok(
        [claim_service.to_list_item(c) for c in claims],
        meta=Meta(page=page, per_page=per_page, total=total),
    )


@router.post(
    "",
    response_model=Envelope[ClaimRead],
    status_code=status.HTTP_201_CREATED,
)
async def submit_claim(
    payload: ClaimCreate,
    current_user: User = Depends(require_roles(*_SUBMITTERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.submit_claim(db, current_user, payload)
    notes = await claim_service.list_notes(db, claim, current_user)
    return ok(claim_service.to_read(claim, notes))


@router.get("/{claim_id}", response_model=Envelope[ClaimRead])
async def get_claim(
    claim_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.get_claim(db, claim_id)
    await claim_service.assert_claim_access(db, claim, current_user)
    notes = await claim_service.list_notes(db, claim, current_user)
    return ok(claim_service.to_read(claim, notes))


@router.post("/{claim_id}/assign", response_model=Envelope[ClaimRead])
async def assign_claim(
    claim_id: uuid.UUID,
    payload: ClaimAssign,
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.assign_claim(db, claim_id, payload.adjuster_id)
    return ok(claim_service.to_read(claim))


@router.post("/{claim_id}/investigate", response_model=Envelope[ClaimRead])
async def investigate_claim(
    claim_id: uuid.UUID,
    current_user: User = Depends(require_roles(*ADJUSTER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.start_investigation(db, claim_id, current_user)
    return ok(claim_service.to_read(claim))


@router.post("/{claim_id}/request-info", response_model=Envelope[ClaimRead])
async def request_info(
    claim_id: uuid.UUID,
    payload: ClaimReject,
    current_user: User = Depends(require_roles(*ADJUSTER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Reuse ClaimReject shape {reason} for the info-request message.
    claim = await claim_service.request_info(
        db, claim_id, current_user, payload.reason
    )
    notes = await claim_service.list_notes(db, claim, current_user)
    return ok(claim_service.to_read(claim, notes))


@router.post("/{claim_id}/approve", response_model=Envelope[ClaimRead])
async def approve_claim(
    claim_id: uuid.UUID,
    payload: ClaimApprove,
    current_user: User = Depends(require_roles(*ADJUSTER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.approve_claim(db, claim_id, current_user, payload)
    worker_tasks.enqueue(
        worker_tasks.generate_claim_decision_letter,
        str(claim.id),
        "approved",
        str(current_user.id),
        description=f"approval letter for {claim.claim_number}",
    )
    return ok(claim_service.to_read(claim))


@router.post("/{claim_id}/reject", response_model=Envelope[ClaimRead])
async def reject_claim(
    claim_id: uuid.UUID,
    payload: ClaimReject,
    current_user: User = Depends(require_roles(*ADJUSTER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.reject_claim(db, claim_id, current_user, payload)
    worker_tasks.enqueue(
        worker_tasks.generate_claim_decision_letter,
        str(claim.id),
        "rejected",
        str(current_user.id),
        description=f"rejection letter for {claim.claim_number}",
    )
    notes = await claim_service.list_notes(db, claim, current_user)
    return ok(claim_service.to_read(claim, notes))


@router.post("/{claim_id}/dispute", response_model=Envelope[ClaimRead])
async def dispute_claim(
    claim_id: uuid.UUID,
    payload: ClaimDispute,
    current_user: User = Depends(require_roles(UserRole.customer, UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.dispute_claim(
        db, claim_id, current_user, payload.reason
    )
    notes = await claim_service.list_notes(db, claim, current_user)
    return ok(claim_service.to_read(claim, notes))


@router.post("/{claim_id}/resolve-dispute", response_model=Envelope[ClaimRead])
async def resolve_dispute(
    claim_id: uuid.UUID,
    payload: ClaimResolveDispute,
    current_user: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.resolve_dispute(db, claim_id, current_user, payload)
    # A resolved dispute is a fresh determination, so it gets its own letter.
    worker_tasks.enqueue(
        worker_tasks.generate_claim_decision_letter,
        str(claim.id),
        str(claim.status),
        str(current_user.id),
        description=f"dispute decision letter for {claim.claim_number}",
    )
    notes = await claim_service.list_notes(db, claim, current_user)
    return ok(claim_service.to_read(claim, notes))


@router.post("/{claim_id}/pay", response_model=Envelope[ClaimRead])
async def pay_claim(
    claim_id: uuid.UUID,
    current_user: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.pay_claim(db, claim_id, current_user)
    notes = await claim_service.list_notes(db, claim, current_user)
    return ok(claim_service.to_read(claim, notes))


@router.post("/{claim_id}/close", response_model=Envelope[ClaimRead])
async def close_claim(
    claim_id: uuid.UUID,
    _: User = Depends(
        require_roles(
            UserRole.agent,
            UserRole.adjuster,
            UserRole.manager,
            UserRole.super_admin,
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.close_claim(db, claim_id)
    return ok(claim_service.to_read(claim))


@router.get("/{claim_id}/notes", response_model=Envelope[list[ClaimNoteRead]])
async def get_notes(
    claim_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    claim = await claim_service.get_claim(db, claim_id)
    await claim_service.assert_claim_access(db, claim, current_user)
    notes = await claim_service.list_notes(db, claim, current_user)
    return ok([ClaimNoteRead.model_validate(n) for n in notes])


@router.post(
    "/{claim_id}/notes",
    response_model=Envelope[ClaimNoteRead],
    status_code=status.HTTP_201_CREATED,
)
async def add_note(
    claim_id: uuid.UUID,
    payload: ClaimNoteCreate,
    current_user: User = Depends(require_roles(*ADJUSTER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    note = await claim_service.add_note(db, claim_id, current_user, payload)
    return ok(ClaimNoteRead.model_validate(note))


@router.get("/{claim_id}/documents", response_model=Envelope[list[DocumentRead]])
async def list_claim_documents(
    claim_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    documents = await document_service.list_documents(
        db,
        current_user,
        owner_type=DocumentOwnerType.claim,
        owner_id=claim_id,
    )
    return ok([DocumentRead.model_validate(d) for d in documents])
