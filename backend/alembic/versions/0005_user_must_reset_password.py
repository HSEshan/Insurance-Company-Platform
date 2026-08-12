"""Add users.must_reset_password for staff temp-password bootstrap.

Revision ID: 0005_must_reset
Revises: 0004_decision_letter
Create Date: 2026-08-10

Idempotent: fresh DBs already get the column from ``metadata.create_all``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_must_reset"
down_revision: str | None = "0004_decision_letter"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    cols = _existing_columns("users")
    if "must_reset_password" not in cols:
        op.add_column(
            "users",
            sa.Column(
                "must_reset_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.alter_column("users", "must_reset_password", server_default=None)


def downgrade() -> None:
    cols = _existing_columns("users")
    if "must_reset_password" in cols:
        op.drop_column("users", "must_reset_password")
