"""Unit tests for endorsement approval thresholds and numbering helpers."""

from __future__ import annotations

from decimal import Decimal

from app.services.endorsement_service import LARGE_ENDORSEMENT_THRESHOLD


def test_large_endorsement_threshold_is_five_hundred() -> None:
    assert LARGE_ENDORSEMENT_THRESHOLD == Decimal("500")
