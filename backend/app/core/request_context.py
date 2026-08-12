"""Per-request forensic context for audit logging.

The HTTP middleware in ``main.py`` populates these contextvars at the start of
every request. ``audit_service.record`` reads them so callers never have to
thread ``request`` through the service layer.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

request_id_var: ContextVar[uuid.UUID | None] = ContextVar("request_id", default=None)
ip_address_var: ContextVar[str | None] = ContextVar("ip_address", default=None)
user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)


def set_request_context(
    *,
    request_id: uuid.UUID | None,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    request_id_var.set(request_id)
    ip_address_var.set(ip_address)
    user_agent_var.set(user_agent)


def clear_request_context() -> None:
    request_id_var.set(None)
    ip_address_var.set(None)
    user_agent_var.set(None)


def current_request_id() -> uuid.UUID | None:
    return request_id_var.get()


def current_ip_address() -> str | None:
    return ip_address_var.get()


def current_user_agent() -> str | None:
    return user_agent_var.get()
