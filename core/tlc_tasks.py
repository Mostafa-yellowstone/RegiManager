"""Celery tasks for TLC installment email reminders."""

from __future__ import annotations

from datetime import datetime, timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .tlc_models import TLCInstallmentReminder


@shared_task
def send_tlc_installment_reminder(reminder_id: int) -> str:
    reminder = TLCInstallmentReminder.objects.select_related(
        "policy", "policy__client", "installment"
    ).filter(id=reminder_id).first()
    if not reminder or reminder.status != TLCInstallmentReminder.Status.PENDING:
        return "skipped"

    policy = reminder.policy
    installment = reminder.installment
    to_email = reminder.recipient_email
    if not to_email and policy.client:
        to_email = policy.client.email
    if reminder.channel == TLCInstallmentReminder.Channel.SMS:
        reminder.status = TLCInstallmentReminder.Status.FAILED
        reminder.error_message = "SMS channel not configured yet."
        reminder.save(update_fields=["status", "error_message"])
        return "sms_not_configured"
    if not to_email:
        reminder.status = TLCInstallmentReminder.Status.FAILED
        reminder.error_message = "No recipient email on file."
        reminder.save(update_fields=["status", "error_message"])
        return "no_email"

    amount = installment.amount if installment else policy.premium_breakdown.monthly_installment
    fee = installment.installment_fee if installment else 0
    due = installment.due_date if installment else policy.effective_date
    subject = f"TLC policy installment reminder — {policy.policy_number}"
    body = (
        f"Hello,\n\n"
        f"This is a reminder for TLC policy {policy.policy_number}.\n"
        f"Amount due: ${amount} + installment fee ${fee}\n"
        f"Due date: {due}\n\n"
        f"Please contact {policy.organization.name} to make payment.\n"
    )
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [to_email],
            fail_silently=False,
        )
        reminder.status = TLCInstallmentReminder.Status.SENT
        reminder.sent_at = timezone.now()
        reminder.error_message = ""
        reminder.save(update_fields=["status", "sent_at", "error_message"])
        return "sent"
    except Exception as exc:
        reminder.status = TLCInstallmentReminder.Status.FAILED
        reminder.error_message = str(exc)[:500]
        reminder.save(update_fields=["status", "error_message"])
        return "failed"


@shared_task
def dispatch_due_tlc_installment_reminders() -> int:
    """Send all TLC installment reminders that are due now."""
    now = timezone.now()
    due_ids = list(
        TLCInstallmentReminder.objects.filter(
            status=TLCInstallmentReminder.Status.PENDING,
            scheduled_for__lte=now,
        ).values_list("id", flat=True)[:200]
    )
    for reminder_id in due_ids:
        send_tlc_installment_reminder.delay(reminder_id)
    return len(due_ids)


def schedule_installment_reminders(policy, *, days_before: int = 3) -> int:
    """Create email reminders for all unpaid future installments on a policy."""
    from .tlc_models import TLCInstallmentReminder

    created = 0
    client_email = policy.client.email if policy.client else ""
    for inst in policy.installments.filter(is_paid=False):
        if not inst.due_date:
            continue
        scheduled_for = timezone.make_aware(
            datetime.combine(
                inst.due_date - timedelta(days=days_before),
                datetime.min.time(),
            )
        )
        reminder, was_created = TLCInstallmentReminder.objects.get_or_create(
            policy=policy,
            installment=inst,
            channel=TLCInstallmentReminder.Channel.EMAIL,
            days_before_due=days_before,
            defaults={
                "scheduled_for": scheduled_for,
                "recipient_email": client_email,
                "recipient_phone": policy.client.phone_number if policy.client else "",
            },
        )
        if was_created:
            created += 1
    return created
