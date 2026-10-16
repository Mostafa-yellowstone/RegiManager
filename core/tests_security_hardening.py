"""Rate limiting, login lockout, tenant isolation, and safe-redirect regression tests."""

from datetime import date

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client as DjangoClient, RequestFactory, TestCase, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Client, Organization, OrganizationMembership, ServiceRecord, Vehicle
from core.policies import redirect_back
from core.ratelimit import client_ip

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "security-tests"}}
PUBLIC_IP = "93.184.216.34"


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, CACHES=LOCMEM)
class ClientIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_spoofed_forwarded_for_prefix_is_ignored_behind_nginx(self):
        request = self.factory.get(
            "/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR=f"1.2.3.4, {PUBLIC_IP}"
        )
        self.assertEqual(client_ip(request), PUBLIC_IP)

    def test_direct_connection_ignores_forwarded_for(self):
        request = self.factory.get("/", REMOTE_ADDR=PUBLIC_IP, HTTP_X_FORWARDED_FOR="9.9.9.9")
        self.assertEqual(client_ip(request), PUBLIC_IP)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    CACHES=LOCMEM,
    RATE_LIMIT_ENABLED=True,
)
class RateLimitAndLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name="Lockout PSB", city="NYC")
        self.user = User.objects.create_user(username="lockme", password="Correct-Horse-9")
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, role=OrganizationMembership.Role.OWNER, is_active=True
        )

    def tearDown(self):
        cache.clear()

    def _web(self):
        return DjangoClient(REMOTE_ADDR=PUBLIC_IP)

    def test_web_login_locks_after_repeated_failures_even_with_the_right_password(self):
        http = self._web()
        for _ in range(5):
            http.post(reverse("login"), {"username": "lockme", "password": "wrong-pass"})
        response = http.post(reverse("login"), {"username": "lockme", "password": "Correct-Horse-9"})
        self.assertNotIn("_auth_user_id", http.session)
        self.assertIn(response.status_code, {200, 429})

    def test_staff_api_login_locks_out(self):
        api = APIClient(REMOTE_ADDR=PUBLIC_IP)
        for _ in range(5):
            api.post(reverse("api-auth-login"), {"username": "lockme", "password": "nope"}, format="json")
        blocked = api.post(
            reverse("api-auth-login"), {"username": "lockme", "password": "Correct-Horse-9"}, format="json"
        )
        self.assertEqual(blocked.status_code, 429)

    def test_auth_posts_are_rate_limited_per_ip(self):
        http = self._web()
        statuses = [
            http.post(reverse("login"), {"username": f"nobody{i}", "password": "x"}).status_code
            for i in range(12)
        ]
        self.assertIn(429, statuses)

    def test_unknown_visitor_ip_never_shares_one_bucket(self):
        http = DjangoClient(REMOTE_ADDR="127.0.0.1")
        statuses = [
            http.post(reverse("login"), {"username": f"nobody{i}", "password": "x"}).status_code
            for i in range(12)
        ]
        self.assertNotIn(429, statuses)

    def test_password_change_revokes_api_tokens(self):
        Token.objects.create(user=self.user)
        self.user.set_password("Another-Horse-10")
        self.user.save()
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_deactivating_a_user_revokes_api_tokens(self):
        Token.objects.create(user=self.user)
        self.user.is_active = False
        self.user.save()
        self.assertFalse(Token.objects.filter(user=self.user).exists())


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, CACHES=LOCMEM)
class TenantIsolationTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="PSB A", city="NYC")
        self.org_b = Organization.objects.create(name="PSB B", city="NYC")
        self.user_a = User.objects.create_user(username="agent_a", password="password123")
        OrganizationMembership.objects.create(
            user=self.user_a, organization=self.org_a, role=OrganizationMembership.Role.OWNER, is_active=True
        )
        self.client_b = Client.objects.create(
            organization=self.org_b, first_name="Secret", last_name="Victim", phone_number="5550001111"
        )
        self.vehicle_b = Vehicle.objects.create(client=self.client_b, vin="1HGCM82633A004352")
        self.client_a = Client.objects.create(organization=self.org_a, first_name="Own", last_name="Client")

    def test_api_cannot_move_a_client_into_another_psb(self):
        api = APIClient()
        api.force_authenticate(self.user_a)
        response = api.patch(
            f"/api/clients/{self.client_a.id}/", {"organization": self.org_b.id}, format="json"
        )
        self.assertIn(response.status_code, {200, 400})
        self.client_a.refresh_from_db()
        self.assertEqual(self.client_a.organization_id, self.org_a.id)

    def test_api_cannot_attach_another_psbs_vehicle(self):
        api = APIClient()
        api.force_authenticate(self.user_a)
        response = api.post(
            "/api/service-records/",
            {"vehicle": self.vehicle_b.id, "client_name": "x", "service_type": "vehicle_registration"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("vehicle", response.json())

    def test_api_vehicle_list_is_scoped_by_client_psb(self):
        api = APIClient()
        api.force_authenticate(self.user_a)
        response = api.get("/api/vehicles/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.json().get("results", [])]
        self.assertNotIn(self.vehicle_b.id, ids)

    def test_dmv_prefill_does_not_borrow_another_psbs_vehicle_by_vin(self):
        service = ServiceRecord.objects.create(
            organization=self.org_a,
            handled_by=self.user_a,
            client_name="Own Client",
            vin=self.vehicle_b.vin,
            service_type="vehicle_registration",
            transaction_date=date.today(),
        )
        http = DjangoClient()
        http.login(username="agent_a", password="password123")
        response = http.get(reverse("mv82-interactive", args=[service.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Victim")

    def test_deactivated_member_loses_receipt_access(self):
        service = ServiceRecord.objects.create(
            organization=self.org_a,
            handled_by=self.user_a,
            client_name="Own Client",
            service_type="vehicle_registration",
            transaction_date=date.today(),
        )
        OrganizationMembership.objects.filter(user=self.user_a).update(is_active=False)
        http = DjangoClient()
        http.login(username="agent_a", password="password123")
        response = http.get(reverse("service-receipt-pdf", args=[service.id]))
        self.assertEqual(response.status_code, 403)


class RedirectBackTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_query_only_next_returns_to_the_fallback_page(self):
        request = self.factory.post("/x/", {"next": "?tab=targets&target_month=2026-10"})
        response = redirect_back(request, "/dashboard/inventory/1/?tab=targets")
        self.assertEqual(response["Location"], "/dashboard/inventory/1/?tab=targets&target_month=2026-10")

    def test_external_next_is_ignored(self):
        request = self.factory.post("/x/", {"next": "https://evil.example/phish"})
        response = redirect_back(request, "/dashboard/")
        self.assertEqual(response["Location"], "/dashboard/")

    def test_bare_word_next_is_not_reversed_as_a_view_name(self):
        request = self.factory.post("/x/", {"next": "dashboard-but-not-a-url"})
        response = redirect_back(request, "/dashboard/")
        self.assertEqual(response["Location"], "/dashboard/")
