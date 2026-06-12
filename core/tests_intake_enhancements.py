"""Tests for intake portal dealer linking, notes, and vehicle options."""

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestClient, TestCase
from django.urls import reverse

from core.models import Client, ClientIntake, ClientNote, Organization, OrganizationMembership, Referral, Vehicle


class IntakePortalEnhancementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="intakeowner", password="password123")
        self.org = Organization.objects.create(
            name="Intake Org",
            city="NYC",
            portal_token="intake-enhance-token",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
        )
        self.dealer = Referral.objects.create(
            organization=self.org,
            name="Metro Auto Group",
            category="dealer",
            phone_no="7185550100",
            email="sales@metroauto.test",
            address="123 Dealer Row, NYC",
        )
        self.http = TestClient()

    def _base_post(self, **extra):
        data = {
            "first_name": "Jane",
            "last_name": "Driver",
            "gender": "female",
            "phone_number": "7185559999",
            "vin": "1HGBH41JXMN109186",
            "source": "walk_in",
            "services": ["registration_title"],
            "vehicle_type": "motorcycle",
            "body_type": "motorcycle",
            "fuel_type": "gas",
        }
        data.update(extra)
        return data

    def test_intake_form_lists_full_body_and_vehicle_types(self):
        response = self.http.get(reverse("public-intake-direct", args=[self.org.portal_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Motorcycle")
        self.assertContains(response, "Flat bed truck")
        self.assertContains(response, "Dealer / Referral")
        self.assertNotContains(response, 'value="referral"')

    def test_dealer_source_requires_partner_selection(self):
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(source="dealer"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dealer / referral partner")

    def test_existing_dealer_selection_saved_on_intake(self):
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(source="dealer", referral_select=str(self.dealer.id)),
        )
        self.assertEqual(response.status_code, 302)
        intake = ClientIntake.objects.get(organization=self.org, first_name="Jane")
        self.assertEqual(intake.selected_referral_id, self.dealer.id)
        self.assertEqual(intake.body_type, "motorcycle")
        self.assertEqual(intake.vehicle_type, "motorcycle")

    def test_new_dealer_fields_saved_on_intake(self):
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(
                source="dealer",
                referral_select="new",
                partner_name="Fresh Motors LLC",
                partner_phone="9175551212",
                partner_email="info@freshmotors.test",
                partner_address="500 Main St, Brooklyn NY",
            ),
        )
        self.assertEqual(response.status_code, 302)
        intake = ClientIntake.objects.get(organization=self.org, first_name="Jane")
        self.assertIsNone(intake.selected_referral_id)
        self.assertEqual(intake.partner_name, "Fresh Motors LLC")
        self.assertEqual(intake.partner_phone, "9175551212")

    def test_intake_note_saved(self):
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(intake_note="Please call before 5 PM."),
        )
        self.assertEqual(response.status_code, 302)
        intake = ClientIntake.objects.get(organization=self.org, first_name="Jane")
        self.assertEqual(intake.intake_note, "Please call before 5 PM.")

    def test_approve_links_existing_dealer_and_creates_note(self):
        intake = ClientIntake.objects.create(
            organization=self.org,
            first_name="Note",
            last_name="Client",
            gender="female",
            phone_number="7185550001",
            vin="VININTAKE00000001",
            source="dealer",
            selected_referral=self.dealer,
            body_type="suv",
            vehicle_type="passenger",
            intake_note="Needs temp plates.",
        )
        self.http.login(username="intakeowner", password="password123")
        response = self.http.get(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 302)
        client = Client.objects.get(organization=self.org, first_name="Note")
        self.assertEqual(client.referral_id, self.dealer.id)
        self.assertEqual(client.source, "dealer")
        note = ClientNote.objects.filter(client=client).first()
        self.assertIsNotNone(note)
        self.assertIn("Needs temp plates.", note.content)
        vehicle = Vehicle.objects.get(vin=intake.vin)
        self.assertEqual(vehicle.body_type, "suv")

    def test_approve_creates_new_dealer_referral_profile(self):
        intake = ClientIntake.objects.create(
            organization=self.org,
            first_name="New",
            last_name="DealerClient",
            gender="male",
            phone_number="7185550002",
            vin="VININTAKE00000002",
            source="dealer",
            partner_name="Fresh Motors LLC",
            partner_phone="9175551212",
            partner_email="info@freshmotors.test",
            partner_address="500 Main St",
            intake_note="",
        )
        self.http.login(username="intakeowner", password="password123")
        response = self.http.get(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 302)
        client = Client.objects.get(organization=self.org, first_name="New")
        self.assertIsNotNone(client.referral_id)
        self.assertEqual(client.referral.name, "Fresh Motors LLC")
        self.assertEqual(client.referral.category, "dealer")
        self.assertEqual(client.referral.phone_no, "9175551212")

    def test_invalid_body_type_defaults_to_other(self):
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(body_type="not_a_real_body"),
        )
        self.assertEqual(response.status_code, 302)
        intake = ClientIntake.objects.get(organization=self.org, first_name="Jane")
        self.assertEqual(intake.body_type, "other")

    def test_referral_source_normalized_to_dealer(self):
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(source="referral", referral_select=str(self.dealer.id)),
        )
        self.assertEqual(response.status_code, 302)
        intake = ClientIntake.objects.get(organization=self.org, first_name="Jane")
        self.assertEqual(intake.source, "dealer")

    def test_pdf_upload_zone_accepts_pdf(self):
        pdf = SimpleUploadedFile("card.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            {**self._base_post(), "insurance_id_card": pdf},
        )
        self.assertEqual(response.status_code, 302)
        intake = ClientIntake.objects.get(organization=self.org, first_name="Jane")
        self.assertTrue(bool(intake.insurance_id_card))
