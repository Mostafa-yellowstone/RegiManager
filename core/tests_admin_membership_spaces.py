from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.admin.organization import MembershipAdminForm
from core.models import Organization, OrganizationMembership, Space


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class MembershipAccessibleSpacesTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Alpha PSB", city="NYC")
        self.org_b = Organization.objects.create(name="Beta PSB", city="NYC")
        self.org_c = Organization.objects.create(name="Gamma PSB", city="NYC")
        self.space_a = Space.objects.create(organization=self.org_a, label="Alpha Insurance", key="insurance")
        self.space_b = Space.objects.create(organization=self.org_b, label="Beta Insurance", key="insurance")
        self.space_c = Space.objects.create(organization=self.org_c, label="Gamma Insurance", key="insurance")
        self.user = User.objects.create_user(username="worker", password="pw12345!")
        self.membership = OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a, role="agent", is_active=True
        )

    def _choices(self, form):
        return set(form.fields["accessible_spaces"].queryset)

    def test_only_spaces_from_the_users_psbs(self):
        self.assertEqual(self._choices(MembershipAdminForm(instance=self.membership)), {self.space_a})

    def test_second_role_adds_that_psbs_spaces(self):
        OrganizationMembership.objects.create(user=self.user, organization=self.org_b, role="agent", is_active=True)
        self.assertEqual(
            self._choices(MembershipAdminForm(instance=self.membership)), {self.space_a, self.space_b}
        )

    def test_inactive_role_elsewhere_does_not_count(self):
        OrganizationMembership.objects.create(user=self.user, organization=self.org_c, role="agent", is_active=False)
        self.assertNotIn(self.space_c, self._choices(MembershipAdminForm(instance=self.membership)))

    def test_new_membership_lists_nothing_until_psb_and_user_chosen(self):
        self.assertEqual(self._choices(MembershipAdminForm()), set())

    def test_posting_another_psbs_space_is_rejected(self):
        form = MembershipAdminForm(
            data={
                "organization": self.org_a.id,
                "user": self.user.id,
                "role": "agent",
                "is_active": "on",
                "accessible_spaces": [self.space_c.id],
            },
            instance=self.membership,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("accessible_spaces", form.errors)

    def test_admin_change_page_hides_other_psbs(self):
        admin = User.objects.create_superuser(username="root", password="pw12345!", email="r@x.com")
        self.client.force_login(admin)
        response = self.client.get(
            reverse("admin:core_organizationmembership_change", args=[self.membership.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Insurance")
        self.assertNotContains(response, "Beta Insurance")
        self.assertNotContains(response, "Gamma Insurance")
