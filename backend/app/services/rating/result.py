"""Result types shared by the rating engine."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import RiskTier


class RatingFactor(BaseModel):
    """A single named adjustment applied to the base premium."""

    name: str
    multiplier: float


class RatingResult(BaseModel):
    """The full, explainable output of a rating calculation."""

    base_premium: Decimal
    factors: list[RatingFactor]
    annual_premium: Decimal
    monthly_premium: Decimal
    risk_tier: RiskTier
    declined: bool = False
    decline_reasons: list[str] = []
