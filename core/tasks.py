from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from .models import Vehicle, ServiceRecord, AutomationLog, Client
from django.db.models import Q

@shared_task
def send_automation_email(to_email, subject, template_name, context):
    """
    Base task to send templated emails.
    """
    html_message = render_to_string(template_name, context)
    # Plain text version for fallback
    message = f"{subject}\n\n"
    for key, value in context.items():
        if isinstance(value, str):
            message += f"{key.replace('_', ' ').title()}: {value}\n"
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [to_email],
            html_message=html_message,
            fail_silently=False,
        )
        return "sent"
    except Exception:
        # Never let transient mail/network errors crash request flow
        # (important when Celery eager mode is enabled).
        return "failed"

def process_vehicle_reminder(vehicle_id, days, log_type, force_sync=False):
    """
    Atomic task to process a reminder for a single vehicle.
    Allows for parallel processing and individual retries.
    """
    try:
        vehicle = Vehicle.objects.get(id=vehicle_id)
        client = vehicle.client
        if not client.email:
            return f"No email for client of vehicle {vehicle_id}"

        # 1. Check if reminders should be stopped
        is_renewed = ServiceRecord.objects.filter(
            vehicle=vehicle,
            status='completed',
            service_type__in=['registration_renewal', 'vehicle_registration']
        ).exists()
        
        explicitly_stopped = ServiceRecord.objects.filter(
            vehicle=vehicle,
            reminders_stopped=True
        ).exists()

        if is_renewed or explicitly_stopped:
            return f"Reminders stopped for vehicle {vehicle_id}"

        # 2. Prevent duplicate reminders for the same day/type (unless forced sync)
        now = timezone.localdate()
        if not force_sync and AutomationLog.objects.filter(
            vehicle=vehicle, 
            log_type=log_type, 
            timestamp__date=now
        ).exists():
            return f"Reminder {log_type} already sent today for vehicle {vehicle_id}"

        # 3. Send Email
        if days == 0:
            subject = "URGENT: Your vehicle registration expires TODAY"
        elif days < 0:
            subject = "URGENT: Your registration has expired"
        else:
            subject = f"Reminder: Your vehicle registration expires in {days} days"

        template = "core/emails/reminder.html" if days >= 0 else "core/emails/expired_warning.html"
        
        context = {
            "client_name": client.name,
            "vehicle_name": str(vehicle),
            "expiration_date": vehicle.registration_expiration_date.strftime("%B %d, %Y") if vehicle.registration_expiration_date else "N/A",
            "days_left": days,
            "cta_link": f"{settings.BASE_URL}/dashboard/vehicles/{vehicle.id}/" if hasattr(settings, 'BASE_URL') else "#",
        }
        
        if force_sync:
            send_automation_email(client.email, subject, template, context)
        else:
            send_automation_email.delay(client.email, subject, template, context)
        
        # 4. Log the automation
        AutomationLog.objects.create(
            organization=client.organization,
            vehicle=vehicle,
            client=client,
            log_type=log_type,
            sent_to=client.email,
            details=f"Automated {days}-day reminder sent." if days >= 0 else "Expired registration warning sent."
        )

        # 5. Smart Escalation
        if days >= 0:
            reminder_count = AutomationLog.objects.filter(vehicle=vehicle, log_type__startswith="reminder_").count()
            if reminder_count >= 2:
                vehicle.is_priority = True
                vehicle.save()

        return f"Successfully processed {log_type} for vehicle {vehicle_id}"
    except Vehicle.DoesNotExist:
        return f"Vehicle {vehicle_id} not found"


@shared_task
def check_registration_reminders():
    """
    Main orchestrator task. Finds vehicles needing reminders and spawns atomic sub-tasks.
    Runs every 6-12 hours.
    """
    now = timezone.localdate()
    intervals = [45, 30, 15, 0]
    
    # 1. Process upcoming expirations
    for days in intervals:
        target_date = now + timedelta(days=days)
        vehicle_ids = Vehicle.objects.filter(registration_expiration_date=target_date).values_list('id', flat=True)
        
        log_type = f"reminder_{days}" if days > 0 else "final_warning"
        for vid in vehicle_ids:
            process_vehicle_reminder.delay(vid, days, log_type)

    # 2. Process post-expiration logic
    expired_vehicle_ids = Vehicle.objects.filter(
        registration_expiration_date__lt=now
    ).exclude(
        automation_logs__log_type="expired_warning"
    ).distinct().values_list('id', flat=True)

    for vid in expired_vehicle_ids:
        process_vehicle_reminder.delay(vid, -1, "expired_warning")
