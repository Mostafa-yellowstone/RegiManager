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
DIRECT_MX_HOST = "regimanager-com.mail.protection.outlook.com"


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


def direct_mx_host() -> str:
    """Inbound mail server for CONTACT_INBOX; delivery there needs no SMTP login. Empty disables it."""
    return (getattr(settings, "CONTACT_DIRECT_MX_HOST", DIRECT_MX_HOST) or "").strip()


def _direct_connection():
    """Hand mail to the inbox's own mail server on port 25, like any outside sender (no username/password)."""
    return get_connection(
        "django.core.mail.backends.smtp.EmailBackend",
        host=direct_mx_host(),
        port=25,
        username="",
        password="",
        use_tls=True,
        use_ssl=False,
        timeout=SEND_TIMEOUT_SECONDS,
        fail_silently=False,
    )


def _build_email(record, recipients, connection) -> EmailMessage:
    return EmailMessage(
        subject=f"RegiManager contact: {_single_line(record.subject, 80)} from {_single_line(record.name, 80)}",
        body=(
            f"From: {record.name} <{record.email}>\n"
            f"Topic: {record.subject}\n"
            f"IP: {record.ip_address or 'unknown'}\n\n"
            f"{record.message}\n\n"
            "Reply to this email to answer the sender directly.\n"
        ),
        from_email=outbound_from_email(),
        to=recipients,
        reply_to=[record.email],
        connection=connection,
    )


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def deliver_contact_message(message_id: int) -> bool:
    """Email one saved message to the team; records the outcome on the row. Returns True when sent.

    Tries the site's normal SMTP login first. If that fails (for example Microsoft 365 rejecting
    SMTP AUTH), delivers straight to the inbox's mail server, which only accepts mail for its own domain.
    """
    from .models import ContactMessage

    record = ContactMessage.objects.filter(id=message_id).first()
    if record is None:
        return False
    recipients = contact_recipients()
    try:
        _build_email(
            record, recipients, get_connection(fail_silently=False, timeout=SEND_TIMEOUT_SECONDS)
        ).send(fail_silently=False)
    except Exception as exc:
        primary_error = _error_text(exc)
        logger.warning("Contact message %s: SMTP login send failed (%s); trying direct delivery", message_id, primary_error)
    else:
        ContactMessage.objects.filter(id=message_id).update(email_sent=True, email_error="")
        logger.info("Contact message %s emailed to %s", message_id, ", ".join(recipients))
        return True

    inbox_domain = CONTACT_INBOX.rsplit("@", 1)[1].lower()
    direct_recipients = [r for r in recipients if r.lower().endswith("@" + inbox_domain)]
    if not direct_mx_host() or not direct_recipients:
        ContactMessage.objects.filter(id=message_id).update(email_sent=False, email_error=primary_error[:255])
        return False
    try:
        _build_email(record, direct_recipients, _direct_connection()).send(fail_silently=False)
    except Exception as exc:
        logger.exception("Contact message %s could not be emailed", message_id)
        ContactMessage.objects.filter(id=message_id).update(
            email_sent=False,
            email_error=f"Login: {primary_error[:110]} | Direct: {_error_text(exc)}"[:255],
        )
        return False
    ContactMessage.objects.filter(id=message_id).update(email_sent=True, email_error="")
    logger.info("Contact message %s delivered directly to %s", message_id, ", ".join(direct_recipients))
    return True


def queue_contact_email(message_id: int) -> None:
    """Email the team once the message row is committed."""

    def _send():
        try:
            deliver_contact_message(message_id)
        except Exception:
            logger.exception("Contact message %s delivery crashed", message_id)

    transaction.on_commit(_send)
