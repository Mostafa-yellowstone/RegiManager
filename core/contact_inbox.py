"""Contact-page messages: saved first, then emailed to the team in the background."""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import close_old_connections, transaction

from .email_branding import outbound_from_email

logger = logging.getLogger(__name__)

CONTACT_INBOX = "mail@regimanager.com"
CONTACT_SUBJECTS = ("General inquiry", "Sales and pricing", "Technical support", "Request a demo")


def _single_line(value: str, limit: int) -> str:
    return " ".join((value or "").split())[:limit]


def _deliver(message_id: int) -> None:
    from .models import ContactMessage

    record = ContactMessage.objects.filter(id=message_id).first()
    if record is None:
        return
    email = EmailMessage(
            subject=f"RegiManager contact: {_single_line(record.subject, 80)} from {_single_line(record.name, 80)}",
        body=(
            f"From: {record.name} <{record.email}>\n"
            f"Topic: {record.subject}\n"
            f"IP: {record.ip_address or 'unknown'}\n\n"
            f"{record.message}\n"
        ),
        from_email=outbound_from_email(),
        to=[getattr(settings, "CONTACT_INBOX_EMAIL", "") or CONTACT_INBOX],
        reply_to=[record.email],
    )
    try:
        email.send(fail_silently=False)
    except Exception as exc:
        logger.exception("Contact message %s could not be emailed", message_id)
        ContactMessage.objects.filter(id=message_id).update(
            email_error=f"{type(exc).__name__}: {exc}"[:255]
        )
        return
    ContactMessage.objects.filter(id=message_id).update(email_sent=True, email_error="")


def _deliver_in_thread(message_id: int) -> None:
    close_old_connections()
    try:
        _deliver(message_id)
    except Exception:
        logger.exception("Contact message %s delivery crashed", message_id)
    finally:
        close_old_connections()


def queue_contact_email(message_id: int) -> None:
    """Email the team after the message row is committed, without making the visitor wait on SMTP."""
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()

    def _start():
        if "locmem" in backend or "console" in backend:
            _deliver(message_id)
        else:
            threading.Thread(target=_deliver_in_thread, args=(message_id,), daemon=True).start()

    transaction.on_commit(_start)
