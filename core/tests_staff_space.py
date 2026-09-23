"""Tests for Inventory Important Docs, Staff space, and related wiring."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestClient
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import (
    Organization,
    OrganizationMembership,
    Space,
    SpaceImportantDocument,
    StaffDocument,
    StaffEmployee,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class InventoryImportantDocsTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Inv Docs Org", city="NYC")
        self.owner = User.objects.create_user(username="invdocsowner", password="password123")
        self.membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="custom_inventory",
            label="Kimos Spikes",
        )
        self.membership.accessible_spaces.add(self.space)
        self.client = TestClient()
        self.client.login(username="invdocsowner", password="password123")

    def test_inventory_documents_tab_renders_and_upload(self):
        response = self.client.get(
            reverse("inventory-detail", args=[self.space.id]) + "?tab=documents"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Important Documents")
        self.assertNotContains(response, "PSB / DMV License")

        upload = self.client.post(
            reverse("upload-space-important-document", args=[self.space.id]),
            {
                "title": "Vendor Contract",
                "category": "contract",
                "file": SimpleUploadedFile(
                    "vendor.pdf", b"%PDF-1.4 x", content_type="application/pdf"
                ),
            },
        )
        self.assertEqual(upload.status_code, 302)
        self.assertTrue(
            SpaceImportantDocument.objects.filter(
                space=self.space, title="Vendor Contract"
            ).exists()
        )


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class StaffSpaceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Staff Org", city="NYC")
        self.owner = User.objects.create_user(username="staffowner", password="password123")
        self.membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
            can_manage_staff=True,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="staff",
            label="Staff",
        )
        self.membership.accessible_spaces.add(self.space)
        self.agent = User.objects.create_user(username="staffagent", password="password123")
        self.agent_membership = OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            is_active=True,
            role="agent",
            can_view_spaces=True,
            can_manage_staff=False,
        )
        self.agent_membership.accessible_spaces.add(self.space)
        self.client = TestClient()
        self.client.login(username="staffowner", password="password123")

    def test_spaces_home_creates_staff_space(self):
        response = self.client.get(reverse("spaces-home"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Space.objects.filter(organization=self.org, key="staff").exists())

    def test_staff_space_renders(self):
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Team roster")

    def test_create_employee_and_upload_cv(self):
        response = self.client.post(
            reverse("save-staff-employee", args=[self.space.id]),
            {
                "first_name": "Ava",
                "last_name": "Nguyen",
                "email": "ava@example.com",
                "job_title": "Office Manager",
                "department": "Ops",
                "employment_status": "active",
            },
        )
        self.assertEqual(response.status_code, 302)
        employee = StaffEmployee.objects.get(organization=self.org)
        self.assertEqual(employee.full_name, "Ava Nguyen")

        upload = self.client.post(
            reverse("upload-staff-document", args=[employee.id]),
            {
                "title": "CV 2026",
                "category": "cv",
                "file": SimpleUploadedFile(
                    "cv.pdf", b"%PDF-1.4 cv", content_type="application/pdf"
                ),
            },
        )
        self.assertEqual(upload.status_code, 302)
        self.assertTrue(
            StaffDocument.objects.filter(employee=employee, category="cv").exists()
        )

        detail = self.client.get(
            reverse("inventory-detail", args=[self.space.id])
            + f"?tab=directory&employee={employee.id}"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Ava Nguyen")
        self.assertContains(detail, "CV 2026")

    def test_agent_without_permission_cannot_mutate(self):
        self.client.logout()
        self.client.login(username="staffagent", password="password123")
        response = self.client.post(
            reverse("save-staff-employee", args=[self.space.id]),
            {
                "first_name": "Blocked",
                "last_name": "User",
                "employment_status": "active",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(StaffEmployee.objects.count(), 0)
