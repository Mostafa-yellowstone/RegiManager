"""Native quote portal and the insurance desk that replaced the EZLynx embed."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.insurance_dec_import import extract_coverages
from core.insurance_desk_models import (
    InsuranceClaim,
    InsuranceCommissionStatementLine,
    InsuranceCoverage,
    InsurancePolicyTransaction,
    InsuranceQuoteOption,
)
from core.insurance_quote_pipeline_models import InsuranceQuoteLead, InsuranceQuoteLeadDriver
from core.models import (
    Client,
    InsuranceCompany,
    InsurancePolicy,
    InsurancePolicyDocument,
    Organization,
    OrganizationMembership,
    Space,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class InsuranceDeskTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Desk Agency",
            city="Brooklyn",
            state="NY",
            portal_token="desk-portal-token",
            is_public_insurance_intake_enabled=True,
            has_insurance=True,
        )
        Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        self.owner = User.objects.create_user(username="desk-owner", password="password123")
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.customer = Client.objects.create(
            organization=self.org,
            first_name="Mina",
            last_name="Cole",
            phone_number="5551112222",
        )
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Progressive")
        today = timezone.localdate()
        self.policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.customer,
            insurance_company=self.company,
            policy_number="NY-100",
            named_insured="Mina Cole",
            premium=Decimal("1200.00"),
            commission_rate=Decimal("10.00"),
            broker_fee=Decimal("50.00"),
            start_date=today,
            end_date=today + timedelta(days=180),
            stage=InsurancePolicy.StageChoices.BOUND,
            status=InsurancePolicy.StatusChoices.ACTIVE,
            added_by=self.owner,
        )
        self.client.login(username="desk-owner", password="password123")
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()

    def test_ezlynx_fields_are_gone(self):
        self.assertFalse(hasattr(self.org, "insurance_ezlynx_quote_url"))
        self.assertFalse(hasattr(self.org, "insurance_intake_portal_mode"))

    def test_public_intake_creates_a_pipeline_lead(self):
        response = self.client.post(
            reverse("public-insurance-intake", args=[self.org.portal_token]),
            {
                "client_name": "Sam Public",
                "phone": "5559990000",
                "email": "sam@example.com",
                "insurance_type": "auto_personal",
                "coverage_type": "full",
                "requested_limits": "BI 25/50",
                "vehicle_year": "2020",
                "vehicle_make": "Honda",
                "vin": "1HGBH41JXMN109186",
                "driver_2_name": "Alex Public",
                "driver_2_dl": "D123",
                "has_prior": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        lead = InsuranceQuoteLead.objects.get(client_name="Sam Public")
        self.assertEqual(lead.organization, self.org)
        self.assertIn("BI 25/50", lead.notes)
        self.assertTrue(lead.has_prior)
        self.assertEqual(InsuranceQuoteLeadDriver.objects.filter(lead=lead).count(), 1)
        self.assertIsNotNone(lead.crm_policy_id)

    def test_public_intake_off_does_not_accept_a_lead(self):
        self.org.is_public_insurance_intake_enabled = False
        self.org.save(update_fields=["is_public_insurance_intake_enabled"])
        response = self.client.post(
            reverse("public-insurance-intake", args=[self.org.portal_token]),
            {"client_name": "Nope", "phone": "5550000000"},
        )
        self.assertContains(response, "turned off")
        self.assertFalse(InsuranceQuoteLead.objects.filter(client_name="Nope").exists())

    def test_coverages_transactions_id_card_and_statement(self):
        saved = self.client.post(
            reverse("insurance-policy-desk", args=[self.policy.id]),
            {
                "desk_action": "coverages",
                "coverage_bi_limit": "25/50",
                "coverage_comp_deductible": "500",
            },
        )
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(InsuranceCoverage.objects.get(policy=self.policy, code="bi").limit_text, "25/50")
        self.assertEqual(
            InsuranceCoverage.objects.get(policy=self.policy, code="comp").deductible,
            Decimal("500.00"),
        )
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.photo_inspection_status, InsurancePolicy.PhotoInspection.REQUIRED)

        card = self.client.post(
            reverse("insurance-policy-desk", args=[self.policy.id]),
            {"desk_action": "id_card"},
        )
        self.assertEqual(card.status_code, 302)
        self.assertTrue(
            InsurancePolicyDocument.objects.filter(
                policy=self.policy,
                document_type=InsurancePolicyDocument.DocumentType.ID_CARDS,
            ).exists()
        )

        cancelled = self.client.post(reverse("insurance-policy-cancel-nonpay", args=[self.policy.id]))
        self.assertEqual(cancelled.status_code, 302)
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.status, InsurancePolicy.StatusChoices.INACTIVE)
        self.assertGreater(self.policy.unearned_commission, 0)
        self.assertEqual(
            InsurancePolicyTransaction.objects.get(policy=self.policy).reason,
            InsurancePolicyTransaction.CancelReason.NON_PAY,
        )

        upload = SimpleUploadedFile("statement.csv", b"policy number,amount\nNY-100,90.00\nMISSING,10.00\n")
        imported = self.client.post(
            reverse("insurance-commission-import"),
            {"organization": self.org.id, "statement": upload},
        )
        self.assertEqual(imported.status_code, 302)
        self.policy.refresh_from_db()
        self.assertTrue(self.policy.commission_received)
        self.assertEqual(self.policy.commission_paid, Decimal("90.00"))
        self.assertEqual(
            InsuranceCommissionStatementLine.objects.get(policy_number="MISSING").status,
            InsuranceCommissionStatementLine.Status.UNMATCHED,
        )
        matched = InsuranceCommissionStatementLine.objects.get(policy=self.policy)
        self.assertEqual(matched.status, InsuranceCommissionStatementLine.Status.SHORT)

    def test_binding_a_carrier_quote_copies_it_onto_the_policy(self):
        lead = InsuranceQuoteLead.objects.create(
            organization=self.org,
            client_name="Nora Quote",
            phone="5551112222",
            insurance_type="auto_personal",
            stage=InsuranceQuoteLead.Stage.QUOTED,
        )
        option = InsuranceQuoteOption.objects.create(
            lead=lead,
            company=self.company,
            term_premium=Decimal("980.00"),
            bi_limit="50/100",
            comp_deductible=Decimal("250.00"),
            term_months=6,
        )
        response = self.client.post(reverse("insurance-quote-option-bind", args=[option.id]))
        self.assertEqual(response.status_code, 302)
        option.refresh_from_db()
        lead.refresh_from_db()
        policy = lead.crm_policy
        self.assertEqual(option.decision, InsuranceQuoteOption.Decision.ACCEPTED)
        self.assertEqual(lead.stage, InsuranceQuoteLead.Stage.WON)
        self.assertEqual(policy.premium, Decimal("980.00"))
        self.assertEqual(policy.stage, InsurancePolicy.StageChoices.BOUND)
        self.assertEqual(InsuranceCoverage.objects.get(policy=policy, code="bi").limit_text, "50/100")
        self.assertTrue(policy.documents.filter(title="Temporary insurance ID card").exists())
        self.assertIsNotNone(policy.compensation_disclosed_at)

    def test_dec_text_coverages(self):
        rows = extract_coverages(
            "Bodily Injury Liability $25,000/$50,000\nProperty Damage $10,000\nComprehensive deductible $500"
        )
        codes = {row.code: row for row in rows}
        self.assertEqual(codes["bi"].limit_text, "25,000/50,000")
        self.assertEqual(codes["pd"].limit_text, "10,000")
        self.assertEqual(codes["comp"].deductible, Decimal("500.00"))
        short = {row.code: row for row in extract_coverages("BI 25/50  PD 10,000")}
        self.assertEqual(short["bi"].limit_text, "25/50")
        self.assertEqual(short["pd"].limit_text, "10,000")

    def test_statement_pdf_review_flag_id_card_form_and_message(self):
        from io import BytesIO

        from pypdf import PdfReader
        from reportlab.pdfgen import canvas

        from core.insurance_dec_import import ParsedInsuranceDec, apply_parsed_dec_to_insurance_policy
        from core.insurance_desk import import_commission_csv, issue_standard_form
        from core.insurance_desk_pdf import temporary_id_card_pdf
        from core.insurance_desk_models import InsuranceIssuedForm
        from core.models import ClientChatMessage

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(72, 720, "Policy NY-100 commission $90.00")
        pdf.save()
        upload = SimpleUploadedFile("statement.pdf", buffer.getvalue(), content_type="application/pdf")
        statement = import_commission_csv(self.org, upload, self.owner, company=self.company)
        self.assertIsNotNone(statement)
        line = statement.lines.get(policy=self.policy)
        self.assertEqual(line.paid_amount, Decimal("90.00"))

        self.company.naic = "24260"
        self.company.save(update_fields=["naic"])
        card = temporary_id_card_pdf(self.policy)
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(card)).pages)
        self.assertIn("24260", text)
        self.assertIn("Temporary card", text)

        apply_parsed_dec_to_insurance_policy(self.policy, ParsedInsuranceDec())
        self.policy.refresh_from_db()
        self.assertTrue(self.policy.coverages_need_review)
        confirmed = self.client.post(
            reverse("insurance-policy-desk", args=[self.policy.id]),
            {"desk_action": "confirm_coverages"},
        )
        self.assertEqual(confirmed.status_code, 302)
        self.policy.refresh_from_db()
        self.assertFalse(self.policy.coverages_need_review)

        issued = issue_standard_form(
            self.policy,
            "liability_certificate",
            self.owner,
            {"holder_name": "City GC", "holder_address": "1 Main St"},
        )
        self.assertTrue(InsuranceIssuedForm.objects.filter(id=issued.id, file__isnull=False).exists())
        self.assertTrue(issued.file.name.endswith(".pdf"))
        self.assertTrue(self.policy.documents.filter(title__startswith="Certificate of Liability Insurance").exists())

        self.customer.email = "mina@example.com"
        self.customer.save(update_fields=["email"])
        sent = self.client.post(
            reverse("insurance-policy-desk", args=[self.policy.id]),
            {"desk_action": "message", "body": "Your ID card is ready."},
        )
        self.assertEqual(sent.status_code, 302)
        self.assertTrue(
            ClientChatMessage.objects.filter(client=self.customer, body="Your ID card is ready.").exists()
        )


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ClientDeskApiTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Wallet Desk",
            city="Queens",
            state="NY",
            portal_token="wallet-desk-token",
        )
        self.customer = Client.objects.create(
            organization=self.org,
            first_name="Ada",
            last_name="Lovelace",
            phone_number="(555) 123-4567",
            app_access_enabled=True,
        )
        self.customer.set_app_pin("1234")
        self.customer.save(update_fields=["app_pin_hash"])
        self.policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.customer,
            policy_number="APP-1",
            premium=Decimal("600.00"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 7, 1),
            stage=InsurancePolicy.StageChoices.BOUND,
            status=InsurancePolicy.StatusChoices.ACTIVE,
        )
        login = self.client.post(
            reverse("api-client-login"),
            {"portal_token": "wallet-desk-token", "phone": "5551234567", "pin": "1234"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")

    def test_client_can_open_a_claim_and_request_a_certificate(self):
        claim = self.client.post(
            reverse("api-client-policy-claim", args=[self.policy.id]),
            {"loss_date": "2026-10-01", "description": "Rear ended", "other_party": "Other driver"},
            format="json",
        )
        self.assertEqual(claim.status_code, 201)
        self.assertEqual(InsuranceClaim.objects.get(policy=self.policy).description, "Rear ended")
        certificate = self.client.post(
            reverse("api-client-policy-certificate", args=[self.policy.id]),
            {"holder_name": "City GC", "holder_address": "1 Main St"},
            format="json",
        )
        self.assertEqual(certificate.status_code, 201)
        detail = self.client.get(reverse("api-client-policy-detail", args=[self.policy.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["claims"][0]["status"], "reported")
