"""Add quote rating persistence columns and policy-number sequences.

Revision ID: 0002_quote_policy
Revises: 0001_initial
Create Date: 2026-08-04

Idempotent: ``0001_initial`` uses ``metadata.create_all``, so a fresh database
already has these quote columns once the model is updated. This revision only
adds missing columns (existing DBs) and always ensures the policy-number
sequences exist.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_quote_policy"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    cols = _existing_columns("quotes")

    if "monthly_premium" not in cols:
        op.add_column(
            "quotes",
            sa.Column("monthly_premium", sa.Numeric(precision=12, scale=2), nullable=True),
        )
    if "risk_tier" not in cols:
        op.add_column(
            "quotes",
            sa.Column(
                "risk_tier",
                postgresql.ENUM(
                    "preferred",
                    "standard",
                    "substandard",
                    "declined",
                    name="risk_tier",
                    create_type=False,
                ),
                nullable=True,
            ),
        )
    if "rating_inputs" not in cols:
        op.add_column(
            "quotes",
            sa.Column(
                "rating_inputs",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
    if "rating_factors" not in cols:
        op.add_column(
            "quotes",
            sa.Column(
                "rating_factors",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
    if "policy_details" not in cols:
        op.add_column(
            "quotes",
            sa.Column(
                "policy_details",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
    if "decline_reasons" not in cols:
        op.add_column(
            "quotes",
            sa.Column(
                "decline_reasons",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )

    op.execute("CREATE SEQUENCE IF NOT EXISTS policy_number_auto START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS policy_number_home START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS policy_number_life START 1")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS policy_number_life")
    op.execute("DROP SEQUENCE IF EXISTS policy_number_home")
    op.execute("DROP SEQUENCE IF EXISTS policy_number_auto")

    cols = _existing_columns("quotes")
    for name in (
        "decline_reasons",
        "policy_details",
        "rating_factors",
        "rating_inputs",
        "risk_tier",
        "monthly_premium",
    ):
        if name in cols:
            op.drop_column("quotes", name)
