from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.intake_profit_metrics import build_intake_source_profit_cards
from core.models import Organization, Referral, ServiceRecord, User


class IntakeProfitMetricsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="profituser", password="password123")
        self.org = Organization.objects.create(name="Profit Org", city="NYC")

    def test_build_intake_source_profit_cards_groups_by_source(self):
        walk_in_referral = Referral.objects.create(
            organization=self.org,
            name="Walk-In Partner",
            referral_fee=Decimal("10.00"),
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            service_type="vehicle_registration",
            source="walk_in",
            referral=walk_in_referral,
            processing_fee=Decimal("100.00"),
            transaction_date=date(2026, 6, 1),
            receipt_number=f"RCPT-INTAKE-PROFIT-1-{self.org.id}",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            service_type="vehicle_registration",
            source="google_search",
            processing_fee=Decimal("50.00"),
            transaction_date=date(2026, 6, 2),
            receipt_number=f"RCPT-INTAKE-PROFIT-2-{self.org.id}",
        )
        source_choices = [
            {"key": "walk_in", "label": "Walk-In"},
            {"key": "google_search", "label": "Google Search"},
        ]
        records = ServiceRecord.objects.filter(organization=self.org)
        cards, total = build_intake_source_profit_cards(records, source_choices)
        by_key = {card["key"]: card for card in cards}
        self.assertEqual(by_key["walk_in"]["net_profit"], Decimal("90.00"))
        self.assertEqual(by_key["google_search"]["net_profit"], Decimal("50.00"))
        self.assertEqual(total, Decimal("140.00"))

    def test_non_standard_source_rolls_into_google_search_card(self):
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            service_type="vehicle_registration",
            source="google_search",
            processing_fee=Decimal("60.00"),
            transaction_date=date(2026, 6, 3),
            receipt_number=f"RCPT-INTAKE-PROFIT-3-{self.org.id}",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            service_type="vehicle_registration",
            source="yelp_ads",
            processing_fee=Decimal("40.00"),
            transaction_date=date(2026, 6, 4),
            receipt_number=f"RCPT-INTAKE-PROFIT-4-{self.org.id}",
        )
        source_choices = [
            {"key": "google_search", "label": "Google Search"},
            {"key": "walk_in", "label": "Walk-In"},
        ]
        records = ServiceRecord.objects.filter(organization=self.org)
        cards, total = build_intake_source_profit_cards(records, source_choices)
        by_key = {card["key"]: card for card in cards}
        self.assertNotIn("_other", by_key)
        self.assertNotIn("yelp_ads", by_key)
        self.assertEqual(by_key["google_search"]["net_profit"], Decimal("100.00"))
        self.assertEqual(by_key["google_search"]["transaction_count"], 2)
        self.assertEqual(total, Decimal("100.00"))
