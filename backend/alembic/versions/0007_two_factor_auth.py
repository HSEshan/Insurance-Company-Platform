"""Add contact verification + two-factor auth columns to users.

Revision ID: 0007_two_factor
Revises: 0006_chat
Create Date: 2026-10-24

Idempotent: fresh DBs already get these columns (and the ``mfa_method`` enum)
from ``metadata.create_all`` in ``0001_initial``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_two_factor"
down_revision: str | None = "0006_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MFA_METHODS = ("totp", "email", "sms")
mfa_method = postgresql.ENUM(*MFA_METHODS, name="mfa_method", create_type=False)


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)}


def _new_columns() -> list[sa.Column]:
    return [
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_method", mfa_method, nullable=True),
        sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("totp_secret_encrypted", sa.String(), nullable=True),
        sa.Column("mfa_recovery_codes", postgresql.JSONB(), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'mfa_method'")
    ).scalar()
    if not exists:
        sa.Enum(*MFA_METHODS, name="mfa_method").create(bind, checkfirst=True)

    cols = _existing_columns("users")
    for column in _new_columns():
        if column.name not in cols:
            op.add_column("users", column)


def downgrade() -> None:
    cols = _existing_columns("users")
    for column in reversed(_new_columns()):
        if column.name in cols:
            op.drop_column("users", column.name)
    sa.Enum(name="mfa_method").drop(op.get_bind(), checkfirst=True)
