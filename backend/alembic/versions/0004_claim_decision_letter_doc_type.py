"""Add the claim_decision_letter document type for generated PDFs.

Revision ID: 0004_decision_letter
Revises: 0003_claim_seq
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_decision_letter"
down_revision: str | None = "0003_claim_seq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept in sync with models.enums.DocumentType, minus the value added here.
_PREVIOUS_VALUES = (
    "policy_pdf",
    "id_document",
    "vehicle_photo",
    "property_photo",
    "police_report",
    "medical_report",
    "repair_estimate",
    "proof_of_ownership",
    "receipt",
    "other",
)


def upgrade() -> None:
    # Postgres 12+ permits ADD VALUE inside a transaction as long as the new
    # value is not also used in that transaction, so no autocommit block needed.
    op.execute(
        "ALTER TYPE document_type ADD VALUE IF NOT EXISTS 'claim_decision_letter'"
    )


def downgrade() -> None:
    # Postgres cannot drop a single enum value, so rebuild the type without it.
    # This intentionally fails if any row still uses the value being removed.
    values = ", ".join(f"'{v}'" for v in _PREVIOUS_VALUES)
    op.execute("ALTER TYPE document_type RENAME TO document_type_old")
    op.execute(f"CREATE TYPE document_type AS ENUM ({values})")
    op.execute(
        "ALTER TABLE documents ALTER COLUMN document_type TYPE document_type "
        "USING document_type::text::document_type"
    )
    op.execute("DROP TYPE document_type_old")
