"""Reusable FastAPI dependencies: DB session, auth, and RBAC."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.enums import UserRole
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

# Convenience role groups mirroring the permission matrix in specs.md.
AGENT_AND_UP: set[UserRole] = {UserRole.agent, UserRole.manager, UserRole.super_admin}
ADJUSTER_AND_UP: set[UserRole] = {
    UserRole.adjuster,
    UserRole.manager,
    UserRole.super_admin,
}
MANAGER_AND_UP: set[UserRole] = {UserRole.manager, UserRole.super_admin}
SUPER_ADMIN_ONLY: set[UserRole] = {UserRole.super_admin}


def _unauthorized(message: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized("Missing authentication token")

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise _unauthorized("Invalid or expired token") from None

    if payload.get("type") != "access":
        raise _unauthorized("Invalid token type")

    subject = payload.get("sub")
    if subject is None:
        raise _unauthorized()

    try:
        user_id = uuid.UUID(subject)
    except (ValueError, TypeError):
        raise _unauthorized() from None

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise _unauthorized("User no longer exists")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Return the authenticated user, or None when no Bearer token is sent.

    Invalid/expired tokens still raise 401 so callers are not silently treated
    as anonymous when they intended to act as a customer.
    """
    if credentials is None:
        return None
    return await get_current_user(credentials=credentials, db=db)


def require_roles(
    *allowed_roles: UserRole,
) -> Callable[[User], Awaitable[User]]:
    """Dependency factory that allows only the given roles."""

    allowed = set(allowed_roles)

    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _checker
