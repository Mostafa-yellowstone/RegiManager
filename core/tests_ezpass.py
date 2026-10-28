"""Comprehensive test suite for the E-ZPass space, operations, trackers, documents, and receipts."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestClient
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import (
    EZPassBatch,
    EZPassTag,
    InventoryInvoice,
    InventoryProduct,
    Organization,
    OrganizationMembership,
    Space,
)
from core.inventory_spaces import ensure_inventory_space, grant_space_to_owners


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class EZPassOperationsTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="YellowStone Motors", city="Brooklyn")
        self.owner = User.objects.create_user(username="ezpass_owner", password="password123")
        self.membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
        )
        self.space = ensure_inventory_space(
            self.org,
            key="ezpass",
            label="E-ZPass",
            description="E-ZPass On-The-Go tags, sales, and stock",
        )
        grant_space_to_owners(self.org, self.space)
        self.client = TestClient()
        self.client.login(username="ezpass_owner", password="password123")

    def test_ezpass_desk_renders_with_zero_tags_low_stock_reminder(self):
        """When 0 tags exist, space renders with low-stock alert and profit summary."""
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E-ZPass")
        self.assertContains(response, "Total Inventory Value")
        self.assertContains(response, "LOW STOCK")
        self.assertContains(response, "Transponder Tracker")
        self.assertContains(response, "Receive Tag Shipment")

    def test_batch_intake_creates_tags_and_stores_manifest_document(self):
        """Batch intake with range entry creates sequential tags and saves attached manifest file."""
        fake_manifest = SimpleUploadedFile(
            "thruway_packing_slip.pdf",
            b"%PDF-1.4 Fake Manifest for Box of 50 E-ZPass tags",
            content_type="application/pdf",
        )
        response = self.client.post(
            reverse("batch-intake-ezpass", args=[self.space.id]),
            {
                "batch_number": "EZB-20261028-01",
                "supplier_name": "NYS Thruway Authority",
                "received_date": "2026-10-28",
                "tag_type": "interior",
                "unit_cost": "25.00",
                "toll_deposit": "25.00",
                "retail_price": "35.00",
                "entry_mode": "range",
                "tag_prefix": "004",
                "range_start": "1001",
                "range_end": "1015",
                "notes": "Delivered in sealed carton via UPS",
                "document": fake_manifest,
            },
        )
        self.assertEqual(response.status_code, 302)

        # 15 tags should be created (1001 to 1015)
        self.assertEqual(EZPassTag.objects.filter(space=self.space).count(), 15)
        batch = EZPassBatch.objects.get(space=self.space, batch_number="EZB-20261028-01")
        self.assertEqual(batch.quantity, 15)
        self.assertEqual(batch.total_cost, Decimal("375.00"))
        self.assertTrue(batch.document)
        self.assertIn("thruway_packing_slip", batch.document_name)

        # Check tag details
        tag_first = EZPassTag.objects.get(space=self.space, tag_number="0041001")
        self.assertEqual(tag_first.status, EZPassTag.Status.IN_STOCK)
        self.assertEqual(tag_first.profit, Decimal("10.00"))

        # Verify manifest download
        doc_resp = self.client.get(reverse("ezpass-batch-document-download", args=[batch.id]))
        self.assertEqual(doc_resp.status_code, 200)

    def test_issue_ezpass_tag_creates_invoice_and_deducts_stock(self):
        """Issuing a tag marks it as sold, records vehicle plate, creates invoice, and yields profit."""
        tag = EZPassTag.objects.create(
            organization=self.org,
            space=self.space,
            tag_number="0049999001",
            tag_type=EZPassTag.TagType.INTERIOR,
            status=EZPassTag.Status.IN_STOCK,
            cost_price=Decimal("25.00"),
            retail_price=Decimal("35.00"),
            toll_deposit=Decimal("25.00"),
            convenience_fee=Decimal("10.00"),
        )
        self.assertTrue(tag.is_in_stock)

        response = self.client.post(
            reverse("issue-ezpass-tag", args=[self.space.id]),
            {
                "tag_id": tag.id,
                "customer_name": "Salim Al-Mansoor",
                "customer_phone": "(718) 555-4321",
                "customer_email": "salim@example.com",
                "plate_number": "JHG4567",
                "plate_state": "NY",
                "vehicle_year": "2023",
                "vehicle_make": "Toyota",
                "vehicle_model": "RAV4",
                "toll_deposit": "25.00",
                "convenience_fee": "10.00",
                "retail_price": "35.00",
                "payment_method": "cash",
                "print_receipt": "0",
            },
        )
        self.assertEqual(response.status_code, 302)

        tag.refresh_from_db()
        self.assertEqual(tag.status, EZPassTag.Status.SOLD)
        self.assertEqual(tag.customer_name, "Salim Al-Mansoor")
        self.assertEqual(tag.plate_number, "JHG4567")
        self.assertEqual(tag.plate_state, "NY")
        self.assertIsNotNone(tag.assigned_at)
        self.assertIsNotNone(tag.invoice)

        # Invoice check
        inv = tag.invoice
        self.assertEqual(inv.total, Decimal("35.00"))
        self.assertIn("JHG4567", inv.notes)

    def test_ezpass_printable_receipt_and_pdf(self):
        """Printable HTML receipt and downloadable PDF receipt render properly."""
        tag = EZPassTag.objects.create(
            organization=self.org,
            space=self.space,
            tag_number="0048888002",
            tag_type=EZPassTag.TagType.INTERIOR,
            status=EZPassTag.Status.SOLD,
            customer_name="Maria Gonzalez",
            customer_phone="(917) 555-8899",
            plate_number="KRT9988",
            plate_state="NY",
            vehicle_year="2022",
            vehicle_make="Honda",
            vehicle_model="Civic",
            cost_price=Decimal("25.00"),
            retail_price=Decimal("40.00"),
            toll_deposit=Decimal("25.00"),
            convenience_fee=Decimal("15.00"),
        )
        # HTML Receipt View
        receipt_resp = self.client.get(reverse("ezpass-receipt-view", args=[tag.id]))
        self.assertEqual(receipt_resp.status_code, 200)
        self.assertContains(receipt_resp, "0048888002")
        self.assertContains(receipt_resp, "Maria Gonzalez")
        self.assertContains(receipt_resp, "KRT9988")
        self.assertContains(receipt_resp, "E-ZPass Service Receipt")
        self.assertContains(receipt_resp, "Our Services")

        # PDF Receipt View
        pdf_resp = self.client.get(reverse("ezpass-receipt-pdf", args=[tag.id]))
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp["Content-Type"], "application/pdf")
        self.assertIn("inline", pdf_resp["Content-Disposition"])

    def test_status_update_and_rma(self):
        """Agents can mark a tag as defective for RMA return to toll authority."""
        tag = EZPassTag.objects.create(
            organization=self.org,
            space=self.space,
            tag_number="0047777003",
            status=EZPassTag.Status.IN_STOCK,
        )
        response = self.client.post(
            reverse("update-ezpass-tag-status", args=[tag.id]),
            {
                "status": "defective",
                "reason": "Battery dead / non-responsive at toll plaza",
            },
        )
        self.assertEqual(response.status_code, 302)
        tag.refresh_from_db()
        self.assertEqual(tag.status, EZPassTag.Status.DEFECTIVE)
        self.assertIn("Battery dead", tag.notes)

    def test_export_ezpass_csv(self):
        """CSV export returns all tag tracking and profit columns."""
        EZPassTag.objects.create(
            organization=self.org,
            space=self.space,
            tag_number="0046666004",
            customer_name="David Miller",
            plate_number="ABC1234",
            cost_price=Decimal("25.00"),
            retail_price=Decimal("35.00"),
            status=EZPassTag.Status.SOLD,
        )
        csv_resp = self.client.get(reverse("export-ezpass-csv", args=[self.space.id]))
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp["Content-Type"], "text/csv")
        self.assertContains(csv_resp, "0046666004")
        self.assertContains(csv_resp, "David Miller")
        self.assertContains(csv_resp, "ABC1234")
        self.assertContains(csv_resp, "Net Profit")
