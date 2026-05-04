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
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        html_message=html_message,
        fail_silently=False,
    )

@shared_task
def check_registration_reminders():
    """
    Periodic task to check for upcoming registration expirations and send reminders.
    Runs every 6-12 hours.
    """
    now = timezone.localdate()
    
    # 1. Confirmation logic is handled in the view when process starts.
    
    # 2. Automation Logic (Reminders)
    # 45 days, 30 days, 15 days, Same day (0 days)
    intervals = [45, 30, 15, 0]
    
    for days in intervals:
        target_date = now + timedelta(days=days)
        
        # Find vehicles expiring on the target date
        vehicles = Vehicle.objects.filter(registration_expiration_date=target_date)
        
        for vehicle in vehicles:
            client = vehicle.client
            if not client.email:
                continue
                
            # Check if reminders should be stopped (if there's a completed renewal record)
            # Or if it's explicitly stopped
            is_renewed = ServiceRecord.objects.filter(
                vehicle=vehicle,
                status='completed',
                service_type__in=['registration_renewal', 'vehicle_registration']
            ).exists()
            
            # Check if any associated record has reminders_stopped=True
            explicitly_stopped = ServiceRecord.objects.filter(
                vehicle=vehicle,
                reminders_stopped=True
            ).exists()

            if is_renewed or explicitly_stopped:
                continue

            # Determine log type
            log_type = f"reminder_{days}" if days > 0 else "final_warning"
            
            # Prevent duplicate reminders for the same day/type
            if AutomationLog.objects.filter(
                vehicle=vehicle, 
                log_type=log_type, 
                timestamp__date=now
            ).exists():
                continue

            # Send Email
            subject = f"Reminder: Your vehicle registration expires in {days} days" if days > 0 else "URGENT: Your vehicle registration expires TODAY"
            template = "core/emails/reminder.html"
            
            context = {
                "client_name": client.name,
                "vehicle_name": str(vehicle),
                "expiration_date": vehicle.registration_expiration_date.strftime("%B %d, %Y"),
                "days_left": days,
                "cta_link": f"{settings.BASE_URL}/dashboard/vehicles/{vehicle.id}/" if hasattr(settings, 'BASE_URL') else "#",
            }
            
            send_automation_email.delay(client.email, subject, template, context)
            
            # Log the automation
            AutomationLog.objects.create(
                organization=client.organization,
                vehicle=vehicle,
                client=client,
                log_type=log_type,
                sent_to=client.email,
                details=f"Automated {days}-day reminder sent."
            )

    # 3. Post-Expiration Logic (Expired Warning)
    expired_vehicles = Vehicle.objects.filter(registration_expiration_date__lt=now)
    for vehicle in expired_vehicles:
        client = vehicle.client
        if not client.email:
            continue
            
        # Stop if renewed
        if ServiceRecord.objects.filter(
            vehicle=vehicle,
            status='completed',
            service_type__in=['registration_renewal', 'vehicle_registration']
        ).exists() or ServiceRecord.objects.filter(vehicle=vehicle, reminders_stopped=True).exists():
            continue

        # Check if already sent expired warning recently (once after expiration)
        if AutomationLog.objects.filter(vehicle=vehicle, log_type="expired_warning").exists():
            continue
            
        # Send Expired Warning
        subject = "URGENT: Your registration has expired"
        template = "core/emails/expired_warning.html"
        
        context = {
            "client_name": client.name,
            "vehicle_name": str(vehicle),
            "expiration_date": vehicle.registration_expiration_date.strftime("%B %d, %Y"),
            "cta_link": f"{settings.BASE_URL}/dashboard/vehicles/{vehicle.id}/" if hasattr(settings, 'BASE_URL') else "#",
        }
        
        send_automation_email.delay(client.email, subject, template, context)
        
        AutomationLog.objects.create(
            organization=client.organization,
            vehicle=vehicle,
            client=client,
            log_type="expired_warning",
            sent_to=client.email,
            details="Expired registration warning sent."
        )
        
        # 4. Smart Escalation (Optional preferred)
        # Escalate to agent if client ignores 2+ reminders
        reminder_count = AutomationLog.objects.filter(vehicle=vehicle, log_type__startswith="reminder_").count()
        if reminder_count >= 2:
            vehicle.is_priority = True
            vehicle.save()
