from django.core.management.base import BaseCommand
from core.tasks import check_registration_reminders

class Command(BaseCommand):
    help = 'Manually trigger registration reminders'

    def handle(self, *args, **options):
        self.stdout.write("Checking for registration reminders...")
        check_registration_reminders()
        self.stdout.write(self.style.SUCCESS("Successfully checked and sent reminders."))
