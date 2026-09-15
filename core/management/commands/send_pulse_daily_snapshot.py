"""Create in-app daily Pulse snapshot notifications for owners/managers.

Schedule via cron, e.g.:
  0 18 * * * cd /app && python manage.py send_pulse_daily_snapshot
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum
from django.utils import timezone

from core.models import Organization, ServiceRecord
from core.owner_notifications import notify_pulse_daily_snapshot


class Command(BaseCommand):
    help = "Send Pulse daily snapshot notifications (yesterday's DMV processing fee + count)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="work_date",
            default="",
            help="YYYY-MM-DD snapshot day (defaults to yesterday in local time).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print counts without creating notifications.",
        )

    def handle(self, *args, **options):
        if options["work_date"]:
            from datetime import date as date_cls

            work_date = date_cls.fromisoformat(options["work_date"])
        else:
            work_date = timezone.localdate() - timedelta(days=1)

        orgs = Organization.objects.filter(is_active=True)
        total = 0
        for org in orgs:
            qs = ServiceRecord.objects.filter(
                organization=org,
                transaction_date=work_date,
            )
            agg = qs.aggregate(
                records=Count("id"),
                processing=Sum("processing_fee"),
            )
            records = agg["records"] or 0
            processing = Decimal(agg["processing"] or 0)
            if options["dry_run"]:
                self.stdout.write(
                    f"[dry-run] {org.name}: {records} records, ${processing}"
                )
                continue
            created = notify_pulse_daily_snapshot(
                organization=org,
                work_date=work_date,
                records=records,
                processing_fee=processing,
            )
            total += created
            self.stdout.write(f"{org.name}: {created} notification(s)")

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created {total} notifications for {work_date}.")
        )
