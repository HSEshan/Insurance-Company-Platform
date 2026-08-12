"""Outbound email via SMTP (MailHog locally, real SMTP in production).

Kept separate from notification persistence so a mail outage never rolls back
an in-app notification the user already needs to see.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_email(*, to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns False (and logs) on failure."""
    if not settings.EMAIL_NOTIFICATIONS_ENABLED:
        logger.info("Email notifications disabled; skipping send to %s", to)
        return False

    message = EmailMessage()
    message["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.MAIL_SERVER,
            port=settings.MAIL_PORT,
            # MailHog accepts unauthenticated plaintext SMTP.
            start_tls=False,
            use_tls=False,
        )
    except Exception:
        logger.exception("Failed to send email to %s (%s)", to, subject)
        return False
    return True
