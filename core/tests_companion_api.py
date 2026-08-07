"""Tests for companion app authentication API."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from core.models import Organization, OrganizationMembership

User = get_user_model()


class CompanionAuthAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test PSB", city="Albany", state="NY")
        self.user = User.objects.create_user(username="agent1", password="pass12345")
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            role=OrganizationMembership.Role.AGENT,
            is_active=True,
            can_manage_email_marketing=True,
        )
        self.login_url = reverse("api-auth-login")
        self.me_url = reverse("api-auth-me")
        self.logout_url = reverse("api-auth-logout")

    def test_login_returns_token_and_organizations(self):
        response = self.client.post(
            self.login_url,
            {"username": "agent1", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["user"]["username"], "agent1")
        self.assertEqual(len(response.data["organizations"]), 1)
        self.assertEqual(response.data["organizations"][0]["name"], "Test PSB")
        self.assertTrue(response.data["organizations"][0]["permissions"]["can_manage_email_marketing"])

    def test_login_invalid_credentials(self):
        response = self.client.post(
            self.login_url,
            {"username": "agent1", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_without_membership_forbidden(self):
        User.objects.create_user(username="orphan", password="pass12345")
        response = self.client.post(
            self.login_url,
            {"username": "orphan", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_me_requires_authentication(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_token(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["username"], "agent1")
        self.assertEqual(len(response.data["organizations"]), 1)
        self.assertIn("server_time", response.data)

    def test_logout_revokes_token(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_clients_list_with_token(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/api/clients/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
