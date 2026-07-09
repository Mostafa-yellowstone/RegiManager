"""Celery tasks and delivery helpers for bulk email campaigns."""

from __future__ import annotations

import logging
import threading

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from .email_marketing_personalize import personalize_text, render_campaign_html
from .models import EmailCampaign, EmailCampaignBatch, EmailCampaignRecipient

logger = logging.getLogger(__name__)


def email_delivery_configured() -> bool:
    backend = getattr(settings, "EMAIL_BACKEND", "")
    if "console" in backend.lower():
        return True
    return bool(getattr(settings, "EMAIL_HOST_USER", "") and getattr(settings, "DEFAULT_FROM_EMAIL", ""))


def _celery_workers_available() -> bool:
    try:
        from celery import current_app

        inspect = current_app.control.inspect(timeout=0.5)
        stats = inspect.stats()
        return bool(stats)
    except Exception:
        return False


def _from_email_for_campaign(campaign: EmailCampaign) -> str:
    return getattr(settings, "DEFAULT_FROM_EMAIL", "") or "noreply@regimanager.local"


def execute_email_campaign_batch(batch_id: int) -> dict:
    """Send all pending recipients for a campaign batch."""
    batch = EmailCampaignBatch.objects.select_related("campaign", "campaign__organization").get(pk=batch_id)
    campaign = batch.campaign
    org = campaign.organization
    logs = list(
        batch.recipient_logs.select_related("contact").filter(
            status=EmailCampaignRecipient.Status.PENDING,
        )
    )

    from_email = _from_email_for_campaign(campaign)
    reply_to = [org.email] if getattr(org, "email", "") else None

    sent = 0
    failed = 0
    for log in logs:
        contact = log.contact
        if not log.email:
            log.status = EmailCampaignRecipient.Status.FAILED
            log.error_message = "Missing email address"
            log.save(update_fields=["status", "error_message"])
            failed += 1
            continue

        html_body = render_campaign_html(campaign.html_content, campaign.css_content, contact)
        subject = personalize_text(campaign.subject or campaign.name, contact)
        plain = f"{subject}\n\nView this message in an HTML-capable email client."
        try:
            message = EmailMultiAlternatives(
                subject=subject,
                body=plain,
                from_email=from_email,
                to=[log.email],
                reply_to=reply_to,
            )
            message.attach_alternative(html_body, "text/html")
            message.send(fail_silently=False)
            log.status = EmailCampaignRecipient.Status.SENT
            log.sent_at = timezone.now()
            log.error_message = ""
            log.save(update_fields=["status", "sent_at", "error_message"])
            sent += 1
        except Exception as exc:
            logger.exception("Campaign email failed for batch=%s recipient=%s", batch_id, log.id)
            log.status = EmailCampaignRecipient.Status.FAILED
            log.error_message = str(exc)[:500]
            log.save(update_fields=["status", "error_message"])
            failed += 1

    batch.sent_count = sent
    batch.failed_count = failed
    batch.save(update_fields=["sent_count", "failed_count"])

    if sent > 0:
        campaign.status = EmailCampaign.Status.SENT
        campaign.last_sent_at = timezone.now()
        campaign.save(update_fields=["status", "last_sent_at"])

    return {"batch_id": batch_id, "sent": sent, "failed": failed, "total": len(logs)}


@shared_task
def send_email_campaign_batch(batch_id: int):
    return execute_email_campaign_batch(batch_id)


def dispatch_email_campaign_batch(batch_id: int) -> str:
    """
    Queue campaign delivery when a Celery worker is available.
    Otherwise send immediately so messages reach inboxes without a worker.
    """
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        execute_email_campaign_batch(batch_id)
        return "sent"

    if _celery_workers_available():
        try:
            send_email_campaign_batch.delay(batch_id)
            return "queued"
        except Exception:
            logger.exception("Celery queue failed for campaign batch %s", batch_id)

    batch = EmailCampaignBatch.objects.only("recipient_count").get(pk=batch_id)
    if batch.recipient_count <= 40:
        execute_email_campaign_batch(batch_id)
        return "sent"

    thread = threading.Thread(target=execute_email_campaign_batch, args=(batch_id,), daemon=True)
    thread.start()
    return "sending"
