"""Celery tasks for bulk email campaign delivery."""

from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from .email_marketing_personalize import personalize_text, render_campaign_html
from .models import EmailCampaign, EmailCampaignBatch, EmailCampaignRecipient, EmailMarketingContact


@shared_task
def send_email_campaign_batch(batch_id: int):
    batch = EmailCampaignBatch.objects.select_related("campaign").get(pk=batch_id)
    campaign = batch.campaign
    logs = batch.recipient_logs.select_related("contact").filter(
        status=EmailCampaignRecipient.Status.PENDING,
    )

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
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[log.email],
            )
            message.attach_alternative(html_body, "text/html")
            message.send(fail_silently=False)
            log.status = EmailCampaignRecipient.Status.SENT
            log.sent_at = timezone.now()
            log.error_message = ""
            log.save(update_fields=["status", "sent_at", "error_message"])
            sent += 1
        except Exception as exc:
            log.status = EmailCampaignRecipient.Status.FAILED
            log.error_message = str(exc)[:500]
            log.save(update_fields=["status", "error_message"])
            failed += 1

    batch.sent_count = sent
    batch.failed_count = failed
    batch.save(update_fields=["sent_count", "failed_count"])

    campaign.status = EmailCampaign.Status.SENT
    campaign.last_sent_at = timezone.now()
    campaign.save(update_fields=["status", "last_sent_at"])
    return {"batch_id": batch_id, "sent": sent, "failed": failed}
