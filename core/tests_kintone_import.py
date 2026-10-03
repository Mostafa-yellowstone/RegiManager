import io
import zipfile
from datetime import date
from decimal import Decimal
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

def csv_file(name, content):
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


def docs_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("TORRES DENNIS M.pdf", b"dl")
        archive.writestr("MOTORCYCLE REGISTRATION.pdf", b"reg")
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
        self.assertEqual(ServiceDocument.objects.filter(vehicle=vehicle).count(), 2)
        names = set(ServiceDocument.objects.filter(vehicle=vehicle).values_list("custom_name", flat=True))
        self.assertEqual(names, {"TORRES DENNIS M.pdf", "MOTORCYCLE REGISTRATION.pdf"})

    def test_existing_profile_is_skipped(self):
        self.import_bundle()
        again = self.import_bundle()

        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(Vehicle.objects.count(), 1)
        self.assertEqual(ServiceRecord.objects.count(), 1)
        self.assertEqual(ServiceDocument.objects.count(), 2)
        self.assertEqual(again["clients_created"], 0)
        self.assertEqual(again["clients_skipped"], 1)
        self.assertEqual(again["vehicles_created"], 0)
        self.assertEqual(again["vehicles_skipped"], 1)
        self.assertEqual(again["transactions_created"], 0)
        self.assertEqual(again["transactions_skipped"], 1)
        self.assertEqual(again["documents_created"], 0)
        self.assertEqual(again["documents_skipped"], 2)

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

    def test_zip_of_both_sheets_builds_one_profile(self):
        clients = """Created datetime,client_uid,Applicant Type,Client Number,Date of birth,Client,License Number,Gender,City,ZIP,State,Phone number
8/25/2026 9:36,,Personal,16269,2/10/1994,TORRES DENNIS MIGUEL,630858905,Male,BRONX,10458,NY,6464691374
"""
        vehicles = """VehicleId,Client,License Number,client id,PlateNumber,Year,Model,Color,Weight,Fuel,Cylinders,Body Type,Plate Type,VehicleType,InsuranceCompany,Registration Expiration Date,Registration Effective Date,Insurance Expiration Date,Insurance Effective Date,VIN
20797,TORRES DENNIS MIGUEL,630858905,,777BN4,1997,DIO,,,,,,Motorcycle,,,4/1/2027,4/1/2027,,,AF181013518
"""
        transactions = """Terminal Number,Transaction Date,Client,VIN,SubTotalXpress,SubTotalDMV,Sales Tax,GrandTotal,CC Fees,Payments,Outstanding
999,5/22/2026,TORRES DENNIS M,AF181013518,65,149.38,44.38,214.38,0,214.38,0
"""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("clients.csv", clients)
            archive.writestr("vehicles.csv", vehicles)
            archive.writestr("transactions.csv", transactions)
        bundle = SimpleUploadedFile("kintone.zip", buffer.getvalue(), content_type="application/zip")

        result = import_kintone(organization=self.org, actor=self.user, documents_zip=bundle)

        self.assertEqual(result["error_count"], 0, result["errors"])
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)
        client = Client.objects.get(external_key="630858905")
        self.assertEqual(client.full_display_name, "Dennis Miguel Torres")
        self.assertEqual(client.dob, date(1994, 2, 10))
        self.assertEqual(client.phone_number, "6464691374")
        self.assertEqual(client.vehicles.count(), 1)
        vehicle = client.vehicles.get()
        self.assertEqual(vehicle.plate_number, "777BN4")
        self.assertEqual(vehicle.vin, "AF181013518")
        self.assertEqual(vehicle.year, 1997)
        self.assertEqual(vehicle.model, "DIO")
        self.assertEqual(vehicle.vehicle_type, "motorcycle")
        self.assertEqual(vehicle.vehicle_number, "20797")
        self.assertEqual(str(vehicle.registration_expiration_date), "2027-04-01")
        record = ServiceRecord.objects.get(vehicle=vehicle)
        self.assertEqual(record.transaction_date, date(2026, 5, 22))
        self.assertEqual(record.processing_fee, Decimal("65.00"))
        self.assertEqual(record.dmv_fee, Decimal("149.38"))
        self.assertEqual(record.service_fee, Decimal("214.38"))
        self.assertEqual(record.paid_amount, Decimal("214.38"))
        self.assertEqual(record.terminal_number, "999")
        self.assertEqual(record.vin, "AF181013518")
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)

    def test_admin_page_explains_the_skip(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:kintone-import"))
        self.assertContains(response, "it is skipped")
        self.assertContains(response, "License Number")
        self.assertContains(response, "one zip")


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
