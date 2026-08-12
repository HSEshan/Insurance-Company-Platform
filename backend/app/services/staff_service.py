"""Super-Admin staff / employee management.

Customers self-register; staff never do. Creation issues a temporary password
with ``must_reset_password=True`` and emails it (MailHog in local compose).
"""

from __future__ import annotations

import secrets
import string
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.models.claim import Claim
from app.models.enums import ClaimStatus, PolicyStatus, UserRole
from app.models.policy import Policy
from app.models.user import User
from app.schemas.staff import (
    STAFF_ROLES,
    OpenWorkSummary,
    StaffCreate,
    StaffCreateResult,
    StaffDeactivate,
    StaffUpdate,
)
from app.schemas.user import UserRead
from app.services import audit_service, email_service

OPEN_CLAIM_STATUSES = frozenset(
    {
        ClaimStatus.submitted,
        ClaimStatus.assigned,
        ClaimStatus.investigating,
        ClaimStatus.info_requested,
        ClaimStatus.approved,
        ClaimStatus.disputed,
    }
)
# Policies that still need an owning agent on the book.
ACTIVE_BOOK_STATUSES = frozenset(
    {PolicyStatus.active, PolicyStatus.lapsed, PolicyStatus.under_review}
)


def generate_temp_password(length: int = 14) -> str:
    """Readable temp password: letters + digits, excludes ambiguous characters."""
    alphabet = string.ascii_letters + string.digits
    alphabet = alphabet.replace("O", "").replace("0", "").replace("l", "").replace("I", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def get_staff_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or user.role not in STAFF_ROLES:
        raise NotFoundError("Staff user not found.", code="STAFF_NOT_FOUND")
    return user


async def list_staff(
    db: AsyncSession,
    *,
    role: UserRole | None = None,
    include_inactive: bool = True,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[User], int]:
    stmt = select(User).where(User.role.in_(STAFF_ROLES))
    if role is not None:
        if role not in STAFF_ROLES:
            raise AppError("Invalid staff role filter.", code="INVALID_ROLE", status_code=422)
        stmt = stmt.where(User.role == role)
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))

    count_stmt = select(func.count()).select_from(User).where(User.role.in_(STAFF_ROLES))
    if role is not None:
        count_stmt = count_stmt.where(User.role == role)
    if not include_inactive:
        count_stmt = count_stmt.where(User.is_active.is_(True))
    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.scalars(
            stmt.order_by(User.last_name.asc(), User.first_name.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()
    return list(rows), total


async def open_work(db: AsyncSession, user: User) -> OpenWorkSummary:
    policies = 0
    claims = 0
    if user.role in {UserRole.agent, UserRole.manager, UserRole.super_admin}:
        # Managers rarely own a book, but count any policies still pointing at them.
        policies = int(
            await db.scalar(
                select(func.count())
                .select_from(Policy)
                .where(
                    Policy.agent_id == user.id,
                    Policy.status.in_(ACTIVE_BOOK_STATUSES),
                )
            )
            or 0
        )
    if user.role in {UserRole.adjuster, UserRole.manager, UserRole.super_admin}:
        claims = int(
            await db.scalar(
                select(func.count())
                .select_from(Claim)
                .where(
                    Claim.adjuster_id == user.id,
                    Claim.status.in_(OPEN_CLAIM_STATUSES),
                )
            )
            or 0
        )
    # Spec ties reassignment to agent_id / adjuster_id roles specifically.
    requires_agent = user.role == UserRole.agent and policies > 0
    requires_adjuster = user.role == UserRole.adjuster and claims > 0
    # If a manager somehow owns work, still require reassignment.
    if user.role in {UserRole.manager, UserRole.super_admin}:
        requires_agent = policies > 0
        requires_adjuster = claims > 0
    return OpenWorkSummary(
        policies=policies,
        open_claims=claims,
        requires_agent_reassign=requires_agent,
        requires_adjuster_reassign=requires_adjuster,
    )


async def _count_active_super_admins(db: AsyncSession) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.super_admin,
                User.is_active.is_(True),
            )
        )
        or 0
    )


async def _assert_not_last_super_admin(
    db: AsyncSession, user: User, *, demoting: bool, deactivating: bool
) -> None:
    if user.role != UserRole.super_admin:
        return
    if not demoting and not deactivating:
        return
    if await _count_active_super_admins(db) <= 1:
        raise AppError(
            "Cannot demote or deactivate the last active Super Admin.",
            code="LAST_SUPER_ADMIN",
            status_code=409,
        )


async def _resolve_reassign_target(
    db: AsyncSession,
    *,
    target_id: uuid.UUID,
    expected_role: UserRole,
    label: str,
) -> User:
    """Managers/super_admins may temporarily hold a book during handoff."""
    target = await db.scalar(select(User).where(User.id == target_id))
    allowed = {expected_role, UserRole.manager, UserRole.super_admin}
    if target is None or not target.is_active or target.role not in allowed:
        raise AppError(
            f"Invalid {label} reassignment target.",
            code="INVALID_REASSIGN_TARGET",
            status_code=422,
        )
    return target


async def _reassign_open_work(
    db: AsyncSession,
    user: User,
    *,
    reassign_agent_id: uuid.UUID | None,
    reassign_adjuster_id: uuid.UUID | None,
    work: OpenWorkSummary,
) -> None:
    if work.requires_agent_reassign:
        if reassign_agent_id is None:
            raise AppError(
                f"This employee still owns {work.policies} policy(ies). "
                "Provide reassign_agent_id before continuing.",
                code="REASSIGN_REQUIRED",
                status_code=409,
            )
        if reassign_agent_id == user.id:
            raise AppError(
                "Cannot reassign work to the same employee.",
                code="INVALID_REASSIGN_TARGET",
                status_code=422,
            )
        await _resolve_reassign_target(
            db,
            target_id=reassign_agent_id,
            expected_role=UserRole.agent,
            label="agent",
        )
        await db.execute(
            update(Policy)
            .where(
                Policy.agent_id == user.id,
                Policy.status.in_(ACTIVE_BOOK_STATUSES),
            )
            .values(agent_id=reassign_agent_id)
        )

    if work.requires_adjuster_reassign:
        if reassign_adjuster_id is None:
            raise AppError(
                f"This employee still owns {work.open_claims} open claim(s). "
                "Provide reassign_adjuster_id before continuing.",
                code="REASSIGN_REQUIRED",
                status_code=409,
            )
        if reassign_adjuster_id == user.id:
            raise AppError(
                "Cannot reassign work to the same employee.",
                code="INVALID_REASSIGN_TARGET",
                status_code=422,
            )
        await _resolve_reassign_target(
            db,
            target_id=reassign_adjuster_id,
            expected_role=UserRole.adjuster,
            label="adjuster",
        )
        await db.execute(
            update(Claim)
            .where(
                Claim.adjuster_id == user.id,
                Claim.status.in_(OPEN_CLAIM_STATUSES),
            )
            .values(adjuster_id=reassign_adjuster_id)
        )


async def create_staff(
    db: AsyncSession, actor: User, payload: StaffCreate
) -> StaffCreateResult:
    if actor.role != UserRole.super_admin:
        raise ForbiddenError("Only a Super Admin can create staff accounts.")

    existing = await db.scalar(select(User).where(User.email == str(payload.email)))
    if existing is not None:
        raise ConflictError(
            "An account with this email already exists.", code="EMAIL_TAKEN"
        )

    temp_password = generate_temp_password()
    user = User(
        email=str(payload.email),
        hashed_password=hash_password(temp_password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        role=payload.role,
        is_active=True,
        must_reset_password=True,
    )
    db.add(user)
    await db.flush()
    await audit_service.record(
        db,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        actor=actor,
        new_value={
            "email": user.email,
            "role": user.role.value,
            "must_reset_password": True,
        },
    )
    await db.commit()
    await db.refresh(user)

    email_sent = await email_service.send_email(
        to=user.email,
        subject="Your InsureCo staff account",
        body=(
            f"Hello {user.first_name},\n\n"
            f"A Super Admin created a staff account for you on InsureCo.\n\n"
            f"Sign in at {settings.FRONTEND_URL}/login with:\n"
            f"  Email: {user.email}\n"
            f"  Temporary password: {temp_password}\n\n"
            "You will be required to set a new password on first sign-in.\n\n"
            "— InsureCo"
        ),
    )
    return StaffCreateResult(
        user=UserRead.model_validate(user),
        temporary_password=temp_password,
        email_sent=email_sent,
    )


async def update_staff(
    db: AsyncSession, actor: User, user_id: uuid.UUID, payload: StaffUpdate
) -> User:
    if actor.role != UserRole.super_admin:
        raise ForbiddenError("Only a Super Admin can update staff accounts.")

    user = await get_staff_user(db, user_id)
    if user.id == actor.id and payload.role is not None and payload.role != user.role:
        raise ForbiddenError("You cannot change your own role.")

    old = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "role": user.role.value,
    }

    role_changing = payload.role is not None and payload.role != user.role
    if role_changing:
        await _assert_not_last_super_admin(
            db, user, demoting=payload.role != UserRole.super_admin, deactivating=False
        )
        # Leaving a role that owns open work requires reassignment first.
        work = await open_work(db, user)
        leaving_agent = user.role == UserRole.agent and payload.role != UserRole.agent
        leaving_adjuster = (
            user.role == UserRole.adjuster and payload.role != UserRole.adjuster
        )
        if leaving_agent or leaving_adjuster or (
            user.role in {UserRole.manager, UserRole.super_admin}
            and (work.policies or work.open_claims)
        ):
            # Narrow the required flags to the work being abandoned.
            effective = OpenWorkSummary(
                policies=work.policies,
                open_claims=work.open_claims,
                requires_agent_reassign=leaving_agent and work.policies > 0
                or (
                    user.role in {UserRole.manager, UserRole.super_admin}
                    and work.policies > 0
                ),
                requires_adjuster_reassign=leaving_adjuster and work.open_claims > 0
                or (
                    user.role in {UserRole.manager, UserRole.super_admin}
                    and work.open_claims > 0
                ),
            )
            await _reassign_open_work(
                db,
                user,
                reassign_agent_id=payload.reassign_agent_id,
                reassign_adjuster_id=payload.reassign_adjuster_id,
                work=effective,
            )

    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name
    if payload.phone is not None:
        user.phone = payload.phone
    if payload.role is not None:
        user.role = payload.role

    await audit_service.record(
        db,
        action="user.role_changed" if role_changing else "user.updated",
        entity_type="user",
        entity_id=user.id,
        actor=actor,
        old_value=old,
        new_value={
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "role": user.role.value,
            "reassign_agent_id": str(payload.reassign_agent_id)
            if payload.reassign_agent_id
            else None,
            "reassign_adjuster_id": str(payload.reassign_adjuster_id)
            if payload.reassign_adjuster_id
            else None,
        },
    )
    await db.commit()
    await db.refresh(user)
    return user


async def deactivate_staff(
    db: AsyncSession, actor: User, user_id: uuid.UUID, payload: StaffDeactivate
) -> User:
    if actor.role != UserRole.super_admin:
        raise ForbiddenError("Only a Super Admin can deactivate staff accounts.")
    if user_id == actor.id:
        raise ForbiddenError("You cannot deactivate your own account.")

    user = await get_staff_user(db, user_id)
    if not user.is_active:
        raise AppError(
            "This account is already deactivated.",
            code="ALREADY_INACTIVE",
            status_code=409,
        )

    await _assert_not_last_super_admin(db, user, demoting=False, deactivating=True)
    work = await open_work(db, user)
    await _reassign_open_work(
        db,
        user,
        reassign_agent_id=payload.reassign_agent_id,
        reassign_adjuster_id=payload.reassign_adjuster_id,
        work=work,
    )

    user.is_active = False
    await audit_service.record(
        db,
        action="user.deactivated",
        entity_type="user",
        entity_id=user.id,
        actor=actor,
        old_value={"is_active": True, "role": user.role.value},
        new_value={
            "is_active": False,
            "reassign_agent_id": str(payload.reassign_agent_id)
            if payload.reassign_agent_id
            else None,
            "reassign_adjuster_id": str(payload.reassign_adjuster_id)
            if payload.reassign_adjuster_id
            else None,
        },
    )
    await db.commit()
    await db.refresh(user)
    return user


async def reactivate_staff(db: AsyncSession, actor: User, user_id: uuid.UUID) -> User:
    if actor.role != UserRole.super_admin:
        raise ForbiddenError("Only a Super Admin can reactivate staff accounts.")

    user = await get_staff_user(db, user_id)
    if user.is_active:
        raise AppError(
            "This account is already active.",
            code="ALREADY_ACTIVE",
            status_code=409,
        )
    user.is_active = True
    await audit_service.record(
        db,
        action="user.reactivated",
        entity_type="user",
        entity_id=user.id,
        actor=actor,
        old_value={"is_active": False},
        new_value={"is_active": True},
    )
    await db.commit()
    await db.refresh(user)
    return user


async def reset_temp_password(
    db: AsyncSession, actor: User, user_id: uuid.UUID
) -> StaffCreateResult:
    if actor.role != UserRole.super_admin:
        raise ForbiddenError("Only a Super Admin can reset staff passwords.")

    user = await get_staff_user(db, user_id)
    if not user.is_active:
        raise AppError(
            "Cannot reset password for a deactivated account.",
            code="ACCOUNT_INACTIVE",
            status_code=409,
        )

    temp_password = generate_temp_password()
    user.hashed_password = hash_password(temp_password)
    user.must_reset_password = True
    await audit_service.record(
        db,
        action="user.password_reset",
        entity_type="user",
        entity_id=user.id,
        actor=actor,
        new_value={"must_reset_password": True},
    )
    await db.commit()
    await db.refresh(user)

    email_sent = await email_service.send_email(
        to=user.email,
        subject="Your InsureCo password was reset",
        body=(
            f"Hello {user.first_name},\n\n"
            f"A Super Admin reset your InsureCo password.\n\n"
            f"Temporary password: {temp_password}\n\n"
            "Sign in and choose a new password immediately.\n\n"
            "— InsureCo"
        ),
    )
    return StaffCreateResult(
        user=UserRead.model_validate(user),
        temporary_password=temp_password,
        email_sent=email_sent,
    )
