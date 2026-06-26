from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.intake_profit_metrics import build_intake_source_profit_cards
from core.models import Client, Organization, ServiceRecord, User, Vehicle
from core.source_choices import resolve_acquisition_source_for_record


class AcquisitionSourceResolutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sourceuser", password="password123")
        self.org = Organization.objects.create(name="Source Org", city="NYC")

    def test_resolve_prefers_client_source_over_default_receipt_source(self):
        client = Client.objects.create(
            organization=self.org,
            first_name="Google",
            last_name="Lead",
            gender="male",
            phone_number="5551112222",
            source="google_search",
        )
        vehicle = Vehicle.objects.create(
            client=client,
            vin="VINGOOGLE12345678",
            vehicle_type="passenger",
            fuel_type="gas",
        )
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=vehicle,
            service_type="vehicle_registration",
            source="walk-in",
            processing_fee=Decimal("80.00"),
            transaction_date=date(2026, 6, 5),
            receipt_number=f"RCPT-SOURCE-1-{self.org.id}",
        )
        self.assertEqual(resolve_acquisition_source_for_record(record), "google_search")

    def test_profit_cards_bucket_by_client_source_not_receipt_default(self):
        client = Client.objects.create(
            organization=self.org,
            first_name="Meta",
            last_name="Lead",
            gender="male",
            phone_number="5553334444",
            source="meta_platform",
        )
        vehicle = Vehicle.objects.create(
            client=client,
            vin="VINMETA1234567890",
            vehicle_type="passenger",
            fuel_type="gas",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=vehicle,
            service_type="vehicle_registration",
            source="walk-in",
            processing_fee=Decimal("120.00"),
            transaction_date=date(2026, 6, 8),
            receipt_number=f"RCPT-SOURCE-2-{self.org.id}",
        )
        source_choices = [
            {"key": "walk_in", "label": "Walk-In"},
            {"key": "meta_platform", "label": "Meta Platform"},
        ]
        records = ServiceRecord.objects.filter(organization=self.org).select_related(
            "vehicle__client"
        )
        cards, total = build_intake_source_profit_cards(records, source_choices)
        by_key = {card["key"]: card for card in cards}
        self.assertEqual(by_key["meta_platform"]["net_profit"], Decimal("120.00"))
        self.assertEqual(by_key["meta_platform"]["transaction_count"], 1)
        self.assertEqual(by_key["walk_in"]["net_profit"], Decimal("0.00"))
        self.assertEqual(by_key["walk_in"]["transaction_count"], 0)
        self.assertEqual(total, Decimal("120.00"))
