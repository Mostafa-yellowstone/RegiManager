"""Tests for intake portal dealer linking, notes, and vehicle options."""

from decimal import Decimal

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
            is_public_intake_enabled=True,
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
        response = self.http.post(reverse("approve-intake", args=[intake.id]))
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
        response = self.http.post(reverse("approve-intake", args=[intake.id]))
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

    def test_approve_creates_new_client_when_dl_blank_not_random_match(self):
        """Blank driver license must not match an unrelated existing client."""
        wrong_client = Client.objects.create(
            organization=self.org,
            first_name="Existing",
            last_name="Person",
            gender="male",
            phone_number="7185550000",
            driver_license="",
        )
        Vehicle.objects.create(
            client=wrong_client,
            vin="OLDVIN00000000001",
            vehicle_type="passenger",
        )
        intake = ClientIntake.objects.create(
            organization=self.org,
            first_name="Brand",
            last_name="NewClient",
            gender="female",
            phone_number="7185558888",
            vin="NEWVIN0000000001",
            source="dealer",
            selected_referral=self.dealer,
            driver_license="",
            intake_note="This note belongs to Brand NewClient.",
            body_type="motorcycle",
            vehicle_type="motorcycle",
        )
        self.http.login(username="intakeowner", password="password123")
        response = self.http.post(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 302)

        new_client = Client.objects.get(organization=self.org, first_name="Brand", last_name="NewClient")
        self.assertNotEqual(new_client.id, wrong_client.id)
        self.assertEqual(new_client.referral_id, self.dealer.id)

        note = ClientNote.objects.filter(client=new_client).first()
        self.assertIsNotNone(note)
        self.assertIn("Brand NewClient", note.content)

        vehicle = Vehicle.objects.get(client=new_client, vin=intake.vin)
        self.assertEqual(vehicle.body_type, "motorcycle")
        self.assertEqual(Vehicle.objects.filter(client=wrong_client).count(), 1)
        self.assertFalse(ClientNote.objects.filter(client=wrong_client).exists())

    def test_approve_does_not_reassign_vehicle_from_other_client(self):
        other = Client.objects.create(
            organization=self.org,
            first_name="Other",
            last_name="Owner",
            gender="male",
            phone_number="7185551111",
            driver_license="DL-OTHER-123",
        )
        shared_vin = "SHAREDVIN00000001"
        other_vehicle = Vehicle.objects.create(
            client=other,
            vin=shared_vin,
            make="Toyota",
            vehicle_type="passenger",
        )
        intake = ClientIntake.objects.create(
            organization=self.org,
            first_name="Separate",
            last_name="Buyer",
            gender="female",
            phone_number="7185552222",
            vin=shared_vin,
            source="walk_in",
            make="Honda",
            vehicle_type="motorcycle",
            body_type="motorcycle",
        )
        self.http.login(username="intakeowner", password="password123")
        response = self.http.post(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 302)

        new_client = Client.objects.get(organization=self.org, first_name="Separate")
        new_vehicle = Vehicle.objects.get(client=new_client, vin=shared_vin)
        self.assertEqual(new_vehicle.make, "Honda")
        self.assertNotEqual(new_vehicle.id, other_vehicle.id)

        other_vehicle.refresh_from_db()
        self.assertEqual(other_vehicle.client_id, other.id)
        self.assertEqual(other_vehicle.make, "Toyota")

    def test_intake_blocks_duplicate_pending_submission(self):
        self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(),
        )
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already being reviewed")
        self.assertEqual(ClientIntake.objects.filter(organization=self.org).count(), 1)

    def test_intake_blocks_existing_client_with_same_vin(self):
        client = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Driver",
            gender="female",
            phone_number="7185559999",
        )
        Vehicle.objects.create(
            client=client,
            vin="1HGBH41JXMN109186",
            vehicle_type="passenger",
        )
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already on file")
        self.assertEqual(ClientIntake.objects.filter(organization=self.org).count(), 0)

    def test_intake_allows_existing_client_new_vehicle_submission(self):
        Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Driver",
            gender="female",
            phone_number="7185559999",
            driver_license="DL-JANE-123",
        )
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(vin="NEWVIN0000000002"),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ClientIntake.objects.filter(organization=self.org).count(), 1)

    def test_intake_allows_same_name_different_people(self):
        Client.objects.create(
            organization=self.org,
            first_name="John",
            last_name="Smith",
            gender="male",
            phone_number="7185551111",
            dob="1980-01-01",
        )
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            self._base_post(
                first_name="John",
                last_name="Smith",
                phone_number="7185552222",
                driver_license="DL-JOHN-OTHER",
                vin="NEWVIN0000000099",
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ClientIntake.objects.filter(organization=self.org).count(), 1)

    def test_approve_links_existing_client_by_name_without_duplicate(self):
        existing = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Driver",
            gender="female",
            phone_number="7185559999",
            driver_license="DL-JANE-123",
        )
        intake = ClientIntake.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Driver",
            gender="female",
            phone_number="7185559999",
            driver_license="DL-JANE-123",
            vin="NEWVIN0000000003",
            source="walk_in",
        )
        self.http.login(username="intakeowner", password="password123")
        response = self.http.post(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)
        vehicle = Vehicle.objects.get(vin="NEWVIN0000000003")
        self.assertEqual(vehicle.client_id, existing.id)

    def test_commercial_intake_submission_saves_business_profile(self):
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            {
                **self._base_post(),
                "is_commercial": "on",
                "business_name": "Acme Fleet LLC",
                "business_ein": "12-3456789",
                "first_name": "",
                "last_name": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        intake = ClientIntake.objects.get(organization=self.org, business_name="Acme Fleet LLC")
        self.assertTrue(intake.is_commercial)
        self.assertEqual(intake.first_name, "Commercial")
        self.assertEqual(intake.last_name, "Acme Fleet LLC")
        self.assertIsNone(intake.gender)

    def test_commercial_intake_requires_business_name(self):
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            {**self._base_post(), "is_commercial": "on", "business_name": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business name is required for commercial")

    def test_approve_commercial_intake_creates_business_client(self):
        intake = ClientIntake.objects.create(
            organization=self.org,
            first_name="Commercial",
            last_name="Acme Fleet LLC",
            gender=None,
            phone_number="7185559999",
            vin="BIZVIN0000000001",
            source="walk_in",
            is_commercial=True,
            business_name="Acme Fleet LLC",
            business_ein="12-3456789",
        )
        self.http.login(username="intakeowner", password="password123")
        response = self.http.post(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 302)
        client = Client.objects.get(organization=self.org, business_name="Acme Fleet LLC")
        self.assertTrue(client.is_commercial)
        self.assertEqual(client.business_ein, "12-3456789")

    def test_commercial_intake_allows_existing_business_new_vehicle(self):
        Client.objects.create(
            organization=self.org,
            first_name="Commercial",
            last_name="Acme Fleet LLC",
            is_commercial=True,
            business_name="Acme Fleet LLC",
            business_ein="12-3456789",
            phone_number="7185550000",
        )
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            {
                **self._base_post(vin="BIZVIN0000000002"),
                "is_commercial": "on",
                "business_name": "Acme Fleet LLC",
                "business_ein": "12-3456789",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ClientIntake.objects.filter(organization=self.org, business_ein="12-3456789").count(), 1)

    def test_intake_monthly_payment_saved_and_copied_on_approval(self):
        response = self.http.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            {**self._base_post(), "insurance_monthly_payment": "149.50"},
        )
        self.assertEqual(response.status_code, 302)
        intake = ClientIntake.objects.get(organization=self.org, first_name="Jane")
        self.assertEqual(intake.insurance_monthly_payment, Decimal("149.50"))

        self.http.login(username="intakeowner", password="password123")
        response = self.http.post(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 302)
        vehicle = Vehicle.objects.get(vin=intake.vin)
        self.assertEqual(vehicle.insurance_monthly_payment, Decimal("149.50"))
