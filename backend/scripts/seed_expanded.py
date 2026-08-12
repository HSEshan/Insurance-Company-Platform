"""Phase 5 consolidated demo data: extra customers, quotes, policies, claims.

Called from ``scripts.seed`` after the baseline demo customer/policy/claims.
Every helper is idempotent (keyed by fixed policy/claim numbers or note tags).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.security import encrypt_pii, hash_password
from app.models.billing import Payment
from app.models.claim import Claim, ClaimNote
from app.models.customer import Customer
from app.models.enums import (
    BeneficiaryRelationship,
    ClaimNoteType,
    ClaimStatus,
    ClaimType,
    ConstructionType,
    HealthClass,
    LifeType,
    PaymentFrequency,
    PaymentMethod,
    PaymentStatus,
    PaymentType,
    PolicyStatus,
    PolicyType,
    PremiumMode,
    QuoteStatus,
    RiskTier,
    RoofType,
    UserRole,
)
from app.models.policy import (
    Beneficiary,
    Policy,
    PolicyHomeDetails,
    PolicyLifeDetails,
)
from app.models.quote import Quote
from app.models.user import User
from app.services import billing

# Extra customers (beyond Casey Customer).
CUSTOMER_B_EMAIL = "homeowner@insureco.com"
CUSTOMER_B_PASSWORD = "Customer123!"
CUSTOMER_C_EMAIL = "lifeholder@insureco.com"
CUSTOMER_C_PASSWORD = "Customer123!"

HOME_POLICY = "HOME-2026-900001"
LIFE_POLICY = "LIFE-2026-900001"
LAPSED_POLICY = "AUTO-2026-900002"
CANCELLED_POLICY = "AUTO-2026-900003"

# Claims covering remaining lifecycle stages (900001/900002 created in base seed).
CLAIM_ASSIGNED = "CLM-2026-900003"
CLAIM_INFO = "CLM-2026-900004"
CLAIM_APPROVED = "CLM-2026-900005"
CLAIM_REJECTED = "CLM-2026-900006"
CLAIM_DISPUTED = "CLM-2026-900007"
CLAIM_PAID = "CLM-2026-900008"
CLAIM_CLOSED = "CLM-2026-900009"
CLAIM_FRAUD = "CLM-2026-900010"

# Quote note tags for idempotent lookup.
QUOTE_TAGS = {
    QuoteStatus.draft: "SEED:quote-draft",
    QuoteStatus.pending_review: "SEED:quote-pending",
    QuoteStatus.approved: "SEED:quote-approved",
    QuoteStatus.rejected: "SEED:quote-rejected",
    QuoteStatus.bound: "SEED:quote-bound",
    QuoteStatus.expired: "SEED:quote-expired",
}


async def _ensure_customer(
    db,
    *,
    email: str,
    password: str,
    first: str,
    last: str,
    dob: date,
    city: str,
    state: str,
    zip_code: str,
) -> Customer:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            first_name=first,
            last_name=last,
            phone="216-555-0199",
            role=UserRole.customer,
        )
        customer = Customer(
            date_of_birth=dob,
            ssn_last4="4321",
            ssn_encrypted=encrypt_pii("987654321"),
            address_line1="100 Demo Street",
            city=city,
            state=state,
            zip=zip_code,
            country="US",
            credit_score=740,
            risk_tier=RiskTier.preferred,
        )
        user.customer = customer
        db.add(user)
        await db.flush()
        print(f"  + created customer {email}")
        return customer

    customer = await db.scalar(select(Customer).where(Customer.user_id == user.id))
    if customer is None:
        raise RuntimeError(f"{email} exists without a customer profile.")
    print(f"  - {email} already exists, skipping")
    return customer


async def _ensure_home_policy(db, customer: Customer, agent: User) -> Policy:
    existing = await db.scalar(select(Policy).where(Policy.policy_number == HOME_POLICY))
    if existing:
        print(f"  - policy {HOME_POLICY} already exists")
        return existing

    effective = date.today() - timedelta(days=90)
    policy = Policy(
        policy_number=HOME_POLICY,
        customer_id=customer.id,
        policy_type=PolicyType.home,
        status=PolicyStatus.active,
        effective_date=effective,
        expiration_date=effective + timedelta(days=365),
        annual_premium=Decimal("1240.00"),
        payment_frequency=PaymentFrequency.annual,
        agent_id=agent.id,
    )
    db.add(policy)
    await db.flush()
    db.add(
        PolicyHomeDetails(
            policy_id=policy.id,
            property_address_line1="88 Maple Rd",
            city="Cleveland",
            state="OH",
            zip="44120",
            year_built=1998,
            square_footage=2100,
            construction_type=ConstructionType.frame,
            roof_type=RoofType.shingle,
            roof_year=2015,
            home_value=Decimal("325000"),
            dwelling_coverage=Decimal("300000"),
            personal_property_coverage=Decimal("150000"),
            liability_coverage=Decimal("300000"),
            deductible=Decimal("1000"),
        )
    )
    print(f"  + created home policy {HOME_POLICY}")
    return policy


async def _ensure_life_policy(db, customer: Customer, agent: User) -> Policy:
    existing = await db.scalar(select(Policy).where(Policy.policy_number == LIFE_POLICY))
    if existing:
        print(f"  - policy {LIFE_POLICY} already exists")
        return existing

    effective = date.today() - timedelta(days=60)
    policy = Policy(
        policy_number=LIFE_POLICY,
        customer_id=customer.id,
        policy_type=PolicyType.life,
        status=PolicyStatus.active,
        effective_date=effective,
        expiration_date=effective + timedelta(days=365 * 20),
        annual_premium=Decimal("890.00"),
        payment_frequency=PaymentFrequency.monthly,
        agent_id=agent.id,
    )
    db.add(policy)
    await db.flush()
    db.add(
        PolicyLifeDetails(
            policy_id=policy.id,
            coverage_amount=Decimal("250000"),
            policy_term_years=20,
            life_type=LifeType.term,
            tobacco_user=False,
            health_class=HealthClass.preferred,
            premium_mode=PremiumMode.level,
        )
    )
    db.add(
        Beneficiary(
            policy_id=policy.id,
            full_name="Pat Beneficiary",
            relationship_type=BeneficiaryRelationship.spouse,
            allocation_pct=Decimal("100.00"),
            is_contingent=False,
        )
    )
    print(f"  + created life policy {LIFE_POLICY}")
    return policy


async def _ensure_status_policies(
    db, customer: Customer, agent: User
) -> None:
    """Lapsed + cancelled auto policies for status variety on agent/manager views."""
    specs = [
        (
            LAPSED_POLICY,
            PolicyStatus.lapsed,
            date.today() - timedelta(days=400),
            date.today() - timedelta(days=35),
            "Non-payment after grace period",
        ),
        (
            CANCELLED_POLICY,
            PolicyStatus.cancelled,
            date.today() - timedelta(days=200),
            date.today() + timedelta(days=165),
            "Customer requested cancellation",
        ),
    ]
    for number, status, effective, expiration, reason in specs:
        existing = await db.scalar(select(Policy).where(Policy.policy_number == number))
        if existing:
            print(f"  - policy {number} already exists")
            continue
        policy = Policy(
            policy_number=number,
            customer_id=customer.id,
            policy_type=PolicyType.auto,
            status=status,
            effective_date=effective,
            expiration_date=expiration,
            annual_premium=Decimal("1100.00"),
            payment_frequency=PaymentFrequency.monthly,
            agent_id=agent.id,
            cancellation_reason=reason if status == PolicyStatus.cancelled else None,
            cancelled_at=datetime.now(UTC) - timedelta(days=10)
            if status == PolicyStatus.cancelled
            else None,
        )
        db.add(policy)
        print(f"  + created {status.value} policy {number}")


async def _ensure_quotes(db, customer: Customer, agent: User) -> None:
    for status, tag in QUOTE_TAGS.items():
        existing = await db.scalar(select(Quote).where(Quote.notes == tag))
        if existing:
            print(f"  - quote {tag} already exists")
            continue

        today = date.today()
        quote = Quote(
            customer_id=customer.id,
            policy_type=PolicyType.auto,
            status=status,
            quoted_premium=Decimal("1600.00"),
            monthly_premium=Decimal("133.33"),
            risk_tier=RiskTier.standard,
            rating_inputs={"seed": True},
            rating_factors=[{"name": "base", "factor": 1.0}],
            policy_details={"make": "Toyota", "model": "Camry", "year": 2022},
            decline_reasons=["SEED decline sample"]
            if status == QuoteStatus.rejected
            else None,
            effective_date=today + timedelta(days=14),
            expiry_date=today
            - timedelta(days=5)
            if status == QuoteStatus.expired
            else today + timedelta(days=30),
            agent_id=agent.id,
            underwriter_id=agent.id
            if status in {QuoteStatus.approved, QuoteStatus.bound, QuoteStatus.rejected}
            else None,
            notes=tag,
        )
        db.add(quote)
        print(f"  + created quote ({status.value})")


async def _ensure_claim(
    db,
    *,
    claim_number: str,
    policy: Policy,
    customer: Customer,
    adjuster: User | None,
    status: ClaimStatus,
    claim_type: ClaimType,
    description: str,
    estimated: Decimal,
    fraud: bool = False,
    fraud_score: Decimal = Decimal("0.000"),
    approved: Decimal | None = None,
    payout: Decimal | None = None,
    note: str | None = None,
) -> Claim:
    existing = await db.scalar(select(Claim).where(Claim.claim_number == claim_number))
    if existing:
        print(f"  - claim {claim_number} already exists")
        return existing

    claim = Claim(
        claim_number=claim_number,
        policy_id=policy.id,
        customer_id=customer.id,
        claim_type=claim_type,
        incident_date=date.today() - timedelta(days=40),
        reported_date=date.today() - timedelta(days=38),
        description=description,
        incident_location="Cleveland, OH",
        estimated_damage=estimated,
        approved_amount=approved,
        final_payout=payout,
        status=status,
        fraud_flag=fraud,
        fraud_score=fraud_score,
        adjuster_id=adjuster.id if adjuster else None,
    )
    db.add(claim)
    await db.flush()
    if note and adjuster:
        db.add(
            ClaimNote(
                claim_id=claim.id,
                author_id=adjuster.id,
                note_type=ClaimNoteType.investigation,
                body=note,
                is_visible_to_customer=status
                in {ClaimStatus.rejected, ClaimStatus.info_requested},
            )
        )
    print(f"  + created claim {claim_number} ({status.value})")
    return claim


async def _ensure_lifecycle_claims(
    db, policy: Policy, customer: Customer, adjuster: User
) -> None:
    await _ensure_claim(
        db,
        claim_number=CLAIM_ASSIGNED,
        policy=policy,
        customer=customer,
        adjuster=adjuster,
        status=ClaimStatus.assigned,
        claim_type=ClaimType.auto_liability,
        description="Parking-lot scrape; third party reported minor damage.",
        estimated=Decimal("1800.00"),
        note="Assigned from intake queue.",
    )
    await _ensure_claim(
        db,
        claim_number=CLAIM_INFO,
        policy=policy,
        customer=customer,
        adjuster=adjuster,
        status=ClaimStatus.info_requested,
        claim_type=ClaimType.auto_collision,
        description="Side-impact at intersection; police report pending.",
        estimated=Decimal("6500.00"),
        note="Please upload the police report and repair estimate.",
    )
    approved = await _ensure_claim(
        db,
        claim_number=CLAIM_APPROVED,
        policy=policy,
        customer=customer,
        adjuster=adjuster,
        status=ClaimStatus.approved,
        claim_type=ClaimType.auto_comprehensive,
        description="Windshield replacement after rock chip spread.",
        estimated=Decimal("900.00"),
        approved=Decimal("850.00"),
        note="Approved for glass replacement.",
    )
    _ = approved
    await _ensure_claim(
        db,
        claim_number=CLAIM_REJECTED,
        policy=policy,
        customer=customer,
        adjuster=adjuster,
        status=ClaimStatus.rejected,
        claim_type=ClaimType.auto_collision,
        description="Claim for pre-existing body damage; not covered.",
        estimated=Decimal("2200.00"),
        note="Rejected: damage predates policy effective date.",
    )
    await _ensure_claim(
        db,
        claim_number=CLAIM_DISPUTED,
        policy=policy,
        customer=customer,
        adjuster=adjuster,
        status=ClaimStatus.disputed,
        claim_type=ClaimType.auto_collision,
        description="Customer disputes prior rejection of fender claim.",
        estimated=Decimal("3100.00"),
        note="Customer filed dispute within 30-day window.",
    )
    paid = await _ensure_claim(
        db,
        claim_number=CLAIM_PAID,
        policy=policy,
        customer=customer,
        adjuster=adjuster,
        status=ClaimStatus.paid,
        claim_type=ClaimType.auto_comprehensive,
        description="Theft of catalytic converter; parts replaced.",
        estimated=Decimal("2400.00"),
        approved=Decimal("2300.00"),
        payout=Decimal("2300.00"),
        note="Payout issued to repair shop.",
    )
    # Matching claim_payout payment so loss-ratio / payments ledger have data.
    existing_pay = await db.scalar(
        select(Payment).where(
            Payment.claim_id == paid.id,
            Payment.payment_type == PaymentType.claim_payout,
        )
    )
    if existing_pay is None and paid.final_payout:
        db.add(
            Payment(
                claim_id=paid.id,
                customer_id=customer.id,
                payment_type=PaymentType.claim_payout,
                amount=paid.final_payout,
                method=PaymentMethod.ach,
                status=PaymentStatus.completed,
                reference_number=billing.build_reference_number(PaymentMethod.ach),
                processed_at=datetime.now(UTC) - timedelta(days=5),
                notes="Seeded claim payout",
                created_by=adjuster.id,
            )
        )
        print(f"  + recorded payout for {CLAIM_PAID}")

    await _ensure_claim(
        db,
        claim_number=CLAIM_CLOSED,
        policy=policy,
        customer=customer,
        adjuster=adjuster,
        status=ClaimStatus.closed,
        claim_type=ClaimType.auto_liability,
        description="Closed after low-severity settlement.",
        estimated=Decimal("500.00"),
        approved=Decimal("500.00"),
        payout=Decimal("500.00"),
        note="File closed.",
    )
    await _ensure_claim(
        db,
        claim_number=CLAIM_FRAUD,
        policy=policy,
        customer=customer,
        adjuster=adjuster,
        status=ClaimStatus.investigating,
        claim_type=ClaimType.auto_collision,
        description=(
            "Total-loss claim filed 2 days after policy inception with "
            "inconsistent incident details."
        ),
        estimated=Decimal("28000.00"),
        fraud=True,
        fraud_score=Decimal("0.820"),
        note="SYSTEM: elevated fraud score — refer to SIU checklist.",
    )


async def ensure_expanded_demo(
    db,
    *,
    primary_customer: Customer,
    primary_policy: Policy,
    staff: dict[UserRole, User],
) -> None:
    """Expand the base seed into a multi-role, multi-stage demo book."""
    agent = staff[UserRole.agent]
    adjuster = staff[UserRole.adjuster]

    homeowner = await _ensure_customer(
        db,
        email=CUSTOMER_B_EMAIL,
        password=CUSTOMER_B_PASSWORD,
        first="Harper",
        last="Homeowner",
        dob=date(1985, 7, 22),
        city="Cleveland",
        state="OH",
        zip_code="44120",
    )
    lifeholder = await _ensure_customer(
        db,
        email=CUSTOMER_C_EMAIL,
        password=CUSTOMER_C_PASSWORD,
        first="Logan",
        last="Lifeholder",
        dob=date(1978, 11, 3),
        city="Lakewood",
        state="OH",
        zip_code="44107",
    )

    await _ensure_home_policy(db, homeowner, agent)
    await _ensure_life_policy(db, lifeholder, agent)
    await _ensure_status_policies(db, primary_customer, agent)
    await _ensure_quotes(db, primary_customer, agent)
    await _ensure_lifecycle_claims(db, primary_policy, primary_customer, adjuster)
