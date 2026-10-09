"""Search still finds a record when the name has extra spaces, and can fall back to a close name."""

from django.contrib.auth.models import User
from django.test import Client as TestClient, TestCase, override_settings
from django.urls import reverse

from core.client_search import search_clients_ranked
from core.models import Client, Organization, OrganizationMembership
from core.text_search import apply_text_search


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class SpaceInsensitiveSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="spacesearch", password="password123")
        self.org = Organization.objects.create(name="Space Search Org", city="NYC")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
        )
        self.client_row = Client.objects.create(
            organization=self.org,
            first_name="Mary  Ann",
            last_name="Smith",
            phone_number="7185552222",
            driver_license="SPACE-DL-1",
            source="walk-in",
        )
        self.http = TestClient()
        self.http.login(username="spacesearch", password="password123")

    def test_extra_spaces_in_the_stored_name_still_match(self):
        found = apply_text_search(
            Client.objects.filter(organization=self.org),
            "Mary Ann",
            ["first_name", "last_name", "business_name"],
        )
        self.assertEqual(list(found), [self.client_row])

    def test_extra_spaces_in_the_query_still_match(self):
        found = search_clients_ranked(Organization.objects.filter(id=self.org.id), "Mary   Ann  Smith")
        self.assertEqual([row.id for row in found], [self.client_row.id])

    def test_dashboard_search_ignores_extra_spaces(self):
        response = self.http.get(reverse("client-search-ajax"), {"q": "Mary Ann Smith"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], self.client_row.id)

    def test_close_spelling_returns_the_nearest_name(self):
        found = search_clients_ranked(Organization.objects.filter(id=self.org.id), "Mery Ann Smith")
        self.assertEqual([row.id for row in found], [self.client_row.id])
