from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.agency_licenses import license_status, parse_reminder_days
from core.models import AgencyLicense, AgencyLicenseFolder, Organization, OrganizationMembership, Space

User = get_user_model()


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class AgencyLicenseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="lic_owner", password="pass")
        self.org = Organization.objects.create(name="Lic Org", city="NYC")
        self.membership = OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
            can_view_spaces=True,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="licenses",
            label="Licenses",
            description="Licenses",
        )
        self.membership.accessible_spaces.add(self.space)
        self.folder = AgencyLicenseFolder.objects.create(
            organization=self.org,
            space=self.space,
            state_code="NY",
            state_name="New York",
        )

    def test_custom_reminder_window(self):
        self.assertEqual(parse_reminder_days("45, 30, 5"), (5, 30, 45))
        lic = AgencyLicense.objects.create(
            organization=self.org,
            space=self.space,
            folder=self.folder,
            title="PSB License",
            expiration_date=timezone.localdate() + timedelta(days=20),
            reminder_days="45,30,5",
        )
        status = license_status(lic)
        self.assertEqual(status["state"], "expiring")
        self.assertEqual(status["milestone"], 30)

    def test_space_page_renders(self):
        self.client.login(username="lic_owner", password="pass")
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add state")
        self.assertContains(response, "New York")
