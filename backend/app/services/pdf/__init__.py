"""Deterministic PDF rendering for carrier-issued documents.

Pure and I/O-free by design: renderers take plain dataclasses and return bytes.
Storing the result is the caller's job (see ``services/pdf_service.py``).
"""

from app.services.pdf.content import (
    DecisionLetterData,
    DeclarationData,
    PartyDetails,
)
from app.services.pdf.decision_letter import render_claim_decision_letter
from app.services.pdf.declaration import render_policy_declaration

__all__ = [
    "DeclarationData",
    "DecisionLetterData",
    "PartyDetails",
    "render_claim_decision_letter",
    "render_policy_declaration",
]
