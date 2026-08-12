"""Seed baseline staff + a demo customer with an active policy and sample claims.

Usage (from the backend directory, with the database reachable):

    python -m scripts.seed
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import encrypt_pii, hash_password
from app.models.audit import AuditLog
from app.models.billing import Payment, PremiumSchedule
from app.models.claim import Claim, ClaimNote
from app.models.customer import Customer
from app.models.enums import (
    AutoCoverageType,
    ClaimNoteType,
    ClaimStatus,
    ClaimType,
    PaymentFrequency,
    PaymentMethod,
    PaymentStatus,
    PaymentType,
    PolicyStatus,
    PolicyType,
    PremiumScheduleStatus,
    RiskTier,
    UserRole,
    VehicleType,
    VehicleUse,
)
from app.models.policy import Policy, PolicyAutoDetails
from app.models.user import User
from app.services import billing, policy_service
from scripts.seed_expanded import ensure_expanded_demo

# Uses a real TLD because RFC-compliant email validation rejects reserved
# special-use domains such as ".local".
SEED_USERS = [
    ("admin@insureco.com", "Admin123!", "Ada", "Admin", UserRole.super_admin),
    ("manager@insureco.com", "Manager123!", "Mona", "Manager", UserRole.manager),
    ("agent@insureco.com", "Agent123!", "Aaron", "Agent", UserRole.agent),
    ("adjuster@insureco.com", "Adjuster123!", "Adam", "Adjuster", UserRole.adjuster),
]

DEMO_CUSTOMER_EMAIL = "customer@insureco.com"
DEMO_CUSTOMER_PASSWORD = "Customer123!"
DEMO_POLICY_NUMBER = "AUTO-2026-900001"
DEMO_CLAIM_SUBMITTED = "CLM-2026-900001"
DEMO_CLAIM_INVESTIGATING = "CLM-2026-900002"


async def _ensure_staff(db) -> dict[UserRole, User]:
    by_role: dict[UserRole, User] = {}
    for email, password, first, last, role in SEED_USERS:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                hashed_password=hash_password(password),
                first_name=first,
                last_name=last,
                role=role,
            )
            db.add(user)
            await db.flush()
            print(f"  + created {role.value}: {email} / {password}")
        else:
            print(f"  - {email} already exists, skipping")
        by_role[role] = user
    return by_role


async def _ensure_demo_customer(db, agent: User) -> Customer:
    user = await db.scalar(select(User).where(User.email == DEMO_CUSTOMER_EMAIL))
    if user is None:
        user = User(
            email=DEMO_CUSTOMER_EMAIL,
            hashed_password=hash_password(DEMO_CUSTOMER_PASSWORD),
            first_name="Casey",
            last_name="Customer",
            phone="216-555-0100",
            role=UserRole.customer,
        )
        customer = Customer(
            date_of_birth=date(1990, 4, 15),
            ssn_last4="6789",
            ssn_encrypted=encrypt_pii("123456789"),
            address_line1="200 Euclid Ave",
            city="Cleveland",
            state="OH",
            zip="44114",
            country="US",
            credit_score=720,
            risk_tier=RiskTier.standard,
        )
        user.customer = customer
        db.add(user)
        await db.flush()
        print(
            f"  + created customer: {DEMO_CUSTOMER_EMAIL} / {DEMO_CUSTOMER_PASSWORD}"
        )
        return customer

    customer = await db.scalar(select(Customer).where(Customer.user_id == user.id))
    if customer is None:
        raise RuntimeError("Demo customer user exists without a customer profile.")
    print(f"  - {DEMO_CUSTOMER_EMAIL} already exists, skipping")
    _ = agent
    return customer


async def _ensure_demo_policy(db, customer: Customer, agent: User) -> Policy:
    policy = await db.scalar(
        select(Policy).where(Policy.policy_number == DEMO_POLICY_NUMBER)
    )
    if policy is not None:
        print(f"  - policy {DEMO_POLICY_NUMBER} already exists, skipping")
        return policy

    effective = date.today() - timedelta(days=120)
    expiration = effective + timedelta(days=365)
    policy = Policy(
        policy_number=DEMO_POLICY_NUMBER,
        customer_id=customer.id,
        policy_type=PolicyType.auto,
        status=PolicyStatus.active,
        effective_date=effective,
        expiration_date=expiration,
        annual_premium=Decimal("1480.00"),
        payment_frequency=PaymentFrequency.monthly,
        agent_id=agent.id,
    )
    db.add(policy)
    await db.flush()
    db.add(
        PolicyAutoDetails(
            policy_id=policy.id,
            vin="1HGCM82633A004352",
            make="Honda",
            model="Accord",
            year=2020,
            vehicle_type=VehicleType.sedan,
            primary_use=VehicleUse.commute,
            annual_mileage=12000,
            garaging_zip="44114",
            coverage_type=AutoCoverageType.full_coverage,
            liability_limit=Decimal("100000"),
            collision_deductible=Decimal("500"),
            comprehensive_deductible=Decimal("500"),
        )
    )
    print(f"  + created active auto policy {DEMO_POLICY_NUMBER}")
    return policy


async def _ensure_premium_schedule(db, policy: Policy) -> None:
    """Bill the demo policy the same way binding would.

    Status is derived later from payments — never stamped ``paid`` without a
    matching ``Payment`` row, or the ledger and the schedule drift apart.
    """
    existing = await db.scalar(
        select(func.count(PremiumSchedule.id)).where(
            PremiumSchedule.policy_id == policy.id
        )
    )
    if existing:
        print(f"  - premium schedule already exists ({existing} installments)")
        return

    today = date.today()
    rows = policy_service.generate_premium_schedule_rows(
        annual_premium=policy.annual_premium,
        payment_frequency=policy.payment_frequency,
        effective_date=policy.effective_date,
    )
    for due_date, amount in rows:
        db.add(
            PremiumSchedule(
                policy_id=policy.id,
                due_date=due_date,
                amount_due=amount,
                status=billing.resolve_schedule_status(
                    amount_due=amount,
                    amount_paid=billing.ZERO,
                    due_date=due_date,
                    today=today,
                    current=PremiumScheduleStatus.upcoming,
                ),
            )
        )
    print(f"  + created premium schedule ({len(rows)} installments)")


async def _ensure_demo_premium_payments(
    db, policy: Policy, customer: Customer, agent: User
) -> None:
    """Post real ACH payments against past installments so the ledger is honest.

    Marks every past installment paid except the most recent one, which is left
    overdue so the billing card and the Celery overdue job have something to
    show. Idempotent: skips installments that already have completed payments.
    """
    schedules = list(
        (
            await db.scalars(
                select(PremiumSchedule)
                .where(PremiumSchedule.policy_id == policy.id)
                .order_by(PremiumSchedule.due_date)
            )
        ).all()
    )
    today = date.today()
    past = [s for s in schedules if s.due_date < today]
    # Leave the newest past installment open so "overdue" is visible — but only
    # if it is still inside the lapse grace window. Anything older must be
    # settled, otherwise the Celery overdue job would lapse the demo policy
    # the first night it runs.
    grace = timedelta(days=settings.PREMIUM_LAPSE_DAYS)
    unpaid_candidate = past[-1] if past else None
    if (
        unpaid_candidate is not None
        and today - unpaid_candidate.due_date < grace
        and len(past) > 1
    ):
        to_settle = past[:-1]
    else:
        to_settle = past

    created = 0
    for schedule in to_settle:
        already = await billing.paid_to_date(db, schedule.id)
        if already >= schedule.amount_due:
            continue
        balance = billing.outstanding_balance(schedule.amount_due, already)
        db.add(
            Payment(
                schedule_id=schedule.id,
                customer_id=customer.id,
                payment_type=PaymentType.premium,
                amount=balance,
                method=PaymentMethod.ach,
                status=PaymentStatus.completed,
                reference_number=billing.build_reference_number(
                    PaymentMethod.ach, on=schedule.due_date
                ),
                processed_at=datetime(
                    schedule.due_date.year,
                    schedule.due_date.month,
                    schedule.due_date.day,
                    14,
                    0,
                    tzinfo=UTC,
                ),
                notes="Seeded demo premium payment",
                created_by=agent.id,
            )
        )
        created += 1

    await db.flush()

    # Re-derive every installment from money on the books — repairs older seeds
    # that stamped status=paid without a Payment row.
    refreshed = 0
    for schedule in schedules:
        before = schedule.status
        schedule.status = billing.resolve_schedule_status(
            amount_due=schedule.amount_due,
            amount_paid=await billing.paid_to_date(db, schedule.id),
            due_date=schedule.due_date,
            today=today,
            current=schedule.status,
        )
        if schedule.status != before:
            refreshed += 1

    # Guarantee one visible overdue row inside the grace window. When the
    # calendar leaves every past installment at/past the lapse threshold, pull
    # the next upcoming due date back a week so demos still show billing work.
    has_overdue = any(s.status == PremiumScheduleStatus.overdue for s in schedules)
    if not has_overdue:
        candidate = None
        for schedule in schedules:
            if schedule.due_date < today:
                continue
            paid = await billing.paid_to_date(db, schedule.id)
            if paid < schedule.amount_due:
                candidate = schedule
                break
        if candidate is not None:
            candidate.due_date = today - timedelta(days=7)
            candidate.status = PremiumScheduleStatus.overdue
            print(
                f"  + marked installment {candidate.due_date.isoformat()} overdue for demos"
            )

    if created:
        print(f"  + recorded {created} demo premium payment(s)")
    else:
        print("  - demo premium payments already in place")
    if refreshed:
        print(f"  + refreshed {refreshed} installment status(es) from payments")


async def _ensure_demo_claims(
    db, policy: Policy, customer: Customer, adjuster: User
) -> list[Claim]:
    submitted = await db.scalar(
        select(Claim).where(Claim.claim_number == DEMO_CLAIM_SUBMITTED)
    )
    if submitted is None:
        submitted = Claim(
            claim_number=DEMO_CLAIM_SUBMITTED,
            policy_id=policy.id,
            customer_id=customer.id,
            claim_type=ClaimType.auto_collision,
            incident_date=date.today() - timedelta(days=3),
            reported_date=date.today() - timedelta(days=2),
            description=(
                "Rear-end collision at a red light. Minor bumper damage; "
                "no injuries reported."
            ),
            incident_location="E 9th St & Lakeside Ave, Cleveland, OH",
            estimated_damage=Decimal("3200.00"),
            status=ClaimStatus.submitted,
            fraud_flag=False,
            fraud_score=Decimal("0.000"),
        )
        db.add(submitted)
        print(f"  + created claim {DEMO_CLAIM_SUBMITTED} (submitted)")
    else:
        print(f"  - claim {DEMO_CLAIM_SUBMITTED} already exists, skipping")

    investigating = await db.scalar(
        select(Claim).where(Claim.claim_number == DEMO_CLAIM_INVESTIGATING)
    )
    if investigating is None:
        investigating = Claim(
            claim_number=DEMO_CLAIM_INVESTIGATING,
            policy_id=policy.id,
            customer_id=customer.id,
            claim_type=ClaimType.auto_comprehensive,
            incident_date=date.today() - timedelta(days=20),
            reported_date=date.today() - timedelta(days=18),
            description=(
                "Hail damage to hood and roof while vehicle was parked overnight."
            ),
            incident_location="Cleveland, OH",
            estimated_damage=Decimal("4800.00"),
            status=ClaimStatus.investigating,
            fraud_flag=False,
            fraud_score=Decimal("0.000"),
            adjuster_id=adjuster.id,
        )
        db.add(investigating)
        await db.flush()
        db.add(
            ClaimNote(
                claim_id=investigating.id,
                author_id=adjuster.id,
                note_type=ClaimNoteType.investigation,
                body="Photos requested; awaiting repair estimate from shop.",
                is_visible_to_customer=False,
            )
        )
        print(f"  + created claim {DEMO_CLAIM_INVESTIGATING} (investigating)")
    else:
        print(f"  - claim {DEMO_CLAIM_INVESTIGATING} already exists, skipping")

    return [c for c in (submitted, investigating) if c is not None]


async def _ensure_welcome_notification(db, customer: Customer) -> None:
    """Leave at least one unread notification so the bell isn't empty on first login."""
    from app.models.enums import NotificationType
    from app.models.notification import Notification

    existing = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == customer.user_id,
            Notification.type == NotificationType.general,
            Notification.title == "Welcome to InsureCo",
        )
    )
    if existing:
        print("  - welcome notification already exists")
        return
    db.add(
        Notification(
            user_id=customer.user_id,
            type=NotificationType.general,
            title="Welcome to InsureCo",
            body=(
                "Your customer portal is ready. Review your active policy, "
                "premium schedule, and any open claims from the dashboard."
            ),
        )
    )
    print("  + created welcome notification")


async def _ensure_demo_audit(
    db, *, manager: User, agent: User, policy: Policy, claim: Claim | None
) -> None:
    """Seed a few historical audit rows so the manager Audit page isn't empty."""
    existing = await db.scalar(select(func.count()).select_from(AuditLog))
    if existing and existing > 0:
        print(f"  - audit_logs already has {existing} row(s), skipping seed samples")
        return

    await db.flush()
    samples = [
        AuditLog(
            actor_id=agent.id,
            actor_role=agent.role,
            action="policy.status_changed",
            entity_type="policy",
            entity_id=policy.id,
            old_value={"status": "draft"},
            new_value={"status": "active", "reason": "bound from quote"},
            ip_address="127.0.0.1",
            user_agent="seed/1.0",
        ),
        AuditLog(
            actor_id=manager.id,
            actor_role=manager.role,
            action="auth.login_success",
            entity_type="user",
            entity_id=manager.id,
            new_value={"email": manager.email},
            ip_address="127.0.0.1",
            user_agent="seed/1.0",
        ),
    ]
    if claim is not None:
        samples.append(
            AuditLog(
                actor_id=manager.id,
                actor_role=manager.role,
                action="claim.approved",
                entity_type="claim",
                entity_id=claim.id,
                old_value={"status": "investigating"},
                new_value={"status": "approved", "approved_amount": "4200.00"},
                ip_address="127.0.0.1",
                user_agent="seed/1.0",
            )
        )
    db.add_all(samples)
    print(f"  + created {len(samples)} sample audit log entries")


async def _ensure_demo_declaration(db, policy: Policy, agent: User) -> None:
    """Give the demo policy a real declaration PDF to download.

    The demo policy is inserted directly rather than bound through the API, so
    it would otherwise miss the document that binding normally issues.
    """
    from app.services import pdf_service

    document = await pdf_service.try_generate(
        pdf_service.generate_policy_declaration(db, policy, agent.id),
        description=f"declaration for {policy.policy_number}",
    )
    if document is None:
        print("  ! could not generate declaration PDF (is MinIO running?)")
    else:
        print(f"  + generated {document.file_name}")


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        staff = await _ensure_staff(db)
        customer = await _ensure_demo_customer(db, staff[UserRole.agent])
        policy = await _ensure_demo_policy(db, customer, staff[UserRole.agent])
        await _ensure_premium_schedule(db, policy)
        await _ensure_demo_premium_payments(
            db, policy, customer, staff[UserRole.agent]
        )
        claims = await _ensure_demo_claims(
            db, policy, customer, staff[UserRole.adjuster]
        )
        await _ensure_welcome_notification(db, customer)
        sample_claim = claims[0] if claims else None
        await _ensure_demo_audit(
            db,
            manager=staff[UserRole.manager],
            agent=staff[UserRole.agent],
            policy=policy,
            claim=sample_claim,
        )
        print("Expanded demo data:")
        await ensure_expanded_demo(
            db,
            primary_customer=customer,
            primary_policy=policy,
            staff=staff,
        )
        await db.commit()
        await _ensure_demo_declaration(db, policy, staff[UserRole.agent])
    print("Seed complete.")
    print(
        "Demo logins: "
        f"{DEMO_CUSTOMER_EMAIL}/{DEMO_CUSTOMER_PASSWORD}, "
        "agent@insureco.com/Agent123!, "
        "adjuster@insureco.com/Adjuster123!, "
        "manager@insureco.com/Manager123!, "
        "admin@insureco.com/Admin123!"
    )
    print(
        "Extra customers: homeowner@insureco.com / Customer123!, "
        "lifeholder@insureco.com / Customer123!"
    )


if __name__ == "__main__":
    asyncio.run(seed())
