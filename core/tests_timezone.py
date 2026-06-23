import json

from django.contrib.auth.models import User
from django.test import Client as TestClient, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from core.context_processors import portal_timezone
from core.middleware import PortalTimezoneMiddleware
from core.models import Organization, OrganizationMembership
from core.timezone_utils import (
    is_valid_timezone,
    resolve_portal_timezone_name,
    state_to_timezone_name,
    timezone_label,
)


class TimezoneUtilsTests(TestCase):
    def test_state_to_timezone_name_maps_us_regions(self):
        self.assertEqual(state_to_timezone_name("NY"), "America/New_York")
        self.assertEqual(state_to_timezone_name("CA"), "America/Los_Angeles")
        self.assertEqual(state_to_timezone_name("TX"), "America/Chicago")
        self.assertEqual(state_to_timezone_name("CO"), "America/Denver")
        self.assertEqual(state_to_timezone_name("AZ"), "America/Phoenix")
        self.assertEqual(state_to_timezone_name("AK"), "America/Anchorage")
        self.assertEqual(state_to_timezone_name("HI"), "Pacific/Honolulu")

    def test_is_valid_timezone(self):
        self.assertTrue(is_valid_timezone("America/New_York"))
        self.assertFalse(is_valid_timezone("Not/A/Timezone"))
        self.assertFalse(is_valid_timezone(""))

    def test_resolve_portal_timezone_prefers_session(self):
        org = Organization.objects.create(name="CA Org", city="LA", state="CA")
        self.assertEqual(
            resolve_portal_timezone_name(
                session_timezone="America/Chicago",
                organization=org,
            ),
            "America/Chicago",
        )

    def test_resolve_portal_timezone_falls_back_to_org_state(self):
        org = Organization.objects.create(name="CA Org", city="LA", state="CA")
        self.assertEqual(
            resolve_portal_timezone_name(organization=org),
            "America/Los_Angeles",
        )

    def test_timezone_label_returns_abbreviation(self):
        label = timezone_label("America/New_York")
        self.assertIn(label, {"EST", "EDT"})


class PortalTimezoneMiddlewareTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tzuser", password="password123")
        self.org = Organization.objects.create(name="NY Org", city="NYC", state="NY")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
        )
        self.factory = RequestFactory()

    def _run_middleware(self, request):
        captured = {}

        def get_response(req):
            captured["tz"] = timezone.get_current_timezone_name()
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = PortalTimezoneMiddleware(get_response)
        middleware(request)
        return captured.get("tz")

    def test_middleware_uses_session_timezone(self):
        request = self.factory.get("/dashboard/")
        request.user = self.user
        request.session = self.client.session
        session = self.client.session
        session["portal_timezone"] = "America/Los_Angeles"
        session.save()
        request.session = session

        self.assertEqual(self._run_middleware(request), "America/Los_Angeles")

    def test_middleware_uses_org_state_when_no_session(self):
        request = self.factory.get("/dashboard/")
        request.user = self.user
        request.session = self.client.session

        self.assertEqual(self._run_middleware(request), "America/New_York")


class SetPortalTimezoneViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tzuser", password="password123")
        self.client = TestClient()
        self.client.login(username="tzuser", password="password123")

    def test_set_portal_timezone_stores_valid_timezone(self):
        response = self.client.post(
            reverse("set-portal-timezone"),
            data=json.dumps({"timezone": "America/Chicago"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["timezone"], "America/Chicago")
        self.assertEqual(self.client.session["portal_timezone"], "America/Chicago")

    def test_set_portal_timezone_rejects_invalid_timezone(self):
        response = self.client.post(
            reverse("set-portal-timezone"),
            data=json.dumps({"timezone": "Invalid/Zone"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class PortalTimezoneContextProcessorTests(TestCase):
    def test_context_processor_includes_label_for_authenticated_user(self):
        user = User.objects.create_user(username="ctxuser", password="password123")
        request = RequestFactory().get("/")
        request.user = user

        with timezone.override("America/Chicago"):
            ctx = portal_timezone(request)

        self.assertEqual(ctx["portal_timezone_name"], "America/Chicago")
        self.assertIn(ctx["portal_timezone_label"], {"CST", "CDT"})

    def test_context_processor_empty_for_anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser

        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        self.assertEqual(portal_timezone(request), {})
