from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.insurance_client_insights import (
    client_timeline,
    coverage_gaps,
    detect_gaps,
    household_suggestions,
    household_summary,
    link_household,
    unlink_household,
)
from core.insurance_producers import add_months
from core.models import (
    Client,
    ClientNote,
    DailyPaymentTransaction,
    InsuranceCompany,
    InsuranceCoverageGapStatus,
    InsuranceHousehold,
    InsuranceHouseholdMember,
    InsurancePolicy,
    InsurancePolicyVehicle,
    InsuranceQuoteLead,
    InsuranceRenewal,
    Organization,
    OrganizationMembership,
    Space,
    Vehicle,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class InsightsBase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.org = Organization.objects.create(name="Insight Org", city="NYC", has_psb_portal=False)
        Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        self.owner = User.objects.create_user(username="ci-owner", password="x")
        self.agent = User.objects.create_user(username="ci-agent", password="x", first_name="Ana", last_name="Agent")
        OrganizationMembership.objects.create(
            user=self.owner, organization=self.org, role=OrganizationMembership.Role.OWNER, is_active=True,
            can_use_insurance=True,
        )
        self.agent_membership = OrganizationMembership.objects.create(
            user=self.agent, organization=self.org, role=OrganizationMembership.Role.AGENT, is_active=True,
            can_use_insurance=True, can_deal_with_insurance=True,
        )
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Acme Mutual")
        self.customer = Client.objects.create(
            organization=self.org, first_name="Mia", last_name="Stone", phone_number="(718) 555-0199",
            building_no="12", street_address="Oak St", zip_code="11201", email="mia@example.com",
        )

    def client_named(self, first, last="Stone", **extra):
        return Client.objects.create(organization=self.org, first_name=first, last_name=last, **extra)

    def policy(self, number, insurance_type="auto_personal", *, client=None, days=120, stage="bound", status="active", **extra):
        end = self.today + timedelta(days=days)
        return InsurancePolicy.objects.create(
            organization=self.org,
            client=client or self.customer,
            policy_number=number,
            insurance_company=self.company,
            premium=extra.pop("premium", Decimal("1000.00")),
            start_date=add_months(end, -6),
            end_date=end,
            bound_date=add_months(end, -6),
            stage=stage,
            status=status,
            insurance_type=insurance_type,
            added_by=extra.pop("added_by", self.agent),
            **extra,
        )


class HouseholdTests(InsightsBase):
    def test_suggests_same_phone_or_address_and_skips_dismissed(self):
        by_phone = self.client_named("Leo", "Diaz", phone_number="718.555.0199")
        by_address = self.client_named("Ava", building_no="12", street_address="oak st.", zip_code="11201-4455")
        self.client_named("Max", "Other", phone_number="2125550000")

        found = {s["client"].id: s["reasons"] for s in household_suggestions(self.customer)}
        self.assertEqual(found, {by_phone.id: ["Same phone"], by_address.id: ["Same address"]})

        self.client.force_login(self.agent)
        self.client.post(reverse("client-household-dismiss", args=[self.customer.id]), {"other_id": by_phone.id})
        found = {s["client"].id for s in household_suggestions(self.customer)}
        self.assertEqual(found, {by_address.id})

    def test_link_creates_household_and_summary_totals_policies(self):
        spouse = self.client_named("Leo")
        self.policy("A-1", premium=Decimal("900.00"))
        self.policy("H-1", "ho3", client=spouse, premium=Decimal("600.00"), days=30)

        self.client.force_login(self.agent)
        resp = self.client.post(
            reverse("client-household-link", args=[self.customer.id]),
            {"other_id": spouse.id, "relationship": "spouse"},
        )
        self.assertEqual(resp.status_code, 302)
        household = InsuranceHousehold.objects.get()
        self.assertEqual(household.name, "Stone household")
        roles = dict(household.members.values_list("client_id", "relationship"))
        self.assertEqual(roles, {self.customer.id: "primary", spouse.id: "spouse"})

        summary = household_summary(spouse)
        self.assertEqual(summary.policy_count, 2)
        self.assertEqual(summary.total_premium, Decimal("1500.00"))
        self.assertEqual(summary.next_expiration, self.today + timedelta(days=30))

    def test_linking_two_households_merges_them_and_unlink_cleans_up(self):
        a, b, c, d = (self.client_named(n) for n in ("A", "B", "C", "D"))
        link_household(a, b, relationship="spouse", user=self.agent)
        link_household(c, d, relationship="child", user=self.agent)
        link_household(a, c, relationship="parent", user=self.agent)
        self.assertEqual(InsuranceHousehold.objects.count(), 1)
        self.assertEqual(InsuranceHouseholdMember.objects.count(), 4)

        for person in (b, c, d):
            unlink_household(person)
        self.assertEqual(InsuranceHousehold.objects.count(), 0)

    def test_other_office_client_cannot_be_linked(self):
        other_org = Organization.objects.create(name="Other")
        stranger = Client.objects.create(organization=other_org, first_name="X", last_name="Y")
        self.client.force_login(self.agent)
        self.client.post(reverse("client-household-link", args=[self.customer.id]), {"other_id": stranger.id})
        self.assertFalse(InsuranceHousehold.objects.exists())

    def test_search_returns_office_clients_only(self):
        self.client_named("Leonard", "Diaz")
        Client.objects.create(organization=Organization.objects.create(name="Z"), first_name="Leonard", last_name="Q")
        self.client.force_login(self.agent)
        data = self.client.get(reverse("client-household-search", args=[self.customer.id]), {"q": "leon"}).json()
        self.assertEqual([r["name"] for r in data["results"]], ["Leonard Diaz"])


class GapTests(InsightsBase):
    def keys(self, client=None):
        return {g.key for g in detect_gaps(client or self.customer, today=self.today)}

    def test_auto_without_home_suggests_home(self):
        self.policy("A-1")
        self.assertIn("home", self.keys())
        self.policy("H-1", "ho4")
        self.assertNotIn("home", self.keys())

    def test_home_gap_is_household_wide(self):
        spouse = self.client_named("Leo")
        self.policy("A-1")
        self.policy("H-1", "ho3", client=spouse)
        self.assertIn("home", self.keys())
        link_household(self.customer, spouse, relationship="spouse", user=self.agent)
        self.assertNotIn("home", self.keys())

    def test_umbrella_for_two_vehicles_or_home_plus_auto(self):
        auto = self.policy("A-1")
        self.assertNotIn("umbrella", self.keys())
        InsurancePolicyVehicle.objects.create(policy=auto, auto_number=1, vin="1")
        InsurancePolicyVehicle.objects.create(policy=auto, auto_number=2, vin="2")
        self.assertIn("umbrella", self.keys())
        self.policy("U-1", "umbrella")
        self.assertNotIn("umbrella", self.keys())

    def test_profile_vehicle_not_on_any_policy(self):
        car = Vehicle.objects.create(client=self.customer, vin="1HGCM82633A004352", plate_number="ABC123", make="Honda")
        Vehicle.objects.create(client=self.customer, vin="BOAT1", vehicle_type="boat")
        self.assertIn(f"vehicle:{car.id}", self.keys())
        auto = self.policy("A-1")
        InsurancePolicyVehicle.objects.create(policy=auto, auto_number=1, plate_number="abc123")
        self.assertNotIn(f"vehicle:{car.id}", self.keys())

    def test_lapsed_policy_is_a_win_back_until_replaced_or_renewed(self):
        old = self.policy("OLD-1", "ho3", days=-40)
        self.assertIn(f"lapsed:{old.id}", self.keys())
        InsuranceRenewal.objects.create(
            organization=self.org, policy=old, expiration_date=old.end_date, stage=InsuranceRenewal.Stage.RENEWED
        )
        self.assertNotIn(f"lapsed:{old.id}", self.keys())

        older = self.policy("OLD-2", "ho6", days=-400)
        self.assertNotIn(f"lapsed:{older.id}", self.keys())

    def test_business_gaps(self):
        biz = self.client_named("Bob", "Builder", is_commercial=True, business_name="Bob Builds LLC")
        self.assertEqual(self.keys(biz), {"gl", "wc"})
        self.policy("GL-1", "general_liability", client=biz)
        self.assertEqual(self.keys(biz), {"wc"})

    def test_dismissed_gap_is_hidden(self):
        self.policy("A-1")
        self.client.force_login(self.agent)
        self.client.post(reverse("client-gap-dismiss", args=[self.customer.id]), {"gap_key": "home"})
        self.assertNotIn("home", {g.key for g in coverage_gaps(self.customer)})


class GapQuoteTests(InsightsBase):
    def test_request_quote_creates_lead_for_clients_agent_on_the_right_client(self):
        self.client_named("Mia")
        self.policy("A-1")
        self.client.force_login(self.owner)

        resp = self.client.post(reverse("client-gap-quote", args=[self.customer.id]), {"gap_key": "home"})
        self.assertEqual(resp.status_code, 302)

        lead = InsuranceQuoteLead.objects.get()
        self.assertEqual(lead.insurance_type, "ho4")
        self.assertEqual(lead.heard_about, "existing_client")
        self.assertEqual(lead.assigned_to, self.agent_membership)
        self.assertEqual(lead.crm_policy.client, self.customer)
        self.assertEqual(lead.crm_policy.stage, InsurancePolicy.StageChoices.QUOTE)
        self.assertEqual(lead.crm_policy.added_by, self.agent)
        status = InsuranceCoverageGapStatus.objects.get()
        self.assertEqual((status.gap_key, status.status, status.lead), ("home", "quoted", lead))

        gap = next(g for g in coverage_gaps(self.customer) if g.key == "home")
        self.assertEqual(gap.status, "quoted")

    def test_unknown_gap_is_rejected(self):
        self.client.force_login(self.agent)
        self.client.post(reverse("client-gap-quote", args=[self.customer.id]), {"gap_key": "umbrella"})
        self.assertFalse(InsuranceQuoteLead.objects.exists())


class TimelineAndPageTests(InsightsBase):
    def test_timeline_merges_sources_newest_first(self):
        policy = self.policy("A-1")
        DailyPaymentTransaction.objects.create(
            organization=self.org, client=self.customer, insurance_policy=policy, transaction_date=self.today,
            amount=Decimal("150.00"), payment_type="monthly_payment", payment_method="cash",
        )
        ClientNote.objects.create(client=self.customer, content="Called about home quote", created_by=self.agent)

        items = client_timeline(self.customer, include_dmv=False)
        kinds = {i.kind for i in items}
        self.assertTrue({"policy", "payment", "note"} <= kinds)
        keys = [i.sort_key for i in items]
        self.assertEqual(keys, sorted(keys, reverse=True))

    def test_profile_shows_sections_for_insurance_users_only(self):
        self.policy("A-1")
        self.client.force_login(self.agent)
        html = self.client.get(reverse("client-detail", args=[self.customer.id])).content.decode()
        self.assertIn('id="timeline"', html)
        self.assertIn('id="coverage-gaps"', html)
        self.assertIn('id="household"', html)

        OrganizationMembership.objects.filter(user=self.agent).update(can_use_insurance=False)
        self.org.has_psb_portal = True
        self.org.save(update_fields=["has_psb_portal"])
        resp = self.client.get(reverse("client-detail", args=[self.customer.id]))
        self.assertNotIn('id="coverage-gaps"', resp.content.decode())

    def test_actions_require_insurance_access(self):
        OrganizationMembership.objects.filter(user=self.agent).update(can_use_insurance=False)
        self.client.force_login(self.agent)
        resp = self.client.post(reverse("client-gap-dismiss", args=[self.customer.id]), {"gap_key": "home"})
        self.assertIn(resp.status_code, (302, 403))
        self.assertFalse(InsuranceCoverageGapStatus.objects.exists())

    def test_policy_detail_shows_renewal_chain(self):
        from core.insurance_renewals import default_terms, renew, sync_renewals

        old = self.policy("OLD-1", days=10)
        sync_renewals(self.org, today=self.today)
        card = old.renewal
        new_policy = renew(card, self.agent, default_terms(card))
        self.client.force_login(self.agent)
        html = self.client.get(reverse("insurance-policy-detail", args=[new_policy.id])).content.decode()
        self.assertIn("ins-renewal__chain", html)
        self.assertIn("#OLD-1", html)
