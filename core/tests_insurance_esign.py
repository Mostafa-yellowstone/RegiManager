"""Tests for Insurance Space Acrobat-style e-signature."""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from core.insurance_esign_models import InsuranceESignEnvelope
from core.models import Organization, OrganizationMembership, Space

User = get_user_model()


def _pdf_bytes(text="Sample application"):
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    pdf.setFont("Helvetica", 14)
    pdf.drawString(72, 720, text)
    pdf.save()
    return buf.getvalue()


class InsuranceESignTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Esign Org", city="NY", state="NY")
        self.space = Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        self.owner = User.objects.create_user(username="esign_owner", password="pass")
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            can_deal_with_insurance=True,
            is_active=True,
        )

    def _login(self):
        self.assertTrue(self.client.login(username="esign_owner", password="pass"))
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()

    def test_upload_opens_editor(self):
        self._login()
        upload = SimpleUploadedFile("app.pdf", _pdf_bytes(), content_type="application/pdf")
        response = self.client.post(reverse("insurance-esign-upload"), {"file": upload, "title": "Auto app"})
        self.assertEqual(response.status_code, 302)
        envelope = InsuranceESignEnvelope.objects.get(organization=self.org)
        self.assertEqual(envelope.title, "Auto app")
        self.assertIn(reverse("insurance-esign-editor", args=[envelope.id]), response["Location"])

    def test_apply_stamps_signature_and_certificate(self):
        self._login()
        envelope = InsuranceESignEnvelope.objects.create(
            organization=self.org,
            title="Disclosure",
            original_file=SimpleUploadedFile("doc.pdf", _pdf_bytes(), content_type="application/pdf"),
            created_by=self.owner,
        )
        tiny_png = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        import json
        response = self.client.post(
            reverse("insurance-esign-apply", args=[envelope.id]),
            data=json.dumps({
                "fields": [{
                    "id": "f1",
                    "type": "signature",
                    "page": 1,
                    "x": 0.1,
                    "y": 0.8,
                    "w": 0.3,
                    "h": 0.08,
                    "image": tiny_png,
                    "text": "Owner Name",
                }],
                "signer_name": "Owner Name",
                "signer_email": "owner@example.com",
            }),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, InsuranceESignEnvelope.Status.SIGNED)
        self.assertTrue(envelope.signed_file)
        signed = envelope.signed_file.read()
        self.assertTrue(signed.startswith(b"%PDF"))
        from pypdf import PdfReader
        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(signed)).pages)
        self.assertIn("Certificate of completion", text)
        self.assertIn("Owner Name", text)

    def test_public_link_opens_for_awaiting_envelope(self):
        envelope = InsuranceESignEnvelope.objects.create(
            organization=self.org,
            title="Client app",
            original_file=SimpleUploadedFile("doc.pdf", _pdf_bytes(), content_type="application/pdf"),
            status=InsuranceESignEnvelope.Status.AWAITING,
            signer_name="Jose Palacios",
            fields_json=[{"id": "f1", "type": "signature", "page": 1, "x": 0.1, "y": 0.8, "w": 0.3, "h": 0.08}],
        )
        response = self.client.get(reverse("public-esign-sign", args=[envelope.signer_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Finish")
        file_response = self.client.get(reverse("public-esign-file", args=[envelope.signer_token]))
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response["Content-Type"], "application/pdf")

    def test_request_signature_emails_the_signer(self):
        self._login()
        envelope = InsuranceESignEnvelope.objects.create(
            organization=self.org,
            title="Auto application",
            original_file=SimpleUploadedFile("doc.pdf", _pdf_bytes(), content_type="application/pdf"),
            created_by=self.owner,
        )
        import json
        from django.core import mail
        from django.test import override_settings

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            DEFAULT_FROM_EMAIL="RegiManager <test@example.com>",
        ):
            response = self.client.post(
                reverse("insurance-esign-request", args=[envelope.id]),
                data=json.dumps({
                    "fields": [{"id": "f1", "type": "signature", "page": 1, "x": 0.1, "y": 0.8, "w": 0.3, "h": 0.08}],
                    "signer_name": "Jose Palacios",
                    "signer_email": "jose@example.com",
                }),
                content_type="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["emailed"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jose@example.com"])
        self.assertIn("Auto application", mail.outbox[0].subject)
        self.assertIn("/sign/", mail.outbox[0].body)
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, InsuranceESignEnvelope.Status.AWAITING)
        self.assertEqual(envelope.signer_email, "jose@example.com")
