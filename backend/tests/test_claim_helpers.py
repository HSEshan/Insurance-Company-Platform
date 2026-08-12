"""Unit tests for claim number formatting and fraud scoring."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.claim_service import (
    FRAUD_FLAG_THRESHOLD,
    LARGE_CLAIM_THRESHOLD,
    build_claim_number,
    score_claim_fraud,
)


def test_claim_number_format() -> None:
    assert build_claim_number(2026, 4521) == "CLM-2026-004521"


def test_fraud_score_clean_claim_is_low() -> None:
    score, flagged, signals = score_claim_fraud(
        policy_effective=date(2025, 1, 1),
        incident_date=date(2026, 6, 1),
        reported_date=date(2026, 6, 2),
        estimated_damage=Decimal("2000"),
        prior_claims_12mo=0,
    )
    assert score == Decimal("0.000")
    assert flagged is False
    assert signals == []


def test_fraud_score_flags_early_high_damage_late_report() -> None:
    score, flagged, signals = score_claim_fraud(
        policy_effective=date(2026, 7, 1),
        incident_date=date(2026, 7, 5),
        reported_date=date(2026, 7, 25),
        estimated_damage=Decimal("75000"),
        prior_claims_12mo=3,
    )
    assert flagged is True
    assert score >= FRAUD_FLAG_THRESHOLD
    assert len(signals) >= 3


def test_large_claim_threshold() -> None:
    assert LARGE_CLAIM_THRESHOLD == Decimal("10000")
