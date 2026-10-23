from django.core.management.base import BaseCommand

from core.contact_inbox import contact_recipients, deliver_contact_message
from core.models import ContactMessage


class Command(BaseCommand):
    help = "Email Contact page messages that were saved but never delivered (use --test to send a test message)."

    def add_arguments(self, parser):
        parser.add_argument("--test", action="store_true", help="Save and send one test message to check delivery.")

    def handle(self, *args, **options):
        recipients = ", ".join(contact_recipients())
        self.stdout.write(f"Contact messages go to: {recipients}")
        if options["test"]:
            record = ContactMessage.objects.create(
                name="RegiManager delivery test",
                email="noreply@regimanager.com",
                subject="General inquiry",
                message="Test from manage.py retry_contact_emails --test. If you can read this, the Contact page email works.",
                is_handled=True,
            )
            ids = [record.id]
        else:
            ids = list(ContactMessage.objects.filter(email_sent=False).order_by("created_at").values_list("id", flat=True))
        if not ids:
            self.stdout.write(self.style.SUCCESS("Nothing to send: every message was already emailed."))
            return
        sent = 0
        for message_id in ids:
            if deliver_contact_message(message_id):
                sent += 1
            else:
                error = ContactMessage.objects.filter(id=message_id).values_list("email_error", flat=True).first()
                self.stdout.write(self.style.ERROR(f"#{message_id} failed: {error}"))
        style = self.style.SUCCESS if sent == len(ids) else self.style.WARNING
        self.stdout.write(style(f"Emailed {sent} of {len(ids)}."))
