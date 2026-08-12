"""Deterministic premium rating engine (Phase 2).

Public entrypoints:
    rate_auto(inputs)  -> RatingResult
    rate_home(inputs)  -> RatingResult
    rate_life(inputs)  -> RatingResult
    rate_quote(policy_type, inputs) -> RatingResult
"""

from app.services.rating.engine import (
    rate_auto,
    rate_home,
    rate_life,
    rate_quote,
)
from app.services.rating.inputs import (
    AutoRatingInput,
    HomeRatingInput,
    LifeRatingInput,
)
from app.services.rating.result import RatingFactor, RatingResult

__all__ = [
    "rate_auto",
    "rate_home",
    "rate_life",
    "rate_quote",
    "AutoRatingInput",
    "HomeRatingInput",
    "LifeRatingInput",
    "RatingFactor",
    "RatingResult",
]
