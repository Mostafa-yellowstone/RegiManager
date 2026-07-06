"""Tests for public insurance intake portal and agent queue."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.insurance_intake_constants import EXCLUDED_INSURANCE_INTAKE_TYPES
from core.insurance_intake_forms import InsuranceIntakeForm
from core.models import (
    InsuranceIntake,
    InsurancePolicy,
    Organization,
    OrganizationMembership,
    Space,
)

User = get_user_model()


class InsuranceIntakeFormTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test PSB", city="Albany", state="NY")

    def _base_personal_data(self):
        return {
            "insurance_type": "auto_personal",
            "source": "walk_in",
            "business_type": "new_business",
            "first_name": "Jane",
            "last_name": "Driver",
            "email": "jane@example.com",
            "phone_number": "5185550100",
            "dob": "1990-01-15",
            "driver_license": "D1234567",
            "street_address": "100 Main St",
            "city": "Albany",
            "state": "NY",
            "zip_code": "12207",
            "vin": "1HGCM82633A123456",
            "year": 2020,
            "make": "Honda",
            "model": "Accord",
            "requested_effective_date": "2026-07-01",
        }

    def test_personal_auto_requires_vehicle_and_license(self):
        data = self._base_personal_data()
        data.pop("vin")
        form = InsuranceIntakeForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("vin", form.errors)

    def test_commercial_auto_requires_business_fields(self):
        data = self._base_personal_data()
        data["insurance_type"] = "commercial_auto"
        data["business_name"] = "Acme Taxi LLC"
        data["business_ein"] = "12-3456789"
        form = InsuranceIntakeForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid())

    def test_disability_not_in_public_choices(self):
        choices = dict(InsuranceIntakeForm().fields["insurance_type"].choices)
        for excluded in EXCLUDED_INSURANCE_INTAKE_TYPES:
            self.assertNotIn(excluded, choices)


@override_settings(DEBUG=True)
class PublicInsuranceIntakePortalTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Insurance PSB",
            city="Buffalo",
            state="NY",
            is_public_insurance_intake_enabled=True,
        )
        self.url = reverse("public-insurance-intake-direct", args=[self.org.portal_token])

    def test_portal_disabled_when_flag_off(self):
        self.org.is_public_insurance_intake_enabled = False
        self.org.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not available")

    def test_successful_submission(self):
        response = self.client.post(
            self.url,
            {
                "insurance_type": "auto_personal",
                "source": "google_search",
                "business_type": "new_business",
                "first_name": "Sam",
                "last_name": "Lee",
                "email": "sam@example.com",
                "phone_number": "7165550199",
                "dob": "1985-06-20",
                "driver_license": "S9988776",
                "street_address": "22 Oak Ave",
                "city": "Buffalo",
                "state": "NY",
                "zip_code": "14201",
                "vin": "2HGFG3B54CH501234",
                "year": 2018,
                "make": "Toyota",
                "model": "Camry",
                "requested_effective_date": "2026-08-01",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(InsuranceIntake.objects.filter(organization=self.org).count(), 1)

    def test_insurance_success_uses_insurance_review_link(self):
        self.org.insurance_show_review_button = True
        self.org.insurance_review_link = "https://example.com/insurance-review"
        self.org.show_review_button = True
        self.org.review_link = "https://example.com/client-review"
        self.org.save()
        response = self.client.get(
            reverse("public-insurance-intake-success")
            + f"?portal_token={self.org.portal_token}"
        )
        self.assertContains(response, "https://example.com/insurance-review")
        self.assertNotContains(response, "https://example.com/client-review")

    def test_portal_uses_custom_brand_name(self):
        self.org.insurance_intake_display_name = "Xpress Insurance Solutions"
        self.org.insurance_intake_tagline = "Your trusted commercial & personal lines partner."
        self.org.save()
        response = self.client.get(self.url)
        self.assertContains(response, "Xpress Insurance Solutions")
        self.assertContains(response, "Your trusted commercial")
        self.assertNotContains(response, "Insurance PSB")


@override_settings(DEBUG=True)
class EzlynxInsuranceIntakePortalTests(TestCase):
    EZLYNX_URL = (
        "https://www.agentinsure.com/compare/auto-insurance-home-insurance/"
        "xpressinsurancesolutions/quote.aspx"
    )

    def setUp(self):
        self.org = Organization.objects.create(
            name="Xpress Insurance",
            city="Yonkers",
            state="NY",
            is_public_insurance_intake_enabled=True,
            insurance_ezlynx_quote_url=self.EZLYNX_URL,
            insurance_intake_portal_mode="ezlynx_dual",
            insurance_intake_display_name="Xpress Insurance Solutions",
        )
        self.url = reverse("public-insurance-intake-direct", args=[self.org.portal_token])

    def test_dual_mode_shows_capture_step(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Step 1 of 2")
        self.assertContains(response, "Continue to Quote Application")

    def test_capture_creates_intake_and_shows_embed(self):
        response = self.client.post(
            self.url,
            {
                "first_name": "Alex",
                "last_name": "Rivera",
                "email": "alex@example.com",
                "phone_number": "9145550100",
                "zip_code": "10704",
                "quote_type": "auto",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("step=quote", response.url)

        intake = InsuranceIntake.objects.get(organization=self.org)
        self.assertEqual(intake.first_name, "Alex")
        self.assertEqual(intake.additional_data.get("portal_mode"), "ezlynx_dual")

        quote_response = self.client.get(self.url + "?step=quote")
        self.assertContains(quote_response, self.EZLYNX_URL)
        self.assertContains(quote_response, "ezlynxQuoteFrame")
        self.assertContains(quote_response, "Alex")
        self.assertContains(quote_response, 'name="Applicant_FirstName"')
        self.assertContains(quote_response, 'value="Alex"')
        self.assertContains(quote_response, 'name="Applicant_LOB"')
        self.assertContains(quote_response, 'value="Auto"')
        self.assertContains(quote_response, "ezlynxPrefillForm")

    def test_ezlynx_only_skips_capture(self):
        self.org.insurance_intake_portal_mode = "ezlynx_only"
        self.org.save()
        response = self.client.get(self.url)
        self.assertContains(response, "ezlynxQuoteFrame")
        self.assertNotContains(response, "Step 1 of 2")

    def test_native_mode_when_configured(self):
        self.org.insurance_intake_portal_mode = "native"
        self.org.save()
        response = self.client.get(self.url)
        self.assertContains(response, "Coverage Type")
        self.assertNotContains(response, "ezlynxQuoteFrame")


class InsuranceIntakeBrandingTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Xpress Plates & Registrations Inc", city="NY", state="NY")
        self.owner = User.objects.create_user(username="owner", password="pass12345")
        self.space = Space.objects.create(organization=self.org, key="insurance", label="Insurance Space")
        membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            can_view_spaces=True,
        )
        membership.accessible_spaces.add(self.space)

    def test_owner_can_update_branding(self):
        self.client.login(username="owner", password="pass12345")
        ezlynx_url = (
            "https://www.agentinsure.com/compare/auto-insurance-home-insurance/"
            "xpressinsurancesolutions/quote.aspx"
        )
        response = self.client.post(
            reverse("update-insurance-space-branding"),
            {
                "organization": self.org.id,
                "space_label": "Xpress Insurance Hub",
                "insurance_intake_display_name": "Xpress Insurance Solutions",
                "insurance_intake_tagline": "Commercial, personal & fleet coverage.",
                "insurance_ezlynx_quote_url": ezlynx_url,
                "insurance_intake_portal_mode": "ezlynx_dual",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.space.refresh_from_db()
        self.org.refresh_from_db()
        self.assertEqual(self.space.label, "Xpress Insurance Hub")
        self.assertEqual(self.org.insurance_intake_display_name, "Xpress Insurance Solutions")
        self.assertEqual(self.org.insurance_intake_brand_name, "Xpress Insurance Solutions")
        self.assertEqual(self.org.insurance_ezlynx_quote_url, ezlynx_url)
        self.assertEqual(self.org.insurance_intake_portal_mode, "ezlynx_dual")


class EzlynxPrefillTests(TestCase):
    def test_build_prefill_fields_maps_phone_and_quote_type(self):
        from core.ezlynx_prefill import build_ezlynx_prefill_fields

        intake = InsuranceIntake(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            phone_number="914-555-0100",
            zip_code="10704",
            additional_data={"ezlynx_quote_type": "home"},
        )
        fields = build_ezlynx_prefill_fields(intake)
        self.assertEqual(fields["Applicant_FirstName"], "Jane")
        self.assertEqual(fields["Applicant_HomePhone"], "914")
        self.assertEqual(fields["Applicant_HomePhone_1"], "555")
        self.assertEqual(fields["Applicant_HomePhone_2"], "0100")
        self.assertEqual(fields["Applicant_LOB"], "Home")
        self.assertEqual(fields["Rating_Zip"], "10704")


class InsuranceIntakeQueueTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Queue PSB", city="Rochester", state="NY")
        self.agent = User.objects.create_user(username="insagent", password="pass12345")
        self.other = User.objects.create_user(username="other", password="pass12345")
        OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            role=OrganizationMembership.Role.MEMBER,
            can_view_spaces=True,
            can_deal_with_insurance=True,
        )
        OrganizationMembership.objects.create(
            user=self.other,
            organization=self.org,
            role=OrganizationMembership.Role.MEMBER,
            can_view_spaces=True,
            can_deal_with_insurance=False,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="insurance",
            label="Insurance",
        )
        for membership in OrganizationMembership.objects.filter(organization=self.org):
            membership.accessible_spaces.add(self.space)
        self.intake = InsuranceIntake.objects.create(
            organization=self.org,
            first_name="Pat",
            last_name="Quote",
            phone_number="5855550101",
            email="pat@example.com",
            insurance_type="auto_personal",
            street_address="1 Main",
            city="Rochester",
            state="NY",
            zip_code="14604",
            requested_effective_date=date(2026, 9, 1),
            vin="3VW2A7AJ5HM123456",
            year=2019,
            make="VW",
            model="Jetta",
            additional_data={"portal_mode": "ezlynx_dual"},
        )

    def test_agent_sees_intake_queue_tab(self):
        self.client.login(username="insagent", password="pass12345")
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Intake Queue")
        self.assertContains(response, "Pat Quote")
        self.assertContains(response, "EZLynx Portal")

    def test_non_insurance_agent_does_not_see_queue(self):
        self.client.login(username="other", password="pass12345")
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "tab-intake-queue-btn")

    def test_owner_sees_intake_queue_without_insurance_agent_flag(self):
        owner = User.objects.create_user(username="owner", password="pass12345")
        owner_membership = OrganizationMembership.objects.create(
            user=owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            can_view_spaces=True,
            can_deal_with_insurance=False,
        )
        owner_membership.accessible_spaces.add(self.space)
        self.client.login(username="owner", password="pass12345")
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Intake Queue")
        self.assertContains(response, "Pat Quote")
        self.assertContains(response, "EZLynx Portal")

    def test_approve_redirects_to_inventory_detail_intake_tab(self):
        self.client.login(username="insagent", password="pass12345")
        response = self.client.post(reverse("approve-insurance-intake", args=[self.intake.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/dashboard/inventory/{self.space.id}/", response.url)
        self.assertIn("tab=intake-queue", response.url)
        self.intake.refresh_from_db()
        self.assertEqual(self.intake.status, InsuranceIntake.Status.APPROVED)
        self.assertIsNotNone(self.intake.created_policy_id)
        policy = self.intake.created_policy
        self.assertEqual(policy.stage, InsurancePolicy.StageChoices.QUOTE)
        self.assertEqual(policy.premium, Decimal("0.00"))
