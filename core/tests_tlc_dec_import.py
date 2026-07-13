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
    parse_hereford_dec_text,
    parse_maya_assurance_dec_text,
    parse_tlc_dec_page,
)
from core.tlc_models import TLCPolicy, TLCPolicyDocument

User = get_user_model()

SAMPLE_ATIC_SINGLE_CAR_DEC = """
AMERICAN TRANSIT INSURANCE COMPANY (036)
DECLARATION AUTOMOBILE INSURANCE
Policy Number B513377
DATE OF ISSUE 02/26/2026
        (                        NAMED INSURED AND ADDRESS                               )                                                            (                PRODUCERS NAME AND ADDRESS                     )
TRAORE,YAYA
137 W 141ST 10
NEW YORK, NY 10030
GM BROKERAGE OF ROCKLAND, INC
2255 GRAND CONCOURSE, STORE # 9
BRONX, NY 10453
POLICY PERIOD 03/01/2026 12:01 AM - 03/01/2027 12:01 AM
GARAGE ADDRESS
CAR MODEL YEAR TRADE NAME IDENTIFICATION NUMBER CLASS TERR MEDALLION # PLATE #
TOYOTA 2013 TOYOTA 2T3RFREV8DW086061 BC 18 T685180C
DRIVER 1. YAYA TRAORE DRIVER 4.
PREMIUMS(ALL PREMIUMS SHOWN ARE FULL POLICY PREMIUMS)
EFFECTIVE DATE PR/SR AMENDED ANNUAL PREMIUM
03/01/2026 1.00 $4,960.99 $4,960.99
DOWN PAYMENT $1310.25 *MONTHLY PREMIUM THEREAFTER $433.25
"""


SAMPLE_MAYA_DEC = """
MAYA ASSURANCE COMPANY
24-29 JACKSON AVENUE, SUITE 200
LONG ISLAND CITY, NEW YORK
11101
POLICY NUMBER
BUSINESS AUTO DECLARATIONS
5-MA000499
ITEM ONE
NAMED INSURED & ADDRESS
SAEYDI, AYAD AMEN
861 KINSELLA ST 2
BRONX, NY 10462
FORM OF NAMED INSURED'S BUSINESS
 Corporation
 Partnership
X
 Individual
 Other
PRODUCER
MULTILINE INSURANCE BROKERAGE
800 YONKERS AVE, 800 YONKERS AVE
YONKERS, NY 10704
 New
X
 Renewal
 Amend
POLICY PERIOD:  FROM
09/26/2025   TO   09/26/2026
ESTIMATED TOTAL ANNUAL PREMIUM
$4,598.87
ITEM THREE - SCHEDULE OF AUTOS YOU OWN
1
2016, HONDA, CIVIC, 19XFC1F38GE204992
DRIVERS SCHEDULE
1
SAEYDI, AYAD AMEN
POLICY NUMBER
PAYMENT SCHEDULE
5-MA000499
BILL Sl NO.
BILL DUE DATE
PREMIUM
FEES
BILL AMOUNT
DEPOSIT
09/26/2025
$919.77
$30.00
$949.77
INSTALLMENT-1
10/26/2025
$408.84
$20.00
$428.84
INSTALLMENT-2
11/25/2025
$408.84
$20.00
$428.84
PLEASE PAY ON OR BEFORE THE DUE DATE. IF YOUR PAYMENT IS LATE, A CANCELLATION NOTICE WILL BE SENT AND
A $50 FEE WILL BE ASSESSED TO REINSTATE THE POLICY.
"""


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


SAMPLE_HIC_DEC = """
HEREFORD INSURANCE COMPANY
36 – 01 43RD AVENUE, 2nd FLOOR
LONG ISLAND CITY, NY 11101
COMMERCIAL AUTOMOBILE INSURANCE.
NAMED INSURED AND ADDRESS PRODUCERS NAME AND ADDRESS
PEDRO T TAVERASCABREJA
2409 CRESTON AVE #44
Bronx, New York 10468
PEARLAND BROKERAGE INC
36-01 43rd Avenue
Long Island City, New York 11101
POLICY PERIOD Effective03/24/2026 (12:01 AM) - Expires : 03/24/2027 (12:01 AM)
CASE MODEL YEAR MAKE IDENTIFICATION NUMBER CLASS TERR UNIT # PLATE #
1 2025 VOLKSWAGEN 1V2HR2CA8SC530919
DRIVER 1. PEDRO T TAVERASCABREJA DRIVER 2.
Amended Premium $4,610.00 Premium $4,610.00
Annual Premium $4,610.00
DOWN PAYMENT $1,150.06
PCA1386002-0POLICY NO.
Policy Number: PCA1386002-0
PAYMENT SCHEDULE
Deposit 03/24/2026 $1,150.06 $0.00 $0.00 $1,150.06
1 04/24/2026 $383.46 $0.00 $20.00 $403.46
2 05/24/2026 $383.31 $0.00 $20.00 $403.31
3 06/24/2026 $383.31 $0.00 $20.00 $403.31
Reinstatements for cancelled policies are subject to approval by the Company. If approved, a fee of $15 per day,
beginning on the effective cancellation date, until the payment date shall be charged.
"""


class TLCDecImportParserTests(TestCase):
    def test_parse_hereford_sample(self):
        parsed = parse_hereford_dec_text(SAMPLE_HIC_DEC)
        self.assertEqual(parsed.policy_number, "PCA1386002-0")
        self.assertEqual(parsed.carrier, "HEREFORD INSURANCE COMPANY")
        self.assertEqual(parsed.named_insured, "PEDRO T TAVERASCABREJA")
        self.assertIn("2409 CRESTON AVE #44", parsed.insured_address)
        self.assertIn("Bronx, New York 10468", parsed.insured_address)
        self.assertEqual(parsed.broker_name, "PEARLAND BROKERAGE INC")
        self.assertIn("Long Island City, New York 11101", parsed.broker_address)
        self.assertEqual(parsed.effective_date.isoformat(), "2026-03-24")
        self.assertEqual(parsed.expiration_date.isoformat(), "2027-03-24")
        self.assertEqual(parsed.annual_premium, Decimal("4610.00"))
        self.assertEqual(parsed.amended_total, Decimal("4610.00"))
        self.assertEqual(parsed.down_payment, Decimal("1150.06"))
        self.assertEqual(parsed.installment_fee, Decimal("20.00"))
        self.assertEqual(len(parsed.vehicles), 1)
        self.assertEqual(parsed.vehicles[0].vin, "1V2HR2CA8SC530919")
        self.assertEqual(len(parsed.drivers), 1)
        self.assertEqual(parsed.drivers[0].name, "Pedro T Taverascabreja")
        self.assertEqual(len(parsed.payments), 4)
        self.assertEqual(parsed.payments[0].label, "DEPOSIT")
        self.assertEqual(parsed.payments[0].amount, Decimal("1150.06"))
        self.assertEqual(parsed.payments[1].label, "BILL # 1")
        self.assertEqual(parsed.payments[1].amount, Decimal("403.46"))
        self.assertEqual(parsed.payments[1].fee, Decimal("20.00"))

    def test_parse_maya_assurance_sample(self):
        parsed = parse_maya_assurance_dec_text(SAMPLE_MAYA_DEC)
        self.assertEqual(parsed.policy_number, "5-MA000499")
        self.assertEqual(parsed.carrier, "MAYA ASSURANCE COMPANY")
        self.assertEqual(parsed.named_insured, "SAEYDI, AYAD AMEN")
        self.assertIn("861 KINSELLA ST 2", parsed.insured_address)
        self.assertEqual(parsed.broker_name, "MULTILINE INSURANCE BROKERAGE")
        self.assertIn("YONKERS, NY 10704", parsed.broker_address)
        self.assertEqual(parsed.form_of_business, "Individual")
        self.assertEqual(parsed.effective_date.isoformat(), "2025-09-26")
        self.assertEqual(parsed.annual_premium, Decimal("4598.87"))
        self.assertEqual(parsed.reinstatement_fee, Decimal("50.00"))
        self.assertEqual(parsed.installment_fee, Decimal("20.00"))
        self.assertEqual(len(parsed.vehicles), 1)
        self.assertEqual(parsed.vehicles[0].vin, "19XFC1F38GE204992")
        self.assertEqual(len(parsed.drivers), 1)
        self.assertEqual(len(parsed.payments), 3)
        self.assertEqual(parsed.payments[0].label, "DEPOSIT")
        self.assertEqual(parsed.payments[0].amount, Decimal("949.77"))
        self.assertEqual(parsed.payments[0].fee, Decimal("30.00"))
        self.assertEqual(parsed.payments[1].label, "BILL # 1")
        self.assertEqual(parsed.payments[1].amount, Decimal("428.84"))
        self.assertEqual(parsed.payments[1].fee, Decimal("20.00"))

    def test_parse_american_transit_single_car_sample(self):
        parsed = parse_american_transit_dec_text(SAMPLE_ATIC_SINGLE_CAR_DEC)
        self.assertEqual(parsed.policy_number, "B513377")
        self.assertEqual(parsed.named_insured, "TRAORE, YAYA")
        self.assertIn("137 W 141ST 10", parsed.insured_address)
        self.assertIn("NEW YORK, NY 10030", parsed.insured_address)
        self.assertNotIn("GM BROKERAGE", parsed.insured_address)
        self.assertEqual(parsed.broker_name, "GM BROKERAGE OF ROCKLAND, INC")
        self.assertIn("BRONX, NY 10453", parsed.broker_address)
        self.assertEqual(parsed.effective_date.isoformat(), "2026-03-01")
        self.assertEqual(parsed.amended_total, Decimal("4960.99"))
        self.assertEqual(parsed.down_payment, Decimal("1310.25"))
        self.assertEqual(parsed.monthly_installment, Decimal("433.25"))
        self.assertEqual(len(parsed.vehicles), 1)
        self.assertEqual(parsed.vehicles[0].vin, "2T3RFREV8DW086061")
        self.assertEqual(parsed.vehicles[0].plate, "T685180C")
        self.assertEqual(len(parsed.drivers), 1)
        self.assertEqual(parsed.drivers[0].name, "Yaya Traore")
        self.assertEqual(len(parsed.payments), 10)
        self.assertEqual(parsed.payments[0].label, "DEPOSIT")
        self.assertEqual(parsed.payments[-1].amount, Decimal("184.74"))

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

    def test_parse_real_hereford_pdf_when_available(self):
        pdf_path = Path(r"c:\Users\mcc\Downloads\PCA1386002_-_DEC.pdf")
        if not pdf_path.exists():
            self.skipTest("Hereford dec PDF not on disk")
        with pdf_path.open("rb") as handle:
            parsed = parse_tlc_dec_page(handle)
        self.assertEqual(parsed.policy_number, "PCA1386002-0")
        self.assertEqual(parsed.broker_name, "PEARLAND BROKERAGE INC")
        self.assertEqual(len(parsed.vehicles), 1)
        self.assertEqual(len(parsed.payments), 10)

    def test_parse_real_maya_pdf_when_available(self):
        pdf_path = Path(r"c:\Users\mcc\Downloads\DEC_COL_5-MA000499_20250924000001855.pdf")
        if not pdf_path.exists():
            self.skipTest("Maya dec PDF not on disk")
        with pdf_path.open("rb") as handle:
            parsed = parse_tlc_dec_page(handle)
        self.assertEqual(parsed.policy_number, "5-MA000499")
        self.assertEqual(parsed.broker_name, "MULTILINE INSURANCE BROKERAGE")
        self.assertEqual(len(parsed.vehicles), 1)
        self.assertEqual(len(parsed.payments), 10)

    def test_parse_real_single_car_pdf_when_available(self):
        pdf_path = Path(r"c:\Users\mcc\Downloads\yaya+dec+2026.pdf")
        if not pdf_path.exists():
            self.skipTest("Single-car dec PDF not on disk")
        with pdf_path.open("rb") as handle:
            parsed = parse_tlc_dec_page(handle)
        self.assertEqual(parsed.policy_number, "B513377")
        self.assertEqual(parsed.broker_name, "GM BROKERAGE OF ROCKLAND, INC")
        self.assertEqual(len(parsed.vehicles), 1)
        self.assertGreaterEqual(len(parsed.payments), 9)

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
