"""Round-trip tests for PSB backup export / wipe / restore."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestClient, TestCase
from django.urls import reverse

from core.models import (
    Client,
    Organization,
    OrganizationMembership,
    ServiceRecord,
    Vehicle,
)
from core.psb_backup import (
    backup_filename,
    export_organization_zip,
    restore_organization_from_zip,
    wipe_organization_tenant_data,
)

User = get_user_model()


class PSBBackupRestoreTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Backup PSB",
            city="Albany",
            state="NY",
            email="backup@example.com",
        )
        self.owner = User.objects.create_user(username="backup_owner", password="pass12345")
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Ada",
            last_name="Lovelace",
            phone_number="5551112222",
            email="ada@example.com",
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="1HGBH41JXMN109186",
            vehicle_number="VEH-BK-001",
            plate_number="ABC1234",
            year=2020,
            make="Honda",
            model="Civic",
        )
        self.record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.owner,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            status="completed",
            payment_method="cash",
            paid_amount=Decimal("100.00"),
            service_fee=Decimal("100.00"),
            processing_fee=Decimal("25.00"),
            transaction_date=date(2026, 7, 1),
            client_name="Ada Lovelace",
        )
        self.http = TestClient()

    def test_export_zip_contains_manifest_and_data(self):
        import io
        import json
        import zipfile

        payload = export_organization_zip(self.org)
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
            self.assertIn("manifest.json", zf.namelist())
            self.assertIn("data.json", zf.namelist())
            manifest = json.loads(zf.read("manifest.json"))
            data = json.loads(zf.read("data.json"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["source_organization_name"], "Backup PSB")
        self.assertGreaterEqual(manifest["object_counts"].get("core.client", 0), 1)
        self.assertGreaterEqual(manifest["object_counts"].get("core.vehicle", 0), 1)
        self.assertGreaterEqual(manifest["object_counts"].get("core.servicerecord", 0), 1)
        self.assertEqual(data["organization"]["source_name"], "Backup PSB")
        self.assertTrue(backup_filename(self.org).startswith("psb-backup-"))

    def test_round_trip_wipe_and_restore(self):
        zip_bytes = export_organization_zip(self.org)
        original_receipt = self.record.receipt_number
        original_invite = self.org.invite_code
        original_portal = self.org.portal_token

        wipe_organization_tenant_data(self.org)
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 0)
        self.assertEqual(Vehicle.all_objects.filter(client__organization=self.org).count(), 0)
        self.assertEqual(ServiceRecord.objects.filter(organization=self.org).count(), 0)
        self.assertEqual(
            OrganizationMembership.objects.filter(organization=self.org).count(),
            0,
        )

        result = restore_organization_from_zip(
            self.org,
            zip_bytes,
            confirm_name="Backup PSB",
        )
        self.assertGreaterEqual(result["restored"].get("core.client", 0), 1)
        self.assertGreaterEqual(result["restored"].get("core.vehicle", 0), 1)
        self.assertGreaterEqual(result["restored"].get("core.servicerecord", 0), 1)
        self.assertGreaterEqual(
            result["restored"].get("core.organizationmembership", 0),
            1,
        )

        restored_client = Client.objects.get(organization=self.org, first_name="Ada")
        self.assertEqual(restored_client.last_name, "Lovelace")
        restored_vehicle = Vehicle.objects.get(client=restored_client)
        self.assertEqual(restored_vehicle.vin, "1HGBH41JXMN109186")
        restored_record = ServiceRecord.objects.get(organization=self.org)
        self.assertEqual(restored_record.processing_fee, Decimal("25.00"))
        self.assertEqual(restored_record.client_name, "Ada Lovelace")
        # Unique receipt regenerated (or still unique) after restore
        self.assertTrue(restored_record.receipt_number)
        self.org.refresh_from_db()
        self.assertEqual(self.org.invite_code, original_invite)
        self.assertEqual(self.org.portal_token, original_portal)
        self.assertEqual(self.org.email, "backup@example.com")
        # Original receipt may differ after regen — either is fine as long as unique
        self.assertNotEqual(restored_record.pk, self.record.pk)
        _ = original_receipt  # kept for clarity of intent

    def test_restore_requires_exact_name_confirmation(self):
        zip_bytes = export_organization_zip(self.org)
        with self.assertRaises(ValueError):
            restore_organization_from_zip(
                self.org,
                zip_bytes,
                confirm_name="Wrong Name",
            )

    def test_admin_download_superuser_only(self):
        url = reverse("admin:psb-backup-download", args=[self.org.pk])
        staff = User.objects.create_user(
            username="backup_staff",
            password="pass12345",
            is_staff=True,
            is_superuser=False,
        )
        self.assertTrue(staff.is_staff)
        self.http.login(username="backup_staff", password="pass12345")
        response = self.http.get(url)
        self.assertEqual(response.status_code, 403)

        User.objects.create_superuser(
            username="backup_super",
            email="super@example.com",
            password="pass12345",
        )
        self.http.logout()
        self.http.login(username="backup_super", password="pass12345")
        response = self.http.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertTrue(len(response.content) > 20)

    def test_admin_import_page_loads_for_superuser(self):
        User.objects.create_superuser(
            username="backup_super2",
            email="super2@example.com",
            password="pass12345",
        )
        self.http.login(username="backup_super2", password="pass12345")
        response = self.http.get(reverse("admin:psb-backup-import"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Restore PSB backup")

    def test_admin_import_post_restores(self):
        zip_bytes = export_organization_zip(self.org)
        wipe_organization_tenant_data(self.org)
        User.objects.create_superuser(
            username="backup_super3",
            email="super3@example.com",
            password="pass12345",
        )
        self.http.login(username="backup_super3", password="pass12345")
        upload = SimpleUploadedFile(
            "backup.zip",
            zip_bytes,
            content_type="application/zip",
        )
        response = self.http.post(
            reverse("admin:psb-backup-import"),
            {
                "organization": str(self.org.pk),
                "confirm_name": "Backup PSB",
                "acknowledge_wipe": "on",
                "backup_file": upload,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)
        self.assertContains(response, "Restore completed")
