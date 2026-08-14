"""Result types shared by the rating engine."""

from __future__ import annotations

from decimal import Decimal

from pydantic import AliasChoices, BaseModel, Field

from app.models.enums import RiskTier


class RatingFactor(BaseModel):
    """A single named adjustment applied to the base premium.

    Older quotes stored the value as ``factor``; accept that alias so GET
    /quotes/{id} still serializes those rows.
    """

    name: str
    multiplier: float = Field(validation_alias=AliasChoices("multiplier", "factor"))


class RatingResult(BaseModel):
    """The full, explainable output of a rating calculation."""

    base_premium: Decimal
    factors: list[RatingFactor]
    annual_premium: Decimal
    monthly_premium: Decimal
    risk_tier: RiskTier
    declined: bool = False
    decline_reasons: list[str] = []
