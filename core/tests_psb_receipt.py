"""Tests for NY PSB official-style service receipt PDF."""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from pypdf import PdfReader

from core.models import Client, Organization, OrganizationMembership, ServiceRecord, Vehicle
from core.psb_receipt_pdf import (
    OFFICIAL_FOOTER,
    _build_service_row_amounts,
    _dollars_to_words,
    format_receipt_number_display,
)

User = get_user_model()


class PsbReceiptPdfTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Xpress Plates",
            business_owner_name="John A. Smith",
            address_line="123 Main Street",
            city="Anytown",
            state="NY",
            phone_number="(518) 555-5123",
        )
        self.user = User.objects.create_user(username="receiptuser", password="password123")
        OrganizationMembership.objects.create(user=self.user, organization=self.org, role="owner")
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Doe",
            street_address="456 Oak Ave",
            city="Anytown",
            state="NY",
            zip_code="13064",
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="1HGBH41JXMN109186",
            vehicle_number="VEH-001",
        )
        self.http = TestClient()
        self.http.login(username="receiptuser", password="password123")

    def _pdf_text(self, record):
        response = self.http.get(reverse("service-receipt-pdf", args=[record.id]))
        self.assertEqual(response.status_code, 200)
        return "".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages)

    def test_numeric_receipt_number_display(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
        )
        self.assertEqual(format_receipt_number_display(record), "00001")
        pdf_text = self._pdf_text(record)
        self.assertIn("00001", pdf_text)
        self.assertNotIn("RCPT", pdf_text)

    def test_business_owner_and_sum_line(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            dmv_fee=Decimal("75.00"),
            processing_fee=Decimal("25.00"),
            service_fee=Decimal("100.00"),
        )
        pdf_text = self._pdf_text(record)
        self.assertIn("JOHN A. SMITH", pdf_text)
        self.assertIn("The sum of", pdf_text)
        self.assertIn("One Hundred", pdf_text)
        self.assertIn("Dollars", pdf_text)

    def test_official_layout_fields(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            dmv_fee=Decimal("75.00"),
            processing_fee=Decimal("25.00"),
            service_fee=Decimal("100.00"),
        )
        pdf_text = self._pdf_text(record)
        self.assertIn("Customer Name:", pdf_text)
        self.assertIn("Customer Address:", pdf_text)
        self.assertIn("Services Provided", pdf_text)
        self.assertIn("DMV Fee", pdf_text)
        self.assertIn("Fee for Service", pdf_text)
        self.assertIn("Obtaining Plates", pdf_text)
        self.assertIn("Received by:", pdf_text)
        self.assertIn(OFFICIAL_FOOTER.strip(), pdf_text)
        self.assertIn("PAYMENT HISTORY", pdf_text)

    def test_service_row_mapping(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="duplicate_title",
            dmv_fee=Decimal("20.00"),
            processing_fee=Decimal("15.00"),
        )
        amounts = _build_service_row_amounts(record)
        self.assertEqual(amounts["duplicate_title"]["dmv"], Decimal("20.00"))
        self.assertEqual(amounts["duplicate_title"]["fee"], Decimal("15.00"))

    def test_dollars_to_words(self):
        self.assertEqual(_dollars_to_words(Decimal("100.00")), "One Hundred")
        self.assertEqual(_dollars_to_words(Decimal("0")), "Zero")
