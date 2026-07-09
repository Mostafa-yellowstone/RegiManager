"""Tests for owner companion API."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from core.models import (
    Client,
    InsuranceCompany,
    InsurancePolicy,
    Notification,
    Organization,
    OrganizationMembership,
    ServiceRecord,
    Space,
)

User = get_user_model()


class OwnerAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Owner PSB", city="Albany", state="NY")
        self.owner = User.objects.create_user(username="owner1", password="pass12345")
        self.agent = User.objects.create_user(username="agent1", password="pass12345")
        self.owner_mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
            can_view_spaces=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.agent,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )
        self.insurance_space = Space.objects.create(
            organization=self.org,
            key="insurance",
            label="Insurance",
        )
        self.owner_mem.accessible_spaces.add(self.insurance_space)
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
        )
        self.company = InsuranceCompany.objects.create(
            organization=self.org,
            name="Test Insurance Co",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent,
            client_name="Jane Doe",
            service_type="registration",
            status="completed",
            service_fee=Decimal("100.00"),
            processing_fee=Decimal("25.00"),
            transaction_date=date.today(),
        )
        self.owner_token = Token.objects.create(user=self.owner)
        self.agent_token = Token.objects.create(user=self.agent)

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_owner_overview_returns_profit_data(self):
        self._auth(self.owner_token)
        response = self.client.get(reverse("api-owner-overview"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("profit", response.data)
        self.assertIn("combined_profit", response.data["profit"])
        self.assertEqual(response.data["profit"]["dmv_core"]["today"]["total_records"], 1)

    def test_agent_without_finance_permission_denied(self):
        self._auth(self.agent_token)
        response = self.client.get(reverse("api-owner-overview"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_finance_compare_requires_months(self):
        self._auth(self.owner_token)
        response = self.client.get(reverse("api-owner-finance-compare"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_finance_compare_returns_deltas(self):
        self._auth(self.owner_token)
        response = self.client.get(
            reverse("api-owner-finance-compare"),
            {"compare_a": "2026-04", "compare_b": "2026-05"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("deltas", response.data)

    def test_policy_bound_notifies_owner(self):
        policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            policy_number="POL-100",
            insurance_company=self.company,
            premium=Decimal("1200.00"),
            commission_rate=Decimal("10.00"),
            start_date=date.today(),
            end_date=date.today().replace(month=12, day=31),
            stage="quote",
            status="pending",
            bound_date=date.today(),
            added_by=self.agent,
        )
        policy.stage = "bound"
        policy.status = "active"
        policy.save()

        self.assertTrue(
            Notification.objects.filter(
                user=self.owner,
                event_type="policy_bound",
                policy=policy,
            ).exists()
        )

    def test_notifications_list_filters_policy_bound(self):
        Notification.objects.create(
            user=self.owner,
            client=self.client_obj,
            organization=self.org,
            event_type="policy_bound",
            title="Policy bound",
            message="Test",
        )
        self._auth(self.owner_token)
        response = self.client.get(
            reverse("api-owner-notifications"),
            {"event_type": "policy_bound"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["notifications"]), 1)

    def test_owner_spaces_list(self):
        self._auth(self.owner_token)
        response = self.client.get(reverse("api-owner-spaces"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["spaces"]), 1)
