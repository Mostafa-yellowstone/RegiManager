from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client as DjangoClient, TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.insurance_targets_metrics import (
    build_insurance_targets_dashboard,
    planner_recommendations,
)
from core.insurance_targets_models import InsuranceMonthlyTarget
from core.models import (
    Client,
    InsuranceCompany,
    InsurancePolicy,
    Organization,
    OrganizationMembership,
    Space,
)


class InsuranceTargetsPlannerTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="tgtowner", password="password123")
        self.agent = User.objects.create_user(username="tgtagent", password="password123")
        self.org = Organization.objects.create(name="Targets Org", city="NYC")
        self.owner_mem = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
            can_deal_with_insurance=True,
            can_view_spaces=True,
            can_view_banking=True,
        )
        self.agent_mem = OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
            can_deal_with_insurance=True,
            can_view_spaces=True,
            can_view_banking=False,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="insurance",
            label="Insurance",
        )
        self.company = InsuranceCompany.objects.create(
            organization=self.org,
            name="Acme Mutual",
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Pat",
            last_name="Policy",
            gender="male",
            phone_number="5551112222",
        )
        self.http = DjangoClient()
        today = date.today()
        bound_day = min(10, max(today.day, 1))
        InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            policy_number="TGT-1",
            insurance_company=self.company,
            premium=Decimal("2000.00"),
            commission_rate=Decimal("10.00"),
            commission_amount=Decimal("200.00"),
            stage=InsurancePolicy.StageChoices.BOUND,
            status=InsurancePolicy.StatusChoices.ACTIVE,
            insurance_type="auto_personal",
            start_date=date(today.year, today.month, 1),
            end_date=date(today.year, today.month, 28),
            insurance_period_months=6,
            bound_date=date(today.year, today.month, bound_day),
            added_by=self.owner,
        )
        InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            policy_number="TGT-2",
            insurance_company=self.company,
            premium=Decimal("5000.00"),
            commission_rate=Decimal("12.00"),
            commission_amount=Decimal("600.00"),
            stage=InsurancePolicy.StageChoices.BOUND,
            status=InsurancePolicy.StatusChoices.ACTIVE,
            insurance_type="commercial_auto",
            start_date=date(today.year, today.month, 1),
            end_date=date(today.year, today.month, 28),
            insurance_period_months=6,
            bound_date=date(today.year, today.month, min(12, max(today.day, 1))),
            added_by=self.owner,
        )

    def test_dashboard_aggregates_by_line(self):
        today = date.today()
        dash = build_insurance_targets_dashboard(
            self.org,
            InsurancePolicy.objects.filter(organization=self.org),
            year=today.year,
            month=today.month,
            today=today,
        )
        by_type = {c["insurance_type"]: c for c in dash["line_cards"]}
        self.assertEqual(by_type["auto_personal"]["premium_actual"], Decimal("2000.00"))
        self.assertEqual(by_type["commercial_auto"]["premium_actual"], Decimal("5000.00"))
        self.assertEqual(dash["totals"]["premium_actual"], Decimal("7000.00"))
        self.assertEqual(dash["totals"]["binds"], 2)

    def test_planner_binds_needed(self):
        cards = [
            {
                "insurance_type": "auto_personal",
                "label": "AUTO PERSONAL",
                "premium_gap": Decimal("3000.00"),
                "assumed_premium": Decimal("1500.00"),
                "avg_commission_rate": Decimal("0.10"),
                "is_active": True,
            }
        ]
        plan = planner_recommendations(
            organization=self.org,
            line_cards=cards,
            premium_gap=Decimal("3000.00"),
        )
        self.assertEqual(plan["plays"][0]["binds_needed"], 2)
        self.assertEqual(plan["plays"][0]["premium_impact"], Decimal("3000.00"))

    def test_pace_and_trends_shape(self):
        today = date.today()
        dash = build_insurance_targets_dashboard(
            self.org,
            InsurancePolicy.objects.filter(organization=self.org),
            year=today.year,
            month=today.month,
            today=today,
        )
        InsuranceMonthlyTarget.objects.filter(
            organization=self.org, year=today.year, month=today.month
        ).update(premium_target=Decimal("14000.00"), commission_target=Decimal("1400.00"))
        dash = build_insurance_targets_dashboard(
            self.org,
            InsurancePolicy.objects.filter(organization=self.org),
            year=today.year,
            month=today.month,
            today=today,
        )
        self.assertEqual(dash["premium_pace"]["mtd"], Decimal("7000.00"))
        self.assertEqual(dash["premium_pace"]["target"], Decimal("14000.00"))
        self.assertEqual(dash["premium_pace"]["gap"], Decimal("7000.00"))
        self.assertEqual(len(dash["trends"]), 6)
        self.assertIn("by_lob", dash["trends"][-1])
        self.assertTrue(any(r["insurance_type"] == "auto_personal" for r in dash["trends"][-1]["by_lob"]))

    def test_save_monthly_target_owner_ok_agent_denied(self):
        today = date.today()
        self.http.login(username="tgtowner", password="password123")
        response = self.http.post(
            reverse("save-insurance-monthly-target"),
            {
                "organization_id": self.org.id,
                "year": today.year,
                "month": today.month,
                "premium_target": "10000",
                "commission_target": "1200",
                "line_premium_auto_personal": "4000",
                "line_commission_auto_personal": "400",
                "line_active_auto_personal": "1",
                "next": f"/dashboard/inventory/{self.space.id}/?tab=targets",
            },
        )
        self.assertEqual(response.status_code, 302)
        monthly = InsuranceMonthlyTarget.objects.get(
            organization=self.org, year=today.year, month=today.month
        )
        self.assertEqual(monthly.premium_target, Decimal("10000.00"))
        line = monthly.line_targets.get(insurance_type="auto_personal")
        self.assertEqual(line.premium_target, Decimal("4000.00"))

        self.http.login(username="tgtagent", password="password123")
        denied = self.http.post(
            reverse("save-insurance-monthly-target"),
            {
                "organization_id": self.org.id,
                "year": today.year,
                "month": today.month,
                "premium_target": "1",
            },
        )
        self.assertEqual(denied.status_code, 403)

    def test_owner_api_targets_get(self):
        token = Token.objects.create(user=self.owner)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = api.get(reverse("api-owner-insurance-targets"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("line_cards", payload)
        self.assertIn("planner", payload)
        self.assertTrue(payload.get("can_edit"))
