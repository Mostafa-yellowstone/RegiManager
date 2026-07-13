"""Tests for TLC declaration page PDF import."""

from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Organization, OrganizationMembership, Space
from core.tlc_dec_import import (
    DecPageParseError,
    apply_parsed_dec_to_policy,
    parse_american_transit_dec_text,
    parse_tlc_dec_page,
)
from core.tlc_models import TLCPolicy, TLCPolicyDocument

User = get_user_model()

SAMPLE_ATIC_DEC = """
AMERICAN TRANSIT INSURANCE COMPANY (036)
DECLARATION AUTOMOBILE INSURANCE
Form Of Business Business Autoss
Policy Number TNC000474
Issue Date : 07/28/2025
POLICY PERIOD Effective 08/09/2025 (12:01 AM) - Expires : 08/09/2026 (12:01 AM)
NAMED INSURED AND ADDRESS PRODUCERS NAME AND ADDRESS
J E CAR SERVICE LLC
110 URBAN ST
MOUNT VERNON NY 10552
ASTORIA LIVERY BROKERAGE
INC.
41-01 BROADWAY
ASTORIA NY 11103
Annual Premium $17,524.14 Premium $17,524.14
DOWN PAYMENT
$800.00
$18,344.14
$3,604.83
**AMENDED TOTAL INCLUDES ORIGINAL POLICY PREMIUM
SCHEDULE # 2
Policy Number TNC000474 Insured J E CAR SERVICE LLC
1 2022 VOLKSWAGEN 1V2HR2CA1NC562342 94 No
2 2025 MAZDA JM3KJDHC6S1106078 94 No
Drivers Information :
MACEDO,MARCO AURELIO 08/09/2025 08/09/2026
ESTIMA,JOHN L 08/09/2025 08/09/2026
MENDONCA,PATRICK D 08/09/2025 08/09/2026
Issued to: J E CAR SERVICE LLC
Policy No: TNC000474 Effective :08/09/2025 - 08/09/2026
Broker: ASTORIA LIVERY BROKERAGE INC.
41-01 BROADWAY
ASTORIANY11103
DEPOSIT 08/09/2025 $3,604.83
Bill # 1 09/15/2025 $1,637.90
Bill # 2 10/15/2025 $1,637.90
Bill # 3 11/15/2025 $1,637.90
The monthly Payment plan provides for a $ 50.00 Reinstatement Fee for failure
to comply with this installment Payment Endorsement.
"""


class TLCDecImportParserTests(TestCase):
    def test_parse_american_transit_sample(self):
        parsed = parse_american_transit_dec_text(SAMPLE_ATIC_DEC)
        self.assertEqual(parsed.policy_number, "TNC000474")
        self.assertEqual(parsed.carrier, "AMERICAN TRANSIT INSURANCE COMPANY")
        self.assertEqual(parsed.named_insured, "J E CAR SERVICE LLC")
        self.assertIn("110 URBAN ST", parsed.insured_address)
        self.assertEqual(parsed.broker_name, "ASTORIA LIVERY BROKERAGE INC.")
        self.assertEqual(parsed.amended_total, Decimal("18344.14"))
        self.assertEqual(parsed.deposit_amount, Decimal("3604.83"))
        self.assertEqual(parsed.reinstatement_fee, Decimal("50.00"))
        self.assertEqual(len(parsed.vehicles), 2)
        self.assertEqual(parsed.vehicles[0].vin, "1V2HR2CA1NC562342")
        self.assertEqual(len(parsed.drivers), 3)
        self.assertEqual(len(parsed.payments), 4)
        self.assertEqual(parsed.payments[0].label, "DEPOSIT")

    def test_apply_dec_sets_default_installment_fee_on_bills(self):
        from core.models import Organization, Space
        from core.tlc_models import TLCPolicy

        org = Organization.objects.create(name="Fee Org", city="NY", state="NY")
        space = Space.objects.create(organization=org, key="tlc", label="TLC")
        policy = TLCPolicy.objects.create(
            organization=org,
            space=space,
            policy_number="TNC-FEE",
        )
        parsed = parse_american_transit_dec_text(SAMPLE_ATIC_DEC)
        apply_parsed_dec_to_policy(policy, parsed)
        breakdown = policy.premium_breakdown
        self.assertEqual(breakdown.installment_fee, Decimal("5.00"))
        deposit = policy.installments.get(notes="DEPOSIT")
        bill = policy.installments.get(notes="BILL # 1")
        self.assertEqual(deposit.installment_fee, Decimal("0.00"))
        self.assertEqual(bill.installment_fee, Decimal("5.00"))
        self.assertEqual(bill.amount, Decimal("1632.90"))
        self.assertEqual(bill.balance, Decimal("1637.90"))

    def test_parse_real_pdf_when_available(self):
        pdf_path = Path(r"c:\Users\mcc\Downloads\NEW+DECPAGE1753732091.pdf")
        if not pdf_path.exists():
            self.skipTest("Sample dec PDF not on disk")
        with pdf_path.open("rb") as handle:
            parsed = parse_tlc_dec_page(handle)
        self.assertEqual(parsed.policy_number, "TNC000474")
        self.assertGreaterEqual(len(parsed.vehicles), 2)
        self.assertGreaterEqual(len(parsed.payments), 9)


class TLCDecImportViewTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="TLC Import PSB", city="Queens", state="NY")
        self.owner = User.objects.create_user(username="tlcimport", password="pass12345")
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
        self.client.login(username="tlcimport", password="pass12345")
        session = self.client.session
        session["active_organization_id"] = self.org.id
        session.save()

    def test_import_dec_page_creates_policy(self):
        pdf_path = Path(r"c:\Users\mcc\Downloads\NEW+DECPAGE1753732091.pdf")
        if not pdf_path.exists():
            self.skipTest("Sample dec PDF not on disk")
        upload = SimpleUploadedFile(
            "dec.pdf",
            pdf_path.read_bytes(),
            content_type="application/pdf",
        )
        response = self.client.post(reverse("import-tlc-dec-page", args=[self.space.id]), {"dec_page": upload})
        self.assertEqual(response.status_code, 302)
        policy = TLCPolicy.objects.get(policy_number="TNC000474")
        self.assertEqual(policy.named_insured, "J E CAR SERVICE LLC")
        self.assertGreaterEqual(policy.policy_vehicles.count(), 2)
        self.assertGreaterEqual(policy.policy_drivers.count(), 3)
        self.assertGreaterEqual(policy.installments.count(), 9)
        self.assertTrue(
            TLCPolicyDocument.objects.filter(
                policy=policy, document_type=TLCPolicyDocument.DocumentType.DECLARATION_PAGE
            ).exists()
        )

    def test_apply_parsed_dec_to_existing_policy(self):
        policy = TLCPolicy.objects.create(
            organization=self.org,
            space=self.space,
            policy_number="TNC000474",
            added_by=self.owner,
        )
        parsed = parse_american_transit_dec_text(SAMPLE_ATIC_DEC)
        apply_parsed_dec_to_policy(policy, parsed, user=self.owner)
        policy.refresh_from_db()
        self.assertEqual(policy.broker_name, "ASTORIA LIVERY BROKERAGE INC.")
        self.assertEqual(policy.premium_breakdown.total_written_premium, Decimal("18344.14"))

    def test_unsupported_pdf_raises(self):
        upload = SimpleUploadedFile("bad.pdf", b"not a real dec page", content_type="application/pdf")
        with self.assertRaises(DecPageParseError):
            parse_tlc_dec_page(BytesIO(upload.read()))
