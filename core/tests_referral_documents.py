import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Organization, OrganizationMembership, Referral, ReferralDocument


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ReferralPartnerPageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.organization = Organization.objects.create(name="Partner Test PSB")
        self.manager = User.objects.create_user(username="partner-manager", password="password123")
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.manager,
            role=OrganizationMembership.Role.MANAGER,
            is_active=True,
        )
        self.referral = Referral.objects.create(
            organization=self.organization,
            name="Sample Partner",
            is_partner=True,
        )
        self.client.login(username="partner-manager", password="password123")

    def test_manager_can_change_referral_fee(self):
        list_response = self.client.get(reverse("all-referrals"))
        self.assertEqual(list_response.status_code, 200)

        response = self.client.post(
            reverse("referral-profile", args=[self.referral.id]),
            {"update_referral_fee": "1", "referral_fee": "25.50"},
        )

        self.assertRedirects(response, reverse("referral-profile", args=[self.referral.id]))
        self.referral.refresh_from_db()
        self.assertEqual(self.referral.referral_fee, Decimal("25.50"))

    def test_manager_can_upload_and_delete_partner_document(self):
        response = self.client.post(
            reverse("referral-profile", args=[self.referral.id]),
            {
                "upload_referral_document": "1",
                "document_title": "Partner Agreement",
                "document": SimpleUploadedFile(
                    "agreement.pdf",
                    b"%PDF-1.4 partner agreement",
                    content_type="application/pdf",
                ),
            },
        )

        self.assertRedirects(response, reverse("referral-profile", args=[self.referral.id]))
        document = ReferralDocument.objects.get(referral=self.referral)
        self.assertEqual(document.title, "Partner Agreement")
        self.assertEqual(document.uploaded_by, self.manager)

        response = self.client.post(reverse("delete-referral-document", args=[document.id]))
        self.assertRedirects(response, reverse("referral-profile", args=[self.referral.id]))
        self.assertFalse(ReferralDocument.objects.filter(id=document.id).exists())

    def test_partner_controls_render_above_record_tables(self):
        response = self.client.get(reverse("referral-profile", args=[self.referral.id]))

        content = response.content.decode()
        self.assertLess(content.index("Referral Fee"), content.index("Client Service Records"))
        self.assertLess(content.index("Partner Documents"), content.index("Transactions"))

