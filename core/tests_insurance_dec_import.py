"""Tests for Integon / NYAIP insurance DEC text parsers."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from django.test import SimpleTestCase

from core.insurance_dec_import import (
    DecPageParseError,
    parse_integon_dec_text,
    parse_insurance_dec_page,
    parse_nyaip_dec_text,
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

    def test_router_rejects_unknown_carrier(self):
        from pypdf import PdfWriter

        buf = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(buf)
        buf.seek(0)
        with self.assertRaises(DecPageParseError):
            parse_insurance_dec_page(buf)
