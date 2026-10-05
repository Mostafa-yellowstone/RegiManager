from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client as DjangoClient, TestCase, override_settings
from django.urls import reverse

from core.insurance_space_metrics import period_stats
from core.models import Client, InsurancePolicy, Organization, OrganizationMembership, Space
from core.role_permissions import apply_role_permission_pack


class BusinessPremiumSplitTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Split Org", city="NYC")
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Pat",
            last_name="Policy",
            gender="male",
            phone_number="5551112222",
        )

    def _policy(self, number, premium, business_type, bound_date, *, stage="bound", status="active"):
        return InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            policy_number=number,
            premium=Decimal(premium),
            business_type=business_type,
            stage=stage,
            status=status,
            bound_date=bound_date,
            start_date=date(2026, 10, 1),
            end_date=date(2027, 4, 1),
        )

    def test_period_splits_bound_active_premium_by_business_type(self):
        self._policy("NB-1", "1000.00", "new_business", date(2026, 10, 5))
        self._policy("NB-2", "250.50", "new_business", date(2026, 10, 20))
        self._policy("RN-1", "800.00", "renewal", date(2026, 10, 8))
        self._policy("RW-1", "400.00", "rewrite", date(2026, 10, 12))
        self._policy("OUT", "9000.00", "renewal", date(2026, 9, 15))
        self._policy("QUOTE", "700.00", "new_business", date(2026, 10, 6), stage="quote")
        self._policy("OFF", "600.00", "rewrite", date(2026, 10, 7), status="inactive")

        stats = period_stats(
            InsurancePolicy.objects.filter(organization=self.org),
            date(2026, 10, 1),
            date(2026, 10, 31),
        )

        self.assertEqual(stats["new_business_premium"], 1250.50)
        self.assertEqual(stats["renewal_premium"], 800.0)
        self.assertEqual(stats["rewrite_premium"], 400.0)
        self.assertEqual(stats["premium"], 2450.50)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class InsuranceBookPremiumCardsTests(TestCase):
    def test_crm_hero_shows_three_premiums_for_selected_range(self):
        org = Organization.objects.create(name="Hero Org", city="NYC")
        space = Space.objects.create(organization=org, label="Insurance", key="insurance")
        user = User.objects.create_user(username="herowner", password="password123")
        membership = OrganizationMembership.objects.create(
            user=user,
            organization=org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        apply_role_permission_pack(membership)
        membership.accessible_spaces.add(space)
        client = Client.objects.create(organization=org, first_name="Pat", last_name="Policy")

        def add(number, premium, business_type):
            InsurancePolicy.objects.create(
                organization=org,
                client=client,
                policy_number=number,
                premium=Decimal(premium),
                business_type=business_type,
                stage="bound",
                status="active",
                bound_date=date(2026, 10, 10),
                start_date=date(2026, 10, 10),
                end_date=date(2027, 4, 10),
            )

        add("NB", "1250.50", "new_business")
        add("RN", "800.00", "renewal")
        add("RW", "400.00", "rewrite")

        http = DjangoClient()
        http.login(username="herowner", password="password123")
        response = http.get(
            reverse("inventory-detail", args=[space.id])
            + "?tab=insurance&comp_mode=custom&comp_from=2026-10-01&comp_to=2026-10-31"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Insurance book snapshot")
        self.assertContains(response, "New Business")
        self.assertContains(response, "Renewal")
        self.assertContains(response, "Rewrite")
        self.assertContains(response, "Oct 01")
        self.assertContains(response, "$1250.50")
        self.assertContains(response, "$800.00")
        self.assertContains(response, "$400.00")
