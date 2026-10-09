from django.contrib.auth.models import User
from django.test import Client as TestClient
from django.test import TestCase, override_settings
from django.urls import reverse

from core.directory_models import DirectoryCredential, DirectoryEntry, DirectoryPhone
from core.models import Organization, OrganizationMembership, Space


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class DirectorySpaceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Directory Org", city="NYC")
        self.owner = User.objects.create_user(username="dirowner", password="password123")
        self.membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
        )
        self.client = TestClient()
        self.client.login(username="dirowner", password="password123")

    def test_spaces_home_creates_directory_for_owner(self):
        response = self.client.get(reverse("spaces-home"))
        self.assertEqual(response.status_code, 200)
        space = Space.objects.get(organization=self.org, key="directory")
        self.assertContains(response, "Directory")
        self.assertTrue(self.membership.accessible_spaces.filter(id=space.id).exists())

    def test_owner_can_save_company_phone_and_login(self):
        space = Space.objects.create(organization=self.org, key="directory", label="Directory")
        self.membership.accessible_spaces.add(space)

        saved = self.client.post(
            reverse("save-directory-entry", args=[space.id]),
            {
                "name": "Acme Carrier",
                "kind": "company",
                "category": "Carrier",
                "website": "acme.example",
                "portal_url": "https://portal.acme.example",
                "email": "desk@acme.example",
            },
        )
        entry = DirectoryEntry.objects.get(space=space, name="Acme Carrier")
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(entry.website, "https://acme.example")

        phone = self.client.post(
            reverse("save-directory-phone", args=[space.id]),
            {"entry_id": entry.id, "label": "Claims", "number": "718-555-0100", "extension": "12"},
        )
        self.assertEqual(phone.status_code, 302)
        self.assertTrue(DirectoryPhone.objects.filter(entry=entry, label="Claims").exists())

        login = self.client.post(
            reverse("save-directory-credential", args=[space.id]),
            {
                "entry_id": entry.id,
                "label": "Gmail",
                "username": "desk@gmail.com",
                "secret": "office-secret",
                "login_url": "https://mail.google.com",
            },
        )
        self.assertEqual(login.status_code, 302)
        self.assertTrue(
            DirectoryCredential.objects.filter(entry=entry, username="desk@gmail.com", secret="office-secret").exists()
        )

        listing = self.client.get(reverse("inventory-detail", args=[space.id]))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Acme Carrier")
        self.assertContains(listing, "Claims")
        self.assertNotContains(listing, "office-secret")

        detail = self.client.get(reverse("inventory-detail", args=[space.id]) + f"?entry={entry.id}")
        self.assertContains(detail, "desk@gmail.com")
        self.assertContains(detail, "office-secret")

    def test_shared_account_kind_and_agent_without_access_is_denied(self):
        space = Space.objects.create(organization=self.org, key="directory", label="Directory")
        self.membership.accessible_spaces.add(space)
        self.client.post(
            reverse("save-directory-entry", args=[space.id]),
            {"name": "Office Gmail", "kind": "shared_account", "email": "office@gmail.com"},
        )
        self.assertEqual(
            DirectoryEntry.objects.get(name="Office Gmail").kind,
            DirectoryEntry.Kind.SHARED_ACCOUNT,
        )

        agent = User.objects.create_user(username="diragent", password="password123")
        OrganizationMembership.objects.create(
            user=agent,
            organization=self.org,
            is_active=True,
            role="agent",
            can_view_spaces=True,
        )
        agent_client = TestClient()
        agent_client.login(username="diragent", password="password123")
        denied = agent_client.get(reverse("inventory-detail", args=[space.id]))
        self.assertEqual(denied.status_code, 403)
