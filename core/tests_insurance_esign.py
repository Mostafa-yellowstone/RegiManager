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
        self.org = Organization.objects.create(
            name="Esign Org",
            city="NY",
            state="NY",
            insurance_intake_display_name="Xpress Insurance Solutions",
        )
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

    def test_public_signer_can_complete_with_drawn_signature(self):
        from PIL import Image, ImageDraw

        buf = BytesIO()
        image = Image.new("RGB", (240, 80), "white")
        draw = ImageDraw.Draw(image)
        draw.line((12, 40, 220, 44), fill="black", width=4)
        image.save(buf, format="PNG")
        import base64

        drawn = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        envelope = InsuranceESignEnvelope.objects.create(
            organization=self.org,
            title="Client app",
            original_file=SimpleUploadedFile("doc.pdf", _pdf_bytes(), content_type="application/pdf"),
            status=InsuranceESignEnvelope.Status.AWAITING,
            signer_name="Jose Palacios",
            signer_email="jose@example.com",
            fields_json=[{"id": "f1", "type": "signature", "page": 1, "x": 0.1, "y": 0.8, "w": 0.3, "h": 0.08}],
        )
        import json

        response = self.client.post(
            reverse("public-esign-sign", args=[envelope.signer_token]),
            data=json.dumps({
                "fields": [{
                    "id": "f1",
                    "type": "signature",
                    "page": 1,
                    "x": 0.1,
                    "y": 0.8,
                    "w": 0.3,
                    "h": 0.08,
                    "image": drawn,
                }],
                "signer_name": "Jose Palacios",
            }),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, InsuranceESignEnvelope.Status.SIGNED)
        self.assertTrue(envelope.signed_file)

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
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("Xpress Insurance Solutions", html)
        self.assertIn("RegiManager", html)
        self.assertIn("©", html)
        self.assertIn("Review and sign", html)
        self.assertIn("/sign/", html)
        self.assertNotIn("word-break:break-all", html)
        self.assertIn("/sign/", mail.outbox[0].body)
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, InsuranceESignEnvelope.Status.AWAITING)
        self.assertEqual(envelope.signer_email, "jose@example.com")

    def test_request_signature_still_sends_when_logo_bytes_are_invalid(self):
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
        from unittest.mock import patch

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            DEFAULT_FROM_EMAIL="RegiManager <test@example.com>",
        ), patch("core.insurance_esign_views.email_brand_for_org") as brand_fn:
            brand_fn.return_value = {
                "name": "Esign Org",
                "phone": "555-0100",
                "email": "agency@test.com",
                "copyright_line": "© 2026 Esign Org · RegiManager",
                "logo_bytes": b"not-an-image",
            }
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
        self.assertTrue(response.json()["ok"])
        self.assertEqual(len(mail.outbox), 1)

    def test_space_user_can_upload_and_download_signed_pdf(self):
        viewer = User.objects.create_user(username="esign_viewer", password="pass")
        membership = OrganizationMembership.objects.create(
            user=viewer,
            organization=self.org,
            role=OrganizationMembership.Role.AGENT,
            can_deal_with_insurance=False,
            can_view_spaces=True,
            is_active=True,
        )
        membership.accessible_spaces.add(self.space)
        envelope = InsuranceESignEnvelope.objects.create(
            organization=self.org,
            title="Signed app",
            original_file=SimpleUploadedFile("doc.pdf", _pdf_bytes(), content_type="application/pdf"),
            signed_file=SimpleUploadedFile("signed.pdf", _pdf_bytes("Signed copy"), content_type="application/pdf"),
            status=InsuranceESignEnvelope.Status.SIGNED,
            created_by=self.owner,
        )
        self.assertTrue(self.client.login(username="esign_viewer", password="pass"))
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()
        view = self.client.get(reverse("insurance-esign-editor", args=[envelope.id]))
        self.assertEqual(view.status_code, 200)
        self.assertContains(view, reverse("insurance-esign-signed", args=[envelope.id]))
        download = self.client.get(reverse("insurance-esign-signed", args=[envelope.id]) + "?download=1")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/pdf")
        upload = self.client.post(
            reverse("insurance-esign-upload"),
            {"file": SimpleUploadedFile("app.pdf", _pdf_bytes(), content_type="application/pdf"), "title": "Viewer upload"},
        )
        self.assertEqual(upload.status_code, 302)
        created = InsuranceESignEnvelope.objects.get(title="Viewer upload")
        self.assertEqual(created.created_by_id, viewer.id)
        self.assertIn(reverse("insurance-esign-editor", args=[created.id]), upload["Location"])

    def test_admin_can_delete_signed_envelope(self):
        self.owner.is_staff = True
        self.owner.is_superuser = True
        self.owner.save()
        envelope = InsuranceESignEnvelope.objects.create(
            organization=self.org,
            title="Signed app",
            original_file=SimpleUploadedFile("doc.pdf", _pdf_bytes(), content_type="application/pdf"),
            signed_file=SimpleUploadedFile("signed.pdf", _pdf_bytes("Signed copy"), content_type="application/pdf"),
            status=InsuranceESignEnvelope.Status.SIGNED,
            created_by=self.owner,
        )
        envelope_id = envelope.id
        self._login()
        response = self.client.post(
            reverse("admin:core_insuranceesignenvelope_delete", args=[envelope_id]),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(InsuranceESignEnvelope.objects.filter(id=envelope_id).exists())
