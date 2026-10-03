import io
import zipfile
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.kintone_import import import_kintone
from core.models import Client, Organization, ServiceDocument, ServiceRecord, Vehicle
from core.ratelimit import rate_limit

CLIENTS_CSV = """Created datetime,Category,Record number,Name,Unique,Gender,City,Zip,State,Attachments,Phone
"Aug 25, 2026 9:36 AM",Personal,16269,TORRES DENNIS MIGUEL,630858905,Male,BRONX,10458,NY,"TORRES DENNIS M.pdf
MOTORCYCLE REGISTRATION.pdf",6464691374
"""

VEHICLES_CSV = """Record number,Name,Unique,Plate,Year,Model,VIN
20797,TORRES DENNIS MIGUEL,630858905,777BN4,1997,DIO,AF181013518
"""

TRANSACTIONS_CSV = """Record number,Unique,Service,Date,Fee,Plate
55,630858905,Motorcycle Registration,"Aug 25, 2026",25.00,777BN4
"""

DOCUMENTS_CSV = """Record number,Space,Unique,File
289,Inventory Management,630858905,INVENTORY MANAGE - REG DOCS ASSIGNED TO 06C FROM 891.pdf
"""


def csv_file(name, content):
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


def docs_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("TORRES DENNIS M.pdf", b"dl")
        archive.writestr("MOTORCYCLE REGISTRATION.pdf", b"reg")
        archive.writestr("INVENTORY MANAGE - REG DOCS ASSIGNED TO 06C FROM 891.pdf", b"inv")
    return SimpleUploadedFile("docs.zip", buffer.getvalue(), content_type="application/zip")


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class KintoneImportTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Kintone Office")
        self.user = User.objects.create_superuser("kadmin", "k@example.com", "password123")

    def import_bundle(self):
        return import_kintone(
            organization=self.org,
            actor=self.user,
            clients_file=csv_file("clients.csv", CLIENTS_CSV),
            vehicles_file=csv_file("vehicles.csv", VEHICLES_CSV),
            transactions_file=csv_file("transactions.csv", TRANSACTIONS_CSV),
            documents_file=csv_file("documents.csv", DOCUMENTS_CSV),
            documents_zip=docs_zip(),
        )

    def test_import_builds_one_profile_with_vehicle_transaction_and_documents(self):
        result = self.import_bundle()

        self.assertEqual(result["clients_created"], 1)
        self.assertEqual(result["error_count"], 0)
        client = Client.objects.get(organization=self.org)
        self.assertEqual(client.first_name, "Dennis")
        self.assertEqual(client.last_name, "Torres")
        self.assertEqual(client.middle_name, "Miguel")
        self.assertEqual(client.external_key, "630858905")
        self.assertEqual(client.phone_number, "6464691374")
        self.assertEqual(client.city, "Bronx")
        vehicle = Vehicle.objects.get(client=client)
        self.assertEqual(vehicle.vin, "AF181013518")
        self.assertEqual(vehicle.plate_number, "777BN4")
        self.assertEqual(vehicle.year, 1997)
        self.assertEqual(vehicle.model, "DIO")
        self.assertEqual(vehicle.vehicle_type, "motorcycle")
        self.assertTrue(vehicle.is_legacy_vin)
        self.assertEqual(ServiceRecord.objects.filter(vehicle=vehicle).count(), 1)
        self.assertEqual(ServiceDocument.objects.filter(vehicle=vehicle).count(), 3)

    def test_existing_profile_is_skipped(self):
        self.import_bundle()
        again = self.import_bundle()

        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(Vehicle.objects.count(), 1)
        self.assertEqual(ServiceRecord.objects.count(), 1)
        self.assertEqual(ServiceDocument.objects.count(), 3)
        self.assertEqual(again["clients_created"], 0)
        self.assertEqual(again["clients_skipped"], 1)
        self.assertEqual(again["vehicles_created"], 0)
        self.assertEqual(again["vehicles_skipped"], 1)
        self.assertEqual(again["transactions_created"], 0)
        self.assertEqual(again["transactions_skipped"], 1)
        self.assertEqual(again["documents_created"], 0)
        self.assertEqual(again["documents_skipped"], 3)

    def test_same_person_already_in_the_office_is_not_copied(self):
        existing = Client.objects.create(
            organization=self.org,
            first_name="Dennis",
            last_name="Torres",
            phone_number="(646) 469-1374",
            city="Queens",
        )
        result = self.import_bundle()
        existing.refresh_from_db()

        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(result["clients_created"], 0)
        self.assertEqual(result["clients_skipped"], 1)
        self.assertEqual(existing.external_key, "630858905")
        self.assertEqual(existing.city, "Queens")
        self.assertEqual(existing.phone_number, "(646) 469-1374")
        self.assertEqual(existing.vehicles.count(), 1)

    def test_admin_page_explains_the_skip(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:kintone-import"))
        self.assertContains(response, "it is skipped")
        self.assertContains(response, "630858905")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class RateLimitTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def view(self):
        @rate_limit(key_prefix="unit", limit=2, window_seconds=60)
        def endpoint(request):
            return HttpResponse("ok")

        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        return endpoint, request

    def test_blocks_after_the_limit(self):
        endpoint, request = self.view()
        self.assertEqual(endpoint(request).status_code, 200)
        self.assertEqual(endpoint(request).status_code, 200)
        self.assertEqual(endpoint(request).status_code, 429)

    def test_cache_outage_does_not_crash_the_request(self):
        endpoint, request = self.view()
        with patch("core.ratelimit.cache.add", side_effect=ConnectionError("redis down")):
            response = endpoint(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
