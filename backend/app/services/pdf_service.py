"""Assembles carrier documents from the database and files them in storage.

This is the seam between the pure renderers in ``services/pdf/`` and the rest of
the system. It is called from the endpoint layer after a lifecycle event
succeeds, which keeps the business services free of any dependency on PDF
generation or object storage — and gives the future Celery worker an obvious
place to take over.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import PremiumSchedule
from app.models.claim import Claim
from app.models.customer import Customer
from app.models.document import Document
from app.models.enums import DocumentOwnerType, DocumentType
from app.models.policy import (
    Beneficiary,
    Policy,
    PolicyAutoDetails,
    PolicyHomeDetails,
    PolicyLifeDetails,
)
from app.models.user import User
from app.services import document_service
from app.services.pdf import (
    DecisionLetterData,
    DeclarationData,
    PartyDetails,
    render_claim_decision_letter,
    render_policy_declaration,
)

logger = logging.getLogger(__name__)


def _money(value: Decimal | None) -> str:
    return "—" if value is None else f"${value:,.2f}"


def _humanize(value: str | None) -> str:
    return "—" if value is None else str(value).replace("_", " ").title()


def _included(flag: bool) -> str:
    return "Included" if flag else "Not included"


async def _party_for_customer(db: AsyncSession, customer_id: uuid.UUID) -> PartyDetails:
    customer = await db.scalar(select(Customer).where(Customer.id == customer_id))
    if customer is None:
        return PartyDetails(name="Valued Customer")

    user = await db.scalar(select(User).where(User.id == customer.user_id))
    name = (
        f"{user.first_name} {user.last_name}".strip()
        if user is not None
        else "Valued Customer"
    )

    city_line = ", ".join(part for part in [customer.city, customer.state] if part)
    if customer.zip:
        city_line = f"{city_line} {customer.zip}".strip()
    lines = [
        customer.address_line1,
        customer.address_line2,
        city_line or None,
    ]
    return PartyDetails(name=name, address_lines=[ln for ln in lines if ln])


async def _coverages_for(db: AsyncSession, policy: Policy) -> list[tuple[str, str]]:
    """Flatten the line-of-business detail row into printable coverage rows."""
    if policy.policy_type == "auto":
        auto = await db.scalar(
            select(PolicyAutoDetails).where(PolicyAutoDetails.policy_id == policy.id)
        )
        if auto is None:
            return []
        vehicle = " ".join(
            str(p) for p in [auto.year, auto.make, auto.model] if p is not None
        )
        return [
            ("Insured vehicle", vehicle or "—"),
            ("VIN", auto.vin),
            ("Coverage type", _humanize(auto.coverage_type)),
            ("Liability limit", _money(auto.liability_limit)),
            ("Collision deductible", _money(auto.collision_deductible)),
            ("Comprehensive deductible", _money(auto.comprehensive_deductible)),
            ("Uninsured motorist", _included(auto.uninsured_motorist)),
            ("Roadside assistance", _included(auto.roadside_assistance)),
            ("Rental reimbursement", _included(auto.rental_reimbursement)),
        ]

    if policy.policy_type == "home":
        home = await db.scalar(
            select(PolicyHomeDetails).where(PolicyHomeDetails.policy_id == policy.id)
        )
        if home is None:
            return []
        address = ", ".join(
            part
            for part in [home.property_address_line1, home.city, home.state, home.zip]
            if part
        )
        return [
            ("Insured property", address or "—"),
            ("Construction", _humanize(home.construction_type)),
            ("Dwelling coverage", _money(home.dwelling_coverage)),
            ("Personal property", _money(home.personal_property_coverage)),
            ("Liability coverage", _money(home.liability_coverage)),
            ("Deductible", _money(home.deductible)),
            ("Flood coverage", _included(home.flood_coverage)),
            ("Earthquake coverage", _included(home.earthquake_coverage)),
        ]

    life = await db.scalar(
        select(PolicyLifeDetails).where(PolicyLifeDetails.policy_id == policy.id)
    )
    if life is None:
        return []
    return [
        ("Coverage amount", _money(life.coverage_amount)),
        ("Product", _humanize(life.life_type)),
        (
            "Term",
            f"{life.policy_term_years} years" if life.policy_term_years else "Whole life",
        ),
        ("Health class", _humanize(life.health_class)),
        ("Premium mode", _humanize(life.premium_mode)),
        ("Tobacco use", "Yes" if life.tobacco_user else "No"),
    ]


async def build_declaration_data(db: AsyncSession, policy: Policy) -> DeclarationData:
    schedules = list(
        (
            await db.scalars(
                select(PremiumSchedule)
                .where(PremiumSchedule.policy_id == policy.id)
                .order_by(PremiumSchedule.due_date)
            )
        ).all()
    )
    beneficiaries = list(
        (
            await db.scalars(
                select(Beneficiary).where(Beneficiary.policy_id == policy.id)
            )
        ).all()
    )

    return DeclarationData(
        policy_number=policy.policy_number,
        policy_type=str(policy.policy_type),
        status=str(policy.status),
        effective_date=policy.effective_date,
        expiration_date=policy.expiration_date,
        annual_premium=policy.annual_premium,
        payment_frequency=str(policy.payment_frequency),
        insured=await _party_for_customer(db, policy.customer_id),
        coverages=await _coverages_for(db, policy),
        installments=[
            (s.due_date.isoformat(), _money(s.amount_due), _humanize(str(s.status)))
            for s in schedules
        ],
        beneficiaries=[
            (
                b.full_name,
                _humanize(b.relationship_type),
                f"{b.allocation_pct:.0f}%",
            )
            for b in beneficiaries
        ],
    )


async def generate_policy_declaration(
    db: AsyncSession, policy: Policy, actor_id: uuid.UUID | None = None
) -> Document:
    """Render and file the declaration page for a bound policy."""
    data = await build_declaration_data(db, policy)
    content = render_policy_declaration(data)
    return await document_service.store_generated_document(
        db,
        owner_type=DocumentOwnerType.policy,
        owner_id=policy.id,
        document_type=DocumentType.policy_pdf,
        file_name=f"declaration-{policy.policy_number}.pdf",
        content=content,
        actor_id=actor_id,
        # Only one declaration is current at a time; a later one supersedes it.
        replace_existing=True,
    )


async def build_decision_letter_data(
    db: AsyncSession, claim: Claim, *, decision: str
) -> DecisionLetterData:
    policy = await db.scalar(select(Policy).where(Policy.id == claim.policy_id))
    adjuster = (
        await db.scalar(select(User).where(User.id == claim.adjuster_id))
        if claim.adjuster_id
        else None
    )
    reason = None
    if decision == "rejected":
        reason = await _latest_rejection_reason(db, claim)

    return DecisionLetterData(
        claim_number=claim.claim_number,
        policy_number=policy.policy_number if policy else "—",
        claim_type=str(claim.claim_type),
        decision=decision,
        decision_date=date.today(),
        incident_date=claim.incident_date,
        reported_date=claim.reported_date,
        insured=await _party_for_customer(db, claim.customer_id),
        estimated_damage=claim.estimated_damage,
        approved_amount=claim.approved_amount,
        reason=reason,
        adjuster_name=(
            f"{adjuster.first_name} {adjuster.last_name}".strip() if adjuster else None
        ),
    )


async def _latest_rejection_reason(db: AsyncSession, claim: Claim) -> str | None:
    """Recover the reason text the adjuster supplied when rejecting."""
    from app.models.claim import ClaimNote

    note = await db.scalar(
        select(ClaimNote)
        .where(
            ClaimNote.claim_id == claim.id,
            ClaimNote.body.like("Claim rejected:%"),
        )
        .order_by(ClaimNote.created_at.desc())
        .limit(1)
    )
    if note is None:
        return None
    return note.body.removeprefix("Claim rejected:").strip() or None


async def generate_claim_decision_letter(
    db: AsyncSession, claim: Claim, *, decision: str, actor_id: uuid.UUID | None = None
) -> Document:
    """Render and file an approval or rejection letter for a claim."""
    data = await build_decision_letter_data(db, claim, decision=decision)
    content = render_claim_decision_letter(data)
    return await document_service.store_generated_document(
        db,
        owner_type=DocumentOwnerType.claim,
        owner_id=claim.id,
        document_type=DocumentType.claim_decision_letter,
        file_name=f"decision-{claim.claim_number}-{decision}.pdf",
        content=content,
        actor_id=actor_id,
        # Each decision is part of the claim's history, so letters accumulate:
        # a dispute that overturns a rejection produces a second letter.
        replace_existing=False,
    )


async def try_generate(coro, *, description: str) -> Document | None:
    """Run a generation coroutine without letting it fail the caller.

    Document generation is a side effect of a business event, not part of it. A
    storage outage must not roll back a bound policy or an adjudicated claim.
    """
    try:
        return await coro
    except Exception:
        logger.exception("Could not generate %s", description)
        return None
