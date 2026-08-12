"""Aggregate model imports so Alembic autogenerate sees every table."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.billing import Payment, PremiumSchedule
from app.models.chat import ChatMessage, ChatSession
from app.models.claim import Claim, ClaimNote
from app.models.customer import Customer
from app.models.document import Document
from app.models.notification import Notification
from app.models.policy import (
    Beneficiary,
    Endorsement,
    Policy,
    PolicyAutoDetails,
    PolicyHomeDetails,
    PolicyLifeDetails,
)
from app.models.quote import Quote
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Customer",
    "Quote",
    "Policy",
    "PolicyAutoDetails",
    "PolicyHomeDetails",
    "PolicyLifeDetails",
    "Beneficiary",
    "Endorsement",
    "PremiumSchedule",
    "Payment",
    "Claim",
    "ClaimNote",
    "Document",
    "Notification",
    "AuditLog",
    "ChatSession",
    "ChatMessage",
]
