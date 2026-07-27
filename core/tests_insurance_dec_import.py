"""Tests for Integon / NYAIP / Maya / Progressive insurance DEC text parsers."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.test import SimpleTestCase

from core.insurance_dec_import import (
    DecPageParseError,
    parse_integon_dec_text,
    parse_insurance_dec_page,
    parse_maya_dec_text,
    parse_nyaip_dec_text,
    parse_progressive_dec_text,
)


INTEGON_SAMPLE = """
INTEGON NATIONAL INSURANCE COMPANY
DECLARATION PAGE
Named Insured: JANE SAMPLE DOE
Insured Address: 123 Main Street, Brooklyn, NY 11201
Policy Number: INT-998877
Effective Date: 01/15/2026
Expiration Date: 07/15/2026
Total Premium: $1,250.00
Down Payment: $350.00
1 2019 HONDA 1HGBH41JXMN109186
DRIVER 1. JANE SAMPLE DOE
DEPOSIT 01/15/2026 $350.00
INSTALLMENT #1 02/15/2026 $150.00
INSTALLMENT #2 03/15/2026 $150.00
"""

NYAIP_SAMPLE = """
NEW YORK AUTOMOBILE INSURANCE PLAN
NYAIP DECLARATION
Name of Insured: JOHN EXAMPLE SMITH
Policy No: NYAIP-445566
Policy Period: 03/01/2026 to 09/01/2026
Annual Premium: $2,100.00
Deposit: $500.00
Vehicle #1: 2020 TOYOTA VIN: 2T1BURHE0JC123456
Driver: JOHN EXAMPLE SMITH
DEPOSIT 03/01/2026 $500.00
Bill # 1 04/01/2026 $320.00
Bill # 2 05/01/2026 $320.00
"""

AIP_21ST_CENTURY_SAMPLE = """
POLICY DECLARATIONS
Policy Number CAR 5007 97 71
Insurer: 21st Century Centennial Insurance Co
NY Automobile Insurance Plan
Standard Time From 06/17/26 To 06/17/27
Named Insured:
FATEH ZINDANI
11501 FARMERS BLVD
SAINT ALBANS, NY 11412-2713
DESCRIPTION OF YOUR COVERED AUTO(S):
AUTO TERR SYMBOL AGE YR MAKE-MODEL
1 55 35 32 7 20 TOYOTA SIENNA
SERIAL NUMBER CLASS
5TDYZ3DCXLS079628 1A 000
TOTAL FULL TERM PREMIUM $7,067.00
DRIVER NAME
1) FATEH ZINDANI
"""

MAYA_SAMPLE = """
MAYA ASSURANCE COMPANY
POLICY NUMBER
BUSINESS AUTO DECLARATIONS
5-MA000460
ITEM ONE
NAMED INSURED & ADDRESS
HAMED, AYOUB
179 SARATOGA AVE 62
YONKERS, NY 10705
POLICY PERIOD:  FROM
09/29/2025   TO   09/29/2026
ESTIMATED TOTAL ANNUAL PREMIUM †
$4,498.18
Minimum Earned Premium
$1,829.27
ITEM THREE - SCHEDULE OF AUTOS YOU OWN
2024, TOYOTA, HIGHLANDER, 5TDKDRBH0RS564584
DRIVERS SCHEDULE
1
HAMED, AYOUB
2
"""

PROGRESSIVE_SAMPLE = """
Progressive Direct Insurance Company
DECLARATIONS PAGE
Named Insured: EBONY N ANDERSON
Policy Number: 942857130
Effective Date: 05/01/2026
Expiration Date: 11/01/2026
Total Premium: $2,450.00
Down Payment: $612.50
Vehicle #1: 2021 HONDA VIN: 5J6RM4H75ML012345
Driver: EBONY N ANDERSON
DEPOSIT 05/01/2026 $612.50
INSTALLMENT #1 06/01/2026 $306.25
"""


class InsuranceDecParseTests(SimpleTestCase):
    def test_parse_integon_text(self):
        parsed = parse_integon_dec_text(INTEGON_SAMPLE)
        self.assertEqual(parsed.carrier_key, "integon")
        self.assertEqual(parsed.policy_number, "INT-998877")
        self.assertEqual(parsed.named_insured.upper(), "JANE SAMPLE DOE")
        self.assertEqual(parsed.effective_date, date(2026, 1, 15))
        self.assertEqual(parsed.expiration_date, date(2026, 7, 15))
        self.assertEqual(parsed.premium, Decimal("1250.00"))
        self.assertGreaterEqual(len(parsed.payments), 2)
        self.assertGreaterEqual(len(parsed.vehicles), 1)
        self.assertEqual(parsed.vehicles[0].vin, "1HGBH41JXMN109186")
        self.assertGreaterEqual(len(parsed.drivers), 1)
        self.assertIn("JANE", parsed.drivers[0].name.upper())

    def test_parse_nyaip_text(self):
        parsed = parse_nyaip_dec_text(NYAIP_SAMPLE)
        self.assertEqual(parsed.carrier_key, "nyaip")
        self.assertEqual(parsed.policy_number, "NYAIP-445566")
        self.assertEqual(parsed.effective_date, date(2026, 3, 1))
        self.assertEqual(parsed.expiration_date, date(2026, 9, 1))
        self.assertEqual(parsed.premium, Decimal("2100.00"))
        self.assertGreaterEqual(len(parsed.payments), 2)
        self.assertGreaterEqual(len(parsed.vehicles), 1)
        self.assertEqual(parsed.vehicles[0].vin, "2T1BURHE0JC123456")
        self.assertGreaterEqual(len(parsed.drivers), 1)

    def test_parse_21st_century_aip_layout(self):
        parsed = parse_nyaip_dec_text(AIP_21ST_CENTURY_SAMPLE)
        self.assertEqual(parsed.carrier_key, "nyaip")
        self.assertIn("CAR", parsed.policy_number.upper())
        self.assertIn("5007", parsed.policy_number)
        self.assertEqual(parsed.effective_date, date(2026, 6, 17))
        self.assertEqual(parsed.expiration_date, date(2027, 6, 17))
        self.assertEqual(parsed.premium, Decimal("7067.00"))
        self.assertGreaterEqual(len(parsed.vehicles), 1)
        self.assertEqual(parsed.vehicles[0].vin, "5TDYZ3DCXLS079628")
        self.assertEqual(parsed.vehicles[0].year, 2020)
        self.assertIn("TOYOTA", parsed.vehicles[0].make.upper())
        self.assertGreaterEqual(len(parsed.drivers), 1)
        self.assertIn("FATEH", parsed.drivers[0].name.upper())

    def test_parse_maya_text(self):
        parsed = parse_maya_dec_text(MAYA_SAMPLE)
        self.assertEqual(parsed.carrier_key, "maya")
        self.assertEqual(parsed.policy_number, "5-MA000460")
        self.assertEqual(parsed.effective_date, date(2025, 9, 29))
        self.assertEqual(parsed.expiration_date, date(2026, 9, 29))
        self.assertEqual(parsed.premium, Decimal("4498.18"))
        self.assertGreaterEqual(len(parsed.vehicles), 1)
        self.assertEqual(parsed.vehicles[0].vin, "5TDKDRBH0RS564584")
        self.assertEqual(parsed.vehicles[0].year, 2024)
        self.assertGreaterEqual(len(parsed.drivers), 1)
        self.assertIn("HAMED", parsed.drivers[0].name.upper())

    def test_parse_progressive_text(self):
        parsed = parse_progressive_dec_text(PROGRESSIVE_SAMPLE)
        self.assertEqual(parsed.carrier_key, "progressive")
        self.assertEqual(parsed.policy_number, "942857130")
        self.assertEqual(parsed.effective_date, date(2026, 5, 1))
        self.assertEqual(parsed.expiration_date, date(2026, 11, 1))
        self.assertEqual(parsed.premium, Decimal("2450.00"))
        self.assertGreaterEqual(len(parsed.vehicles), 1)
        self.assertEqual(parsed.vehicles[0].vin, "5J6RM4H75ML012345")

    def test_router_rejects_blank_pdf(self):
        from pypdf import PdfWriter

        buf = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(buf)
        buf.seek(0)
        with self.assertRaises(DecPageParseError):
            parse_insurance_dec_page(buf)

    def test_real_desktop_samples_when_present(self):
        fateh = Path(r"C:/Users/mcc/Desktop/Fateh+Zindani+-+Decleration+new.pdf")
        maya = Path(r"C:/Users/mcc/Desktop/HAMED,AYOUB+DEC_COL_5-MA000460_20250916000004436.pdf")
        if fateh.exists():
            with fateh.open("rb") as handle:
                parsed = parse_insurance_dec_page(handle)
            self.assertEqual(parsed.carrier_key, "nyaip")
            self.assertIn("5007", parsed.policy_number)
            self.assertEqual(parsed.effective_date, date(2026, 6, 17))
            self.assertGreaterEqual(len(parsed.vehicles), 1)
        if maya.exists():
            with maya.open("rb") as handle:
                parsed = parse_insurance_dec_page(handle)
            self.assertEqual(parsed.carrier_key, "maya")
            self.assertEqual(parsed.policy_number, "5-MA000460")
            self.assertGreaterEqual(len(parsed.vehicles), 1)
