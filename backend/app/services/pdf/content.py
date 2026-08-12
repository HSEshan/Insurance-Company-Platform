"""Plain input types for the PDF renderers.

The renderers deliberately take these instead of ORM objects: the templates stay
free of lazy-loading and session concerns, and tests can build a document from
literals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PartyDetails:
    name: str
    address_lines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DeclarationData:
    """Everything printed on a policy declaration page."""

    policy_number: str
    policy_type: str
    status: str
    effective_date: date
    expiration_date: date
    annual_premium: Decimal
    payment_frequency: str
    insured: PartyDetails
    # (label, value) pairs describing the coverages for this line of business.
    coverages: list[tuple[str, str]] = field(default_factory=list)
    # (due date, amount, status) for each premium installment.
    installments: list[tuple[str, str, str]] = field(default_factory=list)
    # (name, relationship, allocation) — life policies only.
    beneficiaries: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class DecisionLetterData:
    """Everything printed on a claim approval or rejection letter."""

    claim_number: str
    policy_number: str
    claim_type: str
    decision: str  # "approved" or "rejected"
    decision_date: date
    incident_date: date
    reported_date: date
    insured: PartyDetails
    estimated_damage: Decimal | None = None
    approved_amount: Decimal | None = None
    reason: str | None = None
    adjuster_name: str | None = None
