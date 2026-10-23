from django.contrib.auth.models import User
from django.test import Client as TestClient, TestCase, override_settings
from django.urls import reverse

from core.models import Organization, OrganizationMembership


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class SeasonalThemeScopeTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Spooky PSB", city="NYC", is_halloween_theme_enabled=True)
        self.user = User.objects.create_user(username="spooky", password="password123")
        OrganizationMembership.objects.create(user=self.user, organization=self.org, is_active=True, role="owner")
        self.http = TestClient()

    def test_public_pages_never_load_the_theme(self):
        for name in ("home", "contact", "privacy", "login"):
            response = self.http.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
            self.assertNotContains(response, "halloween.js")
            self.assertNotContains(response, "halloween.css")

    def test_public_pages_stay_plain_when_signed_in(self):
        self.http.login(username="spooky", password="password123")
        response = self.http.get(reverse("contact"))
        self.assertNotContains(response, "halloween.js")

    def test_portal_loads_theme_when_office_enabled_it(self):
        self.http.login(username="spooky", password="password123")
        response = self.http.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "halloween.js")
        self.assertContains(response, 'data-halloween-master="true"')

    def test_portal_stays_plain_when_office_turned_it_off(self):
        Organization.objects.filter(id=self.org.id).update(is_halloween_theme_enabled=False)
        self.http.login(username="spooky", password="password123")
        response = self.http.get(reverse("dashboard"))
        self.assertNotContains(response, "halloween.js")
