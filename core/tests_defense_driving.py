"""Tests for space important docs and Defense Driving Course space."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestClient
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import (
    Client,
    DefenseDrivingEnrollment,
    DefenseDrivingPackage,
    Organization,
    OrganizationMembership,
    Space,
    SpaceImportantDocument,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    },
)
class SpaceImportantDocsTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Docs Org", city="NYC")
        self.owner = User.objects.create_user(username="docsowner", password="password123")
        self.owner_membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
            can_deal_with_motorclub=True,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="motorclub",
            label="Motor Club",
        )
        self.owner_membership.accessible_spaces.add(self.space)
        self.agent = User.objects.create_user(username="docsagent", password="password123")
        self.agent_membership = OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            is_active=True,
            role="agent",
            can_view_spaces=True,
            can_deal_with_motorclub=False,
        )
        self.agent_membership.accessible_spaces.add(self.space)
        self.client = TestClient()

    def _pdf_file(self, name="contract.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.4 test", content_type="application/pdf")

    def test_owner_can_upload_list_and_delete_docs(self):
        self.client.login(username="docsowner", password="password123")
        response = self.client.post(
            reverse("upload-space-important-document", args=[self.space.id]),
            {
                "title": "Provider Agreement",
                "category": "contract",
                "notes": "Annual renewal",
                "file": self._pdf_file(),
            },
        )
        self.assertEqual(response.status_code, 302)
        doc = SpaceImportantDocument.objects.get(space=self.space)
        self.assertEqual(doc.title, "Provider Agreement")
        self.assertEqual(doc.category, "contract")

        detail = self.client.get(
            reverse("inventory-detail", args=[self.space.id]) + "?tab=documents"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Provider Agreement")
        self.assertContains(detail, "Important Documents")

        delete = self.client.post(
            reverse("delete-space-important-document", args=[doc.id])
        )
        self.assertEqual(delete.status_code, 302)
        self.assertFalse(SpaceImportantDocument.objects.filter(id=doc.id).exists())

    def test_agent_without_permission_cannot_upload(self):
        self.client.login(username="docsagent", password="password123")
        response = self.client.post(
            reverse("upload-space-important-document", args=[self.space.id]),
            {
                "title": "Blocked",
                "category": "other",
                "file": self._pdf_file("blocked.pdf"),
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(SpaceImportantDocument.objects.count(), 0)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    },
)
class DefenseDrivingTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="DDC Org", city="NYC")
        self.owner = User.objects.create_user(username="ddcowner", password="password123")
        self.owner_membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
            can_deal_with_defense_driving=True,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="defense_driving",
            label="Defense Driving Course",
        )
        self.owner_membership.accessible_spaces.add(self.space)
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Safe",
            last_name="Driver",
        )
        self.package = DefenseDrivingPackage.objects.create(
            organization=self.org,
            name="6-Hour Classroom",
            price=Decimal("50.00"),
            provider_take=Decimal("30.00"),
            is_active=True,
            sort_order=10,
        )
        self.agent = User.objects.create_user(username="ddcagent", password="password123")
        self.agent_membership = OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            is_active=True,
            role="agent",
            can_view_spaces=True,
            can_deal_with_defense_driving=False,
        )
        self.agent_membership.accessible_spaces.add(self.space)
        self.client = TestClient()
        self.client.login(username="ddcowner", password="password123")

    def test_spaces_home_creates_defense_driving_space(self):
        response = self.client.get(reverse("spaces-home"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Space.objects.filter(organization=self.org, key="defense_driving").exists()
        )

    def test_defense_driving_space_renders(self):
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Defense Driving")

    def test_enrollment_create_applies_profit_split(self):
        from core.defense_driving_crm import split_profits_for_package

        provider, psb = split_profits_for_package(self.package)
        self.assertEqual(provider, Decimal("30.00"))
        self.assertEqual(psb, Decimal("20.00"))

        response = self.client.post(
            reverse("add-defense-driving-enrollment", args=[self.space.id]),
            {
                "client_id": self.client_obj.id,
                "package_id": self.package.id,
                "channel": "direct",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 302)
        enrollment = DefenseDrivingEnrollment.objects.get(client=self.client_obj)
        self.assertEqual(enrollment.provider_profit, Decimal("30.00"))
        self.assertEqual(enrollment.psb_profit, Decimal("20.00"))
        self.assertTrue(enrollment.enrollment_number.startswith("DDC-"))

    def test_package_update_affects_new_enrollments(self):
        response = self.client.post(
            reverse("save-defense-driving-package", args=[self.space.id]),
            {
                "package_id": self.package.id,
                "name": "6-Hour Classroom",
                "price": "60.00",
                "provider_take": "25.00",
                "sort_order": "10",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.package.refresh_from_db()
        self.assertEqual(self.package.price, Decimal("60.00"))
        self.assertEqual(self.package.provider_take, Decimal("25.00"))

        self.client.post(
            reverse("add-defense-driving-enrollment", args=[self.space.id]),
            {
                "client_id": self.client_obj.id,
                "package_id": self.package.id,
                "channel": "insurance_client",
                "status": "active",
            },
        )
        enrollment = DefenseDrivingEnrollment.objects.get(client=self.client_obj)
        self.assertEqual(enrollment.provider_profit, Decimal("25.00"))
        self.assertEqual(enrollment.psb_profit, Decimal("35.00"))

    def test_agent_without_permission_cannot_mutate(self):
        self.client.logout()
        self.client.login(username="ddcagent", password="password123")
        response = self.client.post(
            reverse("add-defense-driving-enrollment", args=[self.space.id]),
            {
                "client_id": self.client_obj.id,
                "package_id": self.package.id,
                "channel": "direct",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(DefenseDrivingEnrollment.objects.count(), 0)

    def test_client_profile_shows_defense_driving_card(self):
        DefenseDrivingEnrollment.objects.create(
            organization=self.org,
            space=self.space,
            client=self.client_obj,
            package=self.package,
            channel="direct",
            status="active",
            provider_profit=Decimal("30.00"),
            psb_profit=Decimal("20.00"),
            added_by=self.owner,
        )
        response = self.client.get(reverse("client-detail", args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Active Course")
        self.assertContains(response, "6-Hour Classroom")
