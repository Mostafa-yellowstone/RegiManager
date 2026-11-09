"""Tests for the Insurance Space payment general ledger PDF."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Client,
    DailyPaymentTransaction,
    InsuranceCompany,
    Organization,
    OrganizationMembership,
    Space,
)

User = get_user_model()


class InsuranceLedgerPdfTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Xpress PSB",
            insurance_intake_display_name="Xpress Insurance Solutions Inc.",
            address_line="123 Agency Ave",
            city="Brooklyn",
            state="NY",
            phone_number="7185550100",
            email="agency@example.com",
            psbc_license="PSB-8899",
            business_owner_name="Owner Name",
        )
        Space.objects.create(
            organization=self.org,
            key="insurance",
            label="Insurance",
            business_address="123 Agency Ave, Brooklyn, NY",
            business_phone="7185550100",
            business_email="agency@example.com",
        )
        self.owner = User.objects.create_user(username="gl_owner", password="pass")
        OrganizationMembership.objects.create(
            can_use_insurance=True,
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            can_deal_with_insurance=True,
            can_view_banking=True,
            is_active=True,
        )
        self.company = InsuranceCompany.objects.create(
            organization=self.org,
            name="Progressive",
            license_number="PC-100",
        )
        self.insured = Client.objects.create(
            organization=self.org,
            first_name="Jose",
            last_name="Palacios",
        )
        self.payment = DailyPaymentTransaction.objects.create(
            organization=self.org,
            client=self.insured,
            insurance_company=self.company,
            transaction_date=date(2026, 8, 1),
            amount=Decimal("180.00"),
            payment_type=DailyPaymentTransaction.PaymentType.NEW_BUSINESS,
            payment_method=DailyPaymentTransaction.PaymentMethod.CASH,
            recorded_by=self.owner,
            notes="Down payment",
            is_cleared=True,
            cleared_date=date(2026, 8, 2),
        )

    def test_ledger_pdf_contains_branding_and_receipt(self):
        self.assertTrue(self.client.login(username="gl_owner", password="pass"))
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()

        response = self.client.get(
            reverse("export-insurance-ledger-pdf"),
            {"start_date": "2026-08-01", "end_date": "2026-08-31"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        body = response.content
        self.assertTrue(body.startswith(b"%PDF"))
        from pypdf import PdfReader
        from io import BytesIO

        reader = PdfReader(BytesIO(body))
        page = reader.pages[0]
        self.assertEqual(page.rotation or 0, 0)
        self.assertGreater(float(page.mediabox.height), float(page.mediabox.width))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        self.assertIn("GENERAL LEDGER", text)
        self.assertIn("Xpress Insurance Solutions Inc.", text)
        self.assertIn("Jose Palacios", text)
        self.assertIn("Progressive", text)
        self.assertIn("PMT-", text)
        self.assertNotIn("License PSB-8899", text)
        self.assertNotIn("Principal Owner Name", text)
        self.assertNotIn("PSB-8899", text)

    def _login(self):
        self.assertTrue(self.client.login(username="gl_owner", password="pass"))
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()

    def _assert_pdf(self, url_name, params=None, args=None, must_contain=()):
        self._login()
        response = self.client.get(reverse(url_name, args=args or []), params or {})
        self.assertEqual(response.status_code, 200, url_name)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        from io import BytesIO
        from pypdf import PdfReader

        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(response.content)).pages)
        for snippet in must_contain:
            self.assertIn(snippet, text)
        return text

    def test_reporting_center_pdfs(self):
        remittance = self._assert_pdf(
            "export-insurance-remittance-pdf",
            {"start_date": "2026-08-01", "end_date": "2026-08-31"},
            must_contain=("Carrier remittance", "Progressive", "Jose Palacios"),
        )
        self.assertNotIn("License PSB-8899", remittance)
        self.assertNotIn("Principal Owner Name", remittance)
        self._assert_pdf(
            "export-insurance-payment-receipt-pdf",
            args=[self.payment.id],
            must_contain=("PAYMENT RECEIPT", "Jose Palacios", "PMT-"),
        )
        self._assert_pdf(
            "export-insurance-cashout-pdf",
            {"date": "2026-08-01"},
            must_contain=("Daily cash-out", "Jose Palacios"),
        )
        self._assert_pdf("export-insurance-book-pdf", must_contain=("Book of business",))
        self._assert_pdf("export-insurance-aging-pdf", must_contain=("Installment aging",))
        self._assert_pdf("export-insurance-agent-production-pdf", must_contain=("Producer production",))
        self._assert_pdf("export-insurance-unearned-pdf", must_contain=("Unearned commission",))
        self._assert_pdf("export-insurance-quote-conversion-pdf", must_contain=("Quote pipeline conversion",))
        self._assert_pdf("export-insurance-compliance-pdf", must_contain=("License", "Progressive"))
        self._assert_pdf("export-insurance-targets-pdf", {"month": "2026-08"}, must_contain=("Targets vs actual",))
        self._assert_pdf("export-insurance-commission-register-pdf", must_contain=("Commission production",))

    def _bind(self, number, company, bound, premium):
        from core.models import InsurancePolicy

        return InsurancePolicy.objects.create(
            organization=self.org, client=self.insured, insurance_company=company, policy_number=number,
            premium=Decimal(premium), commission_rate=Decimal("10"), broker_fee=Decimal("50"),
            stage="bound", status="active", bound_date=bound, start_date=bound, end_date=date(2027, 2, 1),
            added_by=self.owner,
        )

    def test_company_report_for_one_company_and_period(self):
        geico = InsuranceCompany.objects.create(organization=self.org, name="Geico")
        self._bind("PRG-IN", self.company, date(2026, 8, 10), "1000")
        self._bind("PRG-OUT", self.company, date(2026, 6, 10), "700")
        self._bind("GEI-IN", geico, date(2026, 8, 12), "500")
        text = self._assert_pdf(
            "export-insurance-company-report-pdf",
            {"start_date": "2026-08-01", "end_date": "2026-08-31", "company": self.company.id},
            must_contain=("Company report", "Progressive", "PRG-IN", "$1,000.00", "$100.00", "$50.00"),
        )
        self.assertNotIn("PRG-OUT", text)
        self.assertNotIn("GEI-IN", text)

    def test_company_report_all_companies_has_a_section_each(self):
        geico = InsuranceCompany.objects.create(organization=self.org, name="Geico")
        self._bind("PRG-IN", self.company, date(2026, 8, 10), "1000")
        self._bind("GEI-IN", geico, date(2026, 8, 12), "500")
        self._assert_pdf(
            "export-insurance-company-report-pdf",
            {"start_date": "2026-08-01", "end_date": "2026-08-31"},
            must_contain=("All companies", "Companies at a glance", "Geico", "Progressive", "PRG-IN", "GEI-IN", "$1,500.00"),
        )

    def test_company_report_view_opens_inline_and_download_saves(self):
        self._login()
        url = reverse("export-insurance-company-report-pdf")
        params = {"start_date": "2026-08-01", "end_date": "2026-08-31", "company": self.company.id}
        view = self.client.get(url, params)
        self.assertTrue(view["Content-Disposition"].startswith("inline;"))
        download = self.client.get(url, {**params, "download": "1"})
        self.assertEqual(
            download["Content-Disposition"],
            'attachment; filename="company-report-progressive-2026-08-01-2026-08-31.pdf"',
        )

    def test_company_report_rejects_another_offices_company(self):
        other = Organization.objects.create(name="Other PSB")
        foreign = InsuranceCompany.objects.create(organization=other, name="Foreign Mutual")
        self._login()
        resp = self.client.get(reverse("export-insurance-company-report-pdf"), {"company": foreign.id})
        self.assertEqual(resp.status_code, 404)

    def test_reports_page_has_view_and_download_buttons(self):
        self._login()
        resp = self.client.get(reverse("insurance-reports"))
        self.assertContains(resp, reverse("export-insurance-company-report-pdf"))
        self.assertContains(resp, 'name="download" value="1"')
