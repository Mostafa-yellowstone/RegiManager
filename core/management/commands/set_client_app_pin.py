from django.core.management.base import BaseCommand, CommandError

from core.models import Client


class Command(BaseCommand):
    help = "Set or replace a client's mobile wallet PIN and enable app access."

    def add_arguments(self, parser):
        parser.add_argument("--client-id", type=int, required=True)
        parser.add_argument("--pin", type=str, required=True, help="4–8 digit PIN")

    def handle(self, *args, **options):
        client_id = options["client_id"]
        pin = "".join(ch for ch in (options["pin"] or "") if ch.isdigit())
        if not (4 <= len(pin) <= 8):
            raise CommandError("PIN must be 4–8 digits.")

        client = Client.objects.filter(id=client_id).first()
        if not client:
            raise CommandError(f"Client {client_id} not found.")

        client.set_app_pin(pin)
        client.app_access_enabled = True
        client.save(update_fields=["app_pin_hash", "app_access_enabled"])
        client.refresh_from_db(fields=["app_pin_hash", "app_access_enabled"])

        if not client.check_app_pin(pin):
            raise CommandError("PIN saved but verification failed.")

        self.stdout.write(
            self.style.SUCCESS(
                f"OK — client #{client.id} ({client.full_display_name}) "
                f"enabled. Phone={client.phone_number or '—'} email={client.email or '—'} "
                f"portal={client.organization.portal_token or '—'}"
            )
        )
