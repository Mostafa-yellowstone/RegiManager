from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Client,
    Organization,
    OrganizationMembership,
    ServiceDocument,
    ServiceRecord,
    Vehicle,
)

User = get_user_model()


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class DocumentSearchCRMTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="doc_agent",
            email="doc_agent@example.com",
            password="testpassword123",
            first_name="Jane",
            last_name="Doe",
        )
        self.other_agent = User.objects.create_user(
            username="other_agent",
            email="other_agent@example.com",
            password="testpassword123",
            first_name="Bob",
            last_name="Smith",
        )
        self.org = Organization.objects.create(
            name="Main PSB",
            city="Yonkers",
            state="NY",
            is_active=True,
        )
        self.membership = OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.other_membership = OrganizationMembership.objects.create(
            user=self.other_agent,
            organization=self.org,
            role=OrganizationMembership.Role.AGENT,
            is_active=True,
        )

        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="John",
            last_name="Doe",
            phone_number="9145550100",
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="1HGCR2F83HA123456",
            plate_number="ABC1234",
            make="Honda",
            model="Accord",
            year=2020,
        )
        self.service_record = ServiceRecord.objects.create(
            organization=self.org,
            vehicle=self.vehicle,
            handled_by=self.other_agent,
            client_name="John Doe",
            service_type="title_only",
            receipt_number="RCPT-100200",
        )

        # Create test documents
        self.doc1 = ServiceDocument.objects.create(
            service_record=self.service_record,
            vehicle=self.vehicle,
            document_type="title",
            custom_name="Title Correction Certificate",
            file=SimpleUploadedFile("title_correction_scan.pdf", b"pdf content", content_type="application/pdf"),
        )
        self.doc2 = ServiceDocument.objects.create(
            service_record=self.service_record,
            vehicle=self.vehicle,
            document_type="driver_license",
            custom_name="Standard Driver License",
            file=SimpleUploadedFile("license_front.png", b"png content", content_type="image/png"),
        )

    def test_document_search_dashboard_view_and_chip(self):
        """Dashboard renders search documents action chip and dedicated section."""
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Search Docs CRM")
        self.assertContains(resp, "Documents Search &amp; Operations Filter")

    def test_document_search_crm_page_filters_correction_word(self):
        """Searching 'correction' returns only matching documents with highlights."""
        self.client.force_login(self.user)
        url = reverse("dashboard-documents-search") + "?q=correction"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Title Correction Certificate")
        self.assertContains(resp, "Correction Tag")
        self.assertNotContains(resp, "Standard Driver License")

    def test_document_search_crm_filter_by_agent(self):
        """Filtering by agent narrows results to that handler."""
        self.client.force_login(self.user)
        url = reverse("dashboard-documents-search") + f"?agent={self.other_agent.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bob Smith")
        self.assertContains(resp, "Title Correction Certificate")

    def test_document_search_crm_preserves_query_across_pagination(self):
        """Query parameters are preserved in preserved_query_string for pagination."""
        self.client.force_login(self.user)
        url = reverse("dashboard-documents-search") + "?q=correction&doc_type=title&file_ext=pdf"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        preserved = resp.context["preserved_query_string"]
        self.assertIn("q=correction", preserved)
        self.assertIn("doc_type=title", preserved)
        self.assertIn("file_ext=pdf", preserved)
