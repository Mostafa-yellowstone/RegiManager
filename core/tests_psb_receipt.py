"""Tests for classic PSB service receipt PDF helpers and layout."""

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from core.models import Client, Organization, OrganizationMembership, ServiceRecord, Vehicle
from core.psb_receipt_pdf import (
    OFFICIAL_FOOTER_LINES,
    dollars_to_words,
    format_receipt_number_display,
    receipt_date_time_labels,
)

User = get_user_model()


class ReceiptFixtureMixin:
    def setUp(self):
        self.org = Organization.objects.create(
            name="Xpress Plates",
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


class PsbReceiptPdfTests(ReceiptFixtureMixin, TestCase):
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

    def test_sum_line(self):
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
        self.assertIn("The sum of", pdf_text)
        self.assertIn("One Hundred", pdf_text)
        self.assertIn("Dollars", pdf_text)
        self.assertNotIn("BUSINESS OWNER", pdf_text)

    def test_classic_layout_fields(self):
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
        self.assertIn("XPRESS PLATES", pdf_text)
        self.assertIn("Client", pdf_text)
        self.assertIn("Client Address", pdf_text)
        self.assertIn("SERVICES PROVIDED", pdf_text)
        self.assertIn("DMV FEE", pdf_text)
        self.assertIn("VEHICLE REGISTRATION", pdf_text)
        self.assertIn("GRAND TOTAL", pdf_text)
        self.assertIn("PAYMENT HISTORY", pdf_text)
        self.assertIn(OFFICIAL_FOOTER_LINES[0], pdf_text)
        self.assertIn(OFFICIAL_FOOTER_LINES[1], pdf_text)

    def test_same_second_saves_get_unique_receipt_numbers(self):
        frozen = datetime(2026, 10, 21, 19, 30, tzinfo=dt_timezone.utc)
        with mock.patch("core.models.timezone.now", return_value=frozen):
            numbers = {
                ServiceRecord.objects.create(
                    organization=self.org, handled_by=self.user, service_type="vehicle_registration"
                ).receipt_number
                for _ in range(5)
            }
        self.assertEqual(len(numbers), 5)
        for number in numbers:
            self.assertTrue(number.startswith(f"RCPT-20261021193000-{self.org.id}-"))

    def test_dollars_to_words(self):
        self.assertEqual(dollars_to_words(Decimal("100.00")), "One Hundred")
        self.assertEqual(dollars_to_words(Decimal("0")), "Zero")


class ReceiptTimezoneTests(ReceiptFixtureMixin, TestCase):
    """Receipt date/time follow the zone where the transaction was made."""

    def _record_at(self, utc_moment, *, tz_name="", tx_date=None):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            receipt_number=f"TZ-{ServiceRecord.objects.count() + 1}",
        )
        ServiceRecord.objects.filter(pk=record.pk).update(
            created_at=utc_moment,
            created_timezone=tz_name,
            transaction_date=tx_date or utc_moment.astimezone(ZoneInfo("America/New_York")).date(),
        )
        record.refresh_from_db()
        return record

    def _set_printer_timezone(self, tz_name):
        session = self.http.session
        session["portal_timezone"] = tz_name
        session.save()

    def test_creation_captures_active_timezone(self):
        with timezone.override(ZoneInfo("Africa/Cairo")):
            cairo = ServiceRecord.objects.create(
                organization=self.org, handled_by=self.user, service_type="vehicle_registration",
                receipt_number="TZ-CAIRO",
            )
        with timezone.override(ZoneInfo("America/New_York")):
            yonkers = ServiceRecord.objects.create(
                organization=self.org, handled_by=self.user, service_type="vehicle_registration",
                receipt_number="TZ-YONKERS",
            )
        self.assertEqual(cairo.created_timezone, "Africa/Cairo")
        self.assertEqual(yonkers.created_timezone, "America/New_York")

    def test_yonkers_transaction_prints_new_york_time(self):
        record = self._record_at(datetime(2026, 1, 15, 19, 30, tzinfo=dt_timezone.utc), tz_name="America/New_York")
        self.assertEqual(receipt_date_time_labels(record), ("Jan 15, 2026", "02:30 PM EST"))
        self._set_printer_timezone("Africa/Cairo")
        text = self._pdf_text(record)
        self.assertIn("02:30 PM EST", text)
        self.assertIn("Jan 15, 2026", text)

    def test_egypt_transaction_prints_cairo_time(self):
        record = self._record_at(datetime(2026, 1, 15, 19, 30, tzinfo=dt_timezone.utc), tz_name="Africa/Cairo")
        self.assertEqual(receipt_date_time_labels(record), ("Jan 15, 2026", "09:30 PM EET"))
        self._set_printer_timezone("America/New_York")
        self.assertIn("09:30 PM EET", self._pdf_text(record))

    def test_egypt_after_midnight_uses_cairo_date(self):
        # 23:30 UTC is still Jan 15 in New York but already Jan 16 in Cairo.
        record = self._record_at(datetime(2026, 1, 15, 23, 30, tzinfo=dt_timezone.utc), tz_name="Africa/Cairo")
        self.assertEqual(receipt_date_time_labels(record), ("Jan 16, 2026", "01:30 AM EET"))

    def test_staff_picked_date_is_kept(self):
        record = self._record_at(
            datetime(2026, 1, 15, 23, 30, tzinfo=dt_timezone.utc),
            tz_name="Africa/Cairo",
            tx_date=date(2026, 1, 10),
        )
        self.assertEqual(receipt_date_time_labels(record), ("Jan 10, 2026", "01:30 AM EET"))

    def test_legacy_record_uses_printing_device_timezone(self):
        record = self._record_at(datetime(2026, 1, 15, 19, 30, tzinfo=dt_timezone.utc))
        self.assertEqual(record.created_timezone, "")
        self._set_printer_timezone("Africa/Cairo")
        self.assertIn("09:30 PM EET", self._pdf_text(record))
        self._set_printer_timezone("America/New_York")
        self.assertIn("02:30 PM EST", self._pdf_text(record))

    def test_summer_time_labels(self):
        moment = datetime(2026, 7, 1, 16, 0, tzinfo=dt_timezone.utc)
        ny = self._record_at(moment, tz_name="America/New_York")
        self.assertEqual(receipt_date_time_labels(ny)[1], "12:00 PM EDT")
        cairo = self._record_at(moment, tz_name="Africa/Cairo")
        expected = moment.astimezone(ZoneInfo("Africa/Cairo"))
        self.assertEqual(
            receipt_date_time_labels(cairo)[1],
            f"{expected.strftime('%I:%M %p')} {expected.strftime('%Z')}",
        )

    def test_invalid_stored_timezone_falls_back(self):
        record = self._record_at(datetime(2026, 1, 15, 19, 30, tzinfo=dt_timezone.utc), tz_name="../../etc/passwd")
        self._set_printer_timezone("America/New_York")
        self.assertIn("02:30 PM EST", self._pdf_text(record))
