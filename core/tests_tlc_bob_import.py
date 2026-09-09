"""Tests for TLC book-of-business Excel import."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from core.models import Organization, OrganizationMembership, Space
from core.tlc_bob_import import BobSheetParseError, import_bob_rows_to_tlc, parse_bob_workbook
from core.tlc_models import TLCPolicy

User = get_user_model()


def _build_bob_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Detail"
    headers = [
        "Account Name",
        "Policy Type",
        "Line Of Business",
        "Master Company",
        "Policy Number ",
        "Term",
        "Effective Date",
        "Annualized Premium",
    ]
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TLCBobImportParserTests(TestCase):
    def test_parse_and_import_creates_pending_shells(self):
        data = _build_bob_xlsx(
            [
                [
                    "ALPHA CAB LLC",
                    "Business Auto",
                    "Commercial Auto",
                    "American Transit",
                    "TNC999001",
                    "12 Months",
                    date(2026, 1, 15),
                    12500.5,
                ],
                [
                    "BETA RIDES INC",
                    "Business Auto",
                    "Commercial Auto",
                    "Hereford",
                    "PCA999002",
                    "12 Months",
                    "02/01/2026",
                    "9800",
                ],
            ]
        )
        rows = parse_bob_workbook(BytesIO(data))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["policy_number"], "TNC999001")
        self.assertEqual(rows[0]["premium"], Decimal("12500.50"))

        org = Organization.objects.create(name="BOB Org", city="NYC", state="NY")
        space = Space.objects.create(organization=org, key="tlc", label="TLC")
        user = User.objects.create_user(username="bobowner", password="pass12345")
        result = import_bob_rows_to_tlc(
            organization=org, space=space, rows=rows, user=user
        )
        self.assertEqual(result.created, 2)
        self.assertEqual(result.skipped_duplicates, 0)
        policy = TLCPolicy.objects.get(policy_number="TNC999001")
        self.assertEqual(policy.status, TLCPolicy.Status.PENDING)
        self.assertEqual(policy.named_insured, "ALPHA CAB LLC")
        self.assertEqual(policy.carrier, "American Transit")
        self.assertEqual(policy.effective_date, date(2026, 1, 15))
        self.assertEqual(policy.expiration_date, date(2027, 1, 15))
        self.assertEqual(policy.premium_breakdown.total_written_premium, Decimal("12500.50"))
        self.assertEqual(policy.policy_vehicles.count(), 0)
        self.assertIn("BOB", policy.notes)

        again = import_bob_rows_to_tlc(
            organization=org, space=space, rows=rows, user=user
        )
        self.assertEqual(again.created, 0)
        self.assertEqual(again.skipped_duplicates, 2)

    def test_missing_columns_raises(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["Foo", "Bar"])
        ws.append(["a", "b"])
        buf = BytesIO()
        wb.save(buf)
        with self.assertRaises(BobSheetParseError):
            parse_bob_workbook(BytesIO(buf.getvalue()))


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class TLCBobImportViewTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="BOB View Org", city="Queens", state="NY")
        self.owner = User.objects.create_user(username="bobview", password="pass12345")
        self.membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
            can_view_spaces=True,
            can_deal_with_tlc=True,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="tlc",
            label="TLC",
            description="TLC profitability",
        )
        self.membership.accessible_spaces.add(self.space)
        self.client.login(username="bobview", password="pass12345")
        session = self.client.session
        session["active_organization_id"] = self.org.id
        session.save()

    def test_import_bob_sheet_creates_policies(self):
        data = _build_bob_xlsx(
            [
                [
                    "SHELL FLEET LLC",
                    "Business Auto",
                    "Commercial Auto",
                    "Maya Assurance",
                    "MA-BOB-100",
                    "12 Months",
                    date(2026, 3, 1),
                    4500,
                ]
            ]
        )
        upload = SimpleUploadedFile(
            "bob.xlsx",
            data,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(
            reverse("import-tlc-bob-sheet", args=[self.space.id]),
            {"bob_sheet": upload},
        )
        self.assertIn(response.status_code, (302, 303))
        policy = TLCPolicy.objects.get(policy_number="MA-BOB-100")
        self.assertEqual(policy.named_insured, "SHELL FLEET LLC")
        self.assertEqual(policy.status, TLCPolicy.Status.PENDING)
        self.assertEqual(policy.premium_breakdown.total_written_premium, Decimal("4500.00"))
