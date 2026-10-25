"""Outbound delivery channels for verification and sign-in codes.

Callers depend only on ``EmailSender`` / ``SmsSender``; which implementation is
used is a config switch (``VERIFICATION_EMAIL_PROVIDER`` / ``SMS_PROVIDER``).
Plugging in a real provider (SendGrid, SES, Twilio, ...) means adding a class
with the same ``send`` signature and a branch in the matching ``get_*`` factory.

The simulated senders never leave the process: they log the message and return
a receipt flagged ``simulated`` so the API can (optionally) echo the code back
for demos. Real senders must return ``simulated=False``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from app.core.config import settings
from app.services import email_service

logger = logging.getLogger(__name__)

Channel = Literal["email", "sms"]


@dataclass(frozen=True)
class DeliveryReceipt:
    channel: Channel
    provider: str
    destination: str
    delivered: bool
    simulated: bool


class EmailSender(Protocol):
    name: str

    async def send(self, *, to: str, subject: str, body: str) -> DeliveryReceipt: ...


class SmsSender(Protocol):
    name: str

    async def send(self, *, to: str, body: str) -> DeliveryReceipt: ...


# --------------------------------------------------------------------------- #
# Masking helpers (destinations are shown to the user and written to logs)     #
# --------------------------------------------------------------------------- #
def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    visible = local[:1]
    return f"{visible}{'*' * max(len(local) - 1, 2)}@{domain}"


def mask_phone(phone: str) -> str:
    digits = [c for c in phone if c.isdigit()]
    if len(digits) < 4:
        return "***"
    return f"***-***-{''.join(digits[-4:])}"


# --------------------------------------------------------------------------- #
# Email                                                                        #
# --------------------------------------------------------------------------- #
class SimulatedEmailSender:
    name = "simulated"

    async def send(self, *, to: str, subject: str, body: str) -> DeliveryReceipt:
        logger.info(
            "[simulated email] to=%s subject=%r\n%s", mask_email(to), subject, body
        )
        return DeliveryReceipt("email", self.name, to, delivered=True, simulated=True)


class SmtpEmailSender:
    """Real SMTP delivery (MailHog locally) via the shared ``email_service``."""

    name = "smtp"

    async def send(self, *, to: str, subject: str, body: str) -> DeliveryReceipt:
        delivered = await email_service.send_email(to=to, subject=subject, body=body)
        return DeliveryReceipt("email", self.name, to, delivered=delivered, simulated=False)


# --------------------------------------------------------------------------- #
# SMS                                                                          #
# --------------------------------------------------------------------------- #
class SimulatedSmsSender:
    name = "simulated"

    async def send(self, *, to: str, body: str) -> DeliveryReceipt:
        logger.info("[simulated sms] to=%s\n%s", mask_phone(to), body)
        return DeliveryReceipt("sms", self.name, to, delivered=True, simulated=True)


def get_email_sender() -> EmailSender:
    if settings.VERIFICATION_EMAIL_PROVIDER == "smtp":
        return SmtpEmailSender()
    return SimulatedEmailSender()


def get_sms_sender() -> SmsSender:
    return SimulatedSmsSender()
