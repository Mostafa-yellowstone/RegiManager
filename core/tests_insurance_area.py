import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.insurance_area_views import insurance_url_for_tab
from core.models import Organization, OrganizationMembership, Space
from core.products import product_for_path

PAGES = (
    "insurance-home",
    "insurance-pipeline",
    "insurance-policies",
    "insurance-payments",
    "insurance-reports",
    "insurance-targets",
    "insurance-agents",
    "insurance-esign",
)
FINANCE_PAGES = ("insurance-finance", "insurance-companies", "insurance-producers")


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class InsuranceAreaBase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Area Org", city="NYC")
        self.space = Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        self.owner = User.objects.create_user(username="area-owner", password="x")
        self.agent = User.objects.create_user(username="area-agent", password="x")
        self.owner_mem = OrganizationMembership.objects.create(
            user=self.owner, organization=self.org, role=OrganizationMembership.Role.OWNER, is_active=True
        )
        self.agent_mem = OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            role=OrganizationMembership.Role.AGENT,
            is_active=True,
            can_use_insurance=True,
        )


class InsuranceAreaPagesTests(InsuranceAreaBase):
    def test_owner_opens_every_page_with_sidebar(self):
        self.client.force_login(self.owner)
        for name in PAGES + FINANCE_PAGES:
            res = self.client.get(reverse(name))
            self.assertEqual(res.status_code, 200, name)
            self.assertContains(res, 'class="ina-side"', msg_prefix=name)
            self.assertContains(res, f'href="{reverse(name)}"', msg_prefix=name)

    def test_menu_uses_the_office_insurance_name(self):
        self.org.insurance_intake_display_name = "Area Insurance Brokers"
        self.org.save()
        self.client.force_login(self.owner)
        res = self.client.get(reverse("insurance-home"))
        self.assertContains(res, "Area Insurance Brokers")

    def test_insurance_menu_opens_motor_club_tlc_and_defense_driving(self):
        self.org.has_psb_portal = False
        self.org.save()
        self.client.force_login(self.agent)
        home = self.client.get(reverse("insurance-home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Motor Club")
        self.assertContains(home, ">TLC<")
        self.assertContains(home, "Defense Driving Course")
        for key in ("motorclub", "tlc", "defense_driving"):
            space = Space.objects.get(organization=self.org, key=key)
            opened = self.client.get(reverse("inventory-detail", args=[space.id]))
            self.assertEqual(opened.status_code, 200, key)

    def test_agent_without_finance_cannot_open_finance_pages(self):
        self.client.force_login(self.agent)
        for name in PAGES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        res = self.client.get(reverse("insurance-home"))
        for name in FINANCE_PAGES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
            self.assertNotContains(res, f'href="{reverse(name)}"')

    def test_agent_without_insurance_access_is_sent_to_the_dashboard(self):
        self.agent_mem.can_use_insurance = False
        self.agent_mem.save()
        self.client.force_login(self.agent)
        res = self.client.get(reverse("insurance-policies"))
        self.assertRedirects(res, reverse("dashboard"), fetch_redirect_response=False)
        res = self.client.post(reverse("add-daily-payment"), {"organization": self.org.id})
        self.assertEqual(res.status_code, 403)

    def test_office_without_insurance_hides_it_even_for_owner(self):
        self.org.has_insurance = False
        self.org.save()
        self.client.force_login(self.owner)
        res = self.client.get(reverse("insurance-home"))
        self.assertRedirects(res, reverse("dashboard"), fetch_redirect_response=False)


class OldInsuranceLinksTests(InsuranceAreaBase):
    def test_old_space_links_open_the_matching_page(self):
        self.client.force_login(self.owner)
        url = reverse("inventory-detail", args=[self.space.id])
        cases = {
            "": reverse("insurance-home"),
            "?tab=insurance&q=smith": reverse("insurance-policies") + "?q=smith",
            "?tab=daily-payments&daily_date=2026-06-01": reverse("insurance-payments") + "?daily_date=2026-06-01",
            "?tab=banking": reverse("insurance-finance"),
            "?tab=quote-pipeline": reverse("insurance-pipeline"),
        }
        for query, expected in cases.items():
            res = self.client.get(url + query)
            self.assertRedirects(res, expected, fetch_redirect_response=False, msg_prefix=query)

    def test_tab_mapping(self):
        self.assertEqual(insurance_url_for_tab("targets", ["target_month=2026-10"]), "/insurance/targets/?target_month=2026-10")
        self.assertEqual(insurance_url_for_tab("unknown"), "/insurance/")

    def test_saving_returns_to_the_page_you_were_on(self):
        self.client.force_login(self.owner)
        res = self.client.post(
            reverse("update-insurance-space-branding"),
            {"organization": self.org.id, "space_label": "Insurance"},
            HTTP_REFERER="http://testserver" + reverse("insurance-payments"),
        )
        self.assertEqual(res["Location"], "http://testserver" + reverse("insurance-payments"))


PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
)


class PoliciesQuoteDateFilterTests(InsuranceAreaBase):
    def setUp(self):
        super().setUp()
        from datetime import timedelta
        from decimal import Decimal

        from django.utils import timezone

        from core.models import Client, InsurancePolicy

        self.today = timezone.localdate()
        self.old_day = self.today.replace(day=1) - timedelta(days=40)
        customer = Client.objects.create(organization=self.org, first_name="Old", last_name="Quote")
        for number, bound in (("OLD-1", self.old_day), ("NEW-1", self.today)):
            InsurancePolicy.objects.create(
                organization=self.org, client=customer, policy_number=number, premium=Decimal("100"),
                start_date=bound, end_date=bound + timedelta(days=180), bound_date=bound, stage="bound",
            )
        self.client.force_login(self.owner)

    def test_default_view_keeps_the_current_month(self):
        res = self.client.get(reverse("insurance-policies"))
        self.assertContains(res, '<td class="ipc-mono">NEW-1</td>')
        self.assertNotContains(res, '<td class="ipc-mono">OLD-1</td>')

    def test_quote_from_reaches_back_past_the_current_month(self):
        res = self.client.get(reverse("insurance-policies"), {"date_from": self.old_day.isoformat()})
        self.assertContains(res, '<td class="ipc-mono">OLD-1</td>')
        self.assertContains(res, '<td class="ipc-mono">NEW-1</td>')
        self.assertContains(res, f"Showing quote dates from {self.old_day:%b %d, %Y} onward")

    def test_quote_range_and_live_table(self):
        params = {"date_from": self.old_day.isoformat(), "date_to": self.old_day.isoformat(), "partial": "crm_policies"}
        res = self.client.get(reverse("insurance-policies"), params)
        self.assertContains(res, '<td class="ipc-mono">OLD-1</td>')
        self.assertNotContains(res, '<td class="ipc-mono">NEW-1</td>')

    def test_invalid_date_is_ignored(self):
        res = self.client.get(reverse("insurance-policies"), {"date_from": "2026-02-30"})
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, '<td class="ipc-mono">OLD-1</td>')


class InsuranceLogoTests(InsuranceAreaBase):
    def setUp(self):
        super().setUp()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.owner)

    def post_branding(self, **extra):
        data = {"organization": self.org.id, "space_label": "Insurance", **extra}
        return self.client.post(reverse("update-insurance-space-branding"), data)

    def test_sidebar_offers_to_add_a_logo_until_one_is_uploaded(self):
        self.assertContains(self.client.get(reverse("insurance-home")), "+ Add your logo")
        self.post_branding(logo=SimpleUploadedFile("logo.png", PNG_1PX, content_type="image/png"))
        self.space.refresh_from_db()
        self.assertTrue(self.space.logo)
        res = self.client.get(reverse("insurance-home"))
        self.assertContains(res, f'<span class="ina-side__logo"><img src="{self.space.logo.url}"')
        self.assertNotContains(res, "+ Add your logo")

    def test_logo_can_be_removed(self):
        self.post_branding(logo=SimpleUploadedFile("logo.png", PNG_1PX, content_type="image/png"))
        self.post_branding(clear_logo="on")
        self.space.refresh_from_db()
        self.assertFalse(self.space.logo)

    def test_svg_logo_is_rejected(self):
        svg = SimpleUploadedFile("logo.svg", b"<svg onload='alert(1)'/>", content_type="image/svg+xml")
        self.post_branding(logo=svg)
        self.space.refresh_from_db()
        self.assertFalse(self.space.logo)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class InsuranceOnlyOfficeTests(InsuranceAreaBase):
    def setUp(self):
        super().setUp()
        self.org.has_psb_portal = False
        self.org.save()

    def test_psb_pages_send_insurance_only_users_to_insurance(self):
        self.client.force_login(self.agent)
        res = self.client.get(reverse("dashboard"))
        self.assertRedirects(res, reverse("insurance-home"), fetch_redirect_response=False)
        res = self.client.get(reverse("spaces-home"))
        self.assertRedirects(res, reverse("insurance-home"), fetch_redirect_response=False)

    def test_menu_shows_insurance_and_hides_psb_sections(self):
        self.client.force_login(self.owner)
        res = self.client.get(reverse("insurance-home"))
        self.assertContains(res, f'href="{reverse("insurance-home")}"')
        self.assertNotContains(res, f'href="{reverse("spaces-home")}"')

    def test_member_without_any_product_is_refused_without_redirect_loop(self):
        self.agent_mem.can_use_insurance = False
        self.agent_mem.save()
        self.client.force_login(self.agent)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("insurance-home")).status_code, 403)

    def test_client_profile_hides_dmv_sections(self):
        from core.models import Client

        client_obj = Client.objects.create(organization=self.org, first_name="Ina", last_name="Only")
        self.client.force_login(self.owner)
        res = self.client.get(reverse("client-detail", args=[client_obj.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Insurance Policies")
        self.assertNotContains(res, "Transaction History")
        self.assertNotContains(res, "Lifetime Spend")
        self.assertNotContains(res, reverse("add-vehicle", args=[client_obj.id]))

    def test_shared_tools_stay_open(self):
        self.client.force_login(self.agent)
        self.assertEqual(self.client.get(reverse("agent-portal-home")).status_code, 200)


class InsuranceSearchTests(InsuranceAreaBase):
    def setUp(self):
        super().setUp()
        from decimal import Decimal

        from core.models import Client, InsuranceCompany, InsurancePolicy, Vehicle

        self.client_obj = Client.objects.create(
            organization=self.org, first_name="Maria", last_name="Lopez", phone_number="7185551234"
        )
        company = InsuranceCompany.objects.create(organization=self.org, name="Searchable Mutual")
        InsurancePolicy.objects.create(
            organization=self.org, client=self.client_obj, insurance_company=company,
            policy_number="NYA-77821", premium=Decimal("900.00"), stage="bound", status="active",
            start_date="2026-06-01", end_date="2026-12-01",
        )
        Vehicle.objects.create(client=self.client_obj, vin="1HGCM82633A004352", plate_number="KZT1234")
        other = Organization.objects.create(name="Other Org", city="NYC")
        Client.objects.create(organization=other, first_name="Maria", last_name="Hidden")

    def _labels(self, q, user=None):
        self.client.force_login(user or self.owner)
        data = self.client.get(reverse("insurance-search"), {"q": q}).json()
        return {g["title"]: [i["label"] for i in g["items"]] for g in data["groups"]}

    def test_finds_clients_by_name_and_phone_within_the_office(self):
        self.assertEqual(self._labels("maria")["Clients"], ["Maria Lopez"])
        self.assertEqual(self._labels("555-1234")["Clients"], ["Maria Lopez"])

    def test_finds_policies_vehicles_and_companies(self):
        self.assertIn("NYA-77821", self._labels("77821")["Policies"])
        self.assertTrue(self._labels("kzt1234")["Vehicles"][0].startswith("KZT1234"))
        self.assertEqual(self._labels("searchable")["Companies"], ["Searchable Mutual"])

    def test_companies_hidden_without_finance_access(self):
        self.assertNotIn("Companies", self._labels("searchable", user=self.agent))


class PolicyAgentChangeTests(InsuranceAreaBase):
    def setUp(self):
        super().setUp()
        from datetime import timedelta
        from decimal import Decimal

        from django.utils import timezone

        from core.insurance_quote_pipeline_models import InsuranceQuoteLead
        from core.insurance_renewal_models import InsuranceRenewal
        from core.models import Client, InsurancePolicy

        today = timezone.localdate()
        self.new_agent = User.objects.create_user(username="area-agent-2", password="x", first_name="Nadia")
        self.new_mem = OrganizationMembership.objects.create(
            user=self.new_agent, organization=self.org, role=OrganizationMembership.Role.AGENT,
            is_active=True, can_use_insurance=True,
        )
        customer = Client.objects.create(organization=self.org, first_name="Move", last_name="Me")
        self.policy = InsurancePolicy.objects.create(
            organization=self.org, client=customer, policy_number="AG-1", premium=Decimal("500"),
            start_date=today, end_date=today + timedelta(days=30), stage="bound", added_by=self.agent,
        )
        self.renewal = InsuranceRenewal.objects.create(
            organization=self.org, policy=self.policy, expiration_date=self.policy.end_date, assigned_to=self.agent
        )
        self.lead = InsuranceQuoteLead.objects.create(
            organization=self.org, created_by=self.owner, client_name="Move Me", phone="5550001111",
            assigned_to=self.agent_mem, stage="quoting", crm_policy=self.policy,
        )

    def test_changing_the_agent_moves_open_work(self):
        from core.insurance_policy_agent import sync_policy_agent

        self.policy.added_by = self.new_agent
        self.policy.save()
        moved = sync_policy_agent(self.policy, actor=self.owner)
        self.renewal.refresh_from_db()
        self.lead.refresh_from_db()
        self.policy.refresh_from_db()
        self.assertEqual(moved["renewals"], 1)
        self.assertEqual(moved["quotes"], 1)
        self.assertEqual(self.renewal.assigned_to, self.new_agent)
        self.assertEqual(self.lead.assigned_to, self.new_mem)
        self.assertEqual(self.lead.agent_task.assigned_to, self.new_mem)
        self.assertEqual(self.policy.added_by, self.new_agent)

    def test_admin_change_form_offers_an_agent_dropdown(self):
        self.owner.is_staff = self.owner.is_superuser = True
        self.owner.save()
        self.client.force_login(self.owner)
        res = self.client.get(reverse("admin:core_insurancepolicy_change", args=[self.policy.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '<select name="added_by"')
        self.assertContains(res, ">Nadia<")


class ProductForPathTests(TestCase):
    def test_paths(self):
        self.assertEqual(product_for_path("/insurance/policies/"), "insurance")
        self.assertEqual(product_for_path("/dashboard/spaces/insurance/policy/add/"), "insurance")
        self.assertEqual(product_for_path("/dashboard/insurance-quotes/5/stage/"), "insurance")
        self.assertEqual(product_for_path("/dashboard/agent-portal/"), "shared")
        self.assertEqual(product_for_path("/dashboard/spaces/"), "psb")
        self.assertEqual(product_for_path("/dashboard/spaces/motorclub/1/member/add/"), "shared")
        self.assertEqual(product_for_path("/dashboard/spaces/tlc/1/policy/add/"), "shared")
        self.assertEqual(product_for_path("/dashboard/spaces/defense-driving/1/package/save/"), "shared")
        self.assertIsNone(product_for_path("/api/clients/"))
