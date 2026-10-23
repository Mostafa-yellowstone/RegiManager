"""Contact-page messages: saved first, then emailed to the team."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import transaction

from .email_branding import outbound_from_email

logger = logging.getLogger(__name__)

CONTACT_INBOX = "mail@regimanager.com"
CONTACT_SUBJECTS = ("General inquiry", "Sales and pricing", "Technical support", "Request a demo")
SEND_TIMEOUT_SECONDS = 12


def _single_line(value: str, limit: int) -> str:
    return " ".join((value or "").split())[:limit]


def contact_recipients() -> list[str]:
    """Always mail@regimanager.com, plus any extra CONTACT_INBOX_EMAIL addresses (comma separated)."""
    configured = getattr(settings, "CONTACT_INBOX_EMAIL", "") or ""
    recipients = [CONTACT_INBOX]
    for part in configured.split(","):
        address = part.strip()
        if "@" in address and address.lower() not in {r.lower() for r in recipients}:
            recipients.append(address)
    return recipients


def deliver_contact_message(message_id: int) -> bool:
    """Email one saved message to the team; records the outcome on the row. Returns True when sent."""
    from .models import ContactMessage

    record = ContactMessage.objects.filter(id=message_id).first()
    if record is None:
        return False
    email = EmailMessage(
        subject=f"RegiManager contact: {_single_line(record.subject, 80)} from {_single_line(record.name, 80)}",
        body=(
            f"From: {record.name} <{record.email}>\n"
            f"Topic: {record.subject}\n"
            f"IP: {record.ip_address or 'unknown'}\n\n"
            f"{record.message}\n\n"
            "Reply to this email to answer the sender directly.\n"
        ),
        from_email=outbound_from_email(),
        to=contact_recipients(),
        reply_to=[record.email],
        connection=get_connection(fail_silently=False, timeout=SEND_TIMEOUT_SECONDS),
    )
    try:
        email.send(fail_silently=False)
    except Exception as exc:
        logger.exception("Contact message %s could not be emailed", message_id)
        ContactMessage.objects.filter(id=message_id).update(
            email_sent=False, email_error=f"{type(exc).__name__}: {exc}"[:255]
        )
        return False
    ContactMessage.objects.filter(id=message_id).update(email_sent=True, email_error="")
    logger.info("Contact message %s emailed to %s", message_id, ", ".join(email.to))
    return True


def queue_contact_email(message_id: int) -> None:
    """Email the team once the message row is committed."""

    def _send():
        try:
            deliver_contact_message(message_id)
        except Exception:
            logger.exception("Contact message %s delivery crashed", message_id)

    transaction.on_commit(_send)
