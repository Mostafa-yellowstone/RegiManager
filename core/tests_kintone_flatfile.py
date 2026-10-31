import os
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from core.kintone_flatfile_import import (
    FlatfileImporter,
    import_kintone_records,
    start_flatfile_import,
    flatfile_import_status,
)
from core.models import Client, ClientNote, Organization, ServiceDocument, Vehicle

SAMPLE_RECORDS_CSV = """*,"Record_number","Calculated","applicanttype","client_uid","source_dropdown","last","first","middle","Number_0","licenseper","birth_date","Number","build_no","street_ad","apart","city","state","zip","county","email","g_dropdown","business","Number_1","licensecom","Number_2","Text_18","Text_19","Text_20","Text_21","Drop_down_8","Text_22","Drop_down_7","Text_23","Table","Date_and_time","Text_2","Attachment","Text_3","Text","Text_13","Text_15","Text_24","Text_1","Text_0","Created_by","Created_datetime","Updated_by","Updated_datetime","vname","vzip"
*,"3980","4","Personal",,,"CABRERA","DANIEL","ALBINO",,"566019972","1987-08-01","9142479736","158","ELM ST","2","YONKERS","NY","10701","NEW YORK",,"Male",,,,,,,,,,,,,"170846","2022-11-14T14:36:00Z","Daniel intake notes","Attachment-3980\\DANIEL,CABRERA.pdf
Attachment-3980\\CABRERA ALBINO, DANIEL.pdf","CABRERA, DANIEL ALBINO","000004","CABRERA DANIEL ALBINO","566019972","158 ELM ST 2","9142479736",,"essam@multilineins.com","2022-11-14T14:38:00Z","Abigail","2024-11-12T19:02:00Z","DANIEL","10701"
,"3980","4","Personal",,,"CABRERA","DANIEL","ALBINO",,"566019972","1987-08-01","9142479736","158","ELM ST","2","YONKERS","NY","10701","NEW YORK",,"Male",,,,,,,,,,,,,"395646","2024-11-09T19:01:00Z","Daniel intake notes","Attachment-3980\\DANIEL,CABRERA.pdf
Attachment-3980\\CABRERA ALBINO, DANIEL.pdf","CABRERA, DANIEL ALBINO","000004","CABRERA DANIEL ALBINO","566019972","158 ELM ST 2","9142479736",,"essam@multilineins.com","2022-11-14T14:38:00Z","Abigail","2024-11-12T19:02:00Z","DANIEL","10701"
*,"3989","13","Commercial",,,,,,,,,,,,,,"NY",,,,,"ABS LIMO AND CAR SERVICE CORP",,"821839335",,"24","ETHAN ALLEN","CT","ORANGEBURG","NY","10962","ROCKLAND",,"170910","2022-11-14T21:45:00Z",,"Attachment-3989\\ABS LIMO AND CAR SERVICES.pdf","ABS LIMO AND CAR SERVICE CORP","000013","ABS LIMO AND CAR SERVICE CORP","821839335","24 ETHAN ALLEN CT",,,"Yesenia","2022-11-14T21:55:00Z","essam@multilineins.com","2024-09-27T20:19:00Z","ABS LIMO AND CAR SERVICE CORP","10962"
"""


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class KintoneFlatfileImportTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test PSB Office")
        self.user = User.objects.create_superuser("adminuser", "admin@example.com", "password123")
        self.temp_dir = tempfile.TemporaryDirectory()

        # Create sample CSV
        self.csv_path = os.path.join(self.temp_dir.name, "records.csv")
        with open(self.csv_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_RECORDS_CSV)

        # Create attachments directory structure
        self.attachments_dir = os.path.join(self.temp_dir.name, "Attachments")
        sub_3980 = os.path.join(self.attachments_dir, "Attachment-3980")
        sub_3989 = os.path.join(self.attachments_dir, "Attachment-3989")
        os.makedirs(sub_3980, exist_ok=True)
        os.makedirs(sub_3989, exist_ok=True)

        with open(os.path.join(sub_3980, "DANIEL,CABRERA.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 test document 1")
        with open(os.path.join(sub_3980, "CABRERA ALBINO, DANIEL.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 test document 2")
        with open(os.path.join(sub_3989, "ABS LIMO AND CAR SERVICES.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 commercial license doc")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_creates_personal_and_commercial_clients_and_documents(self):
        result = import_kintone_records(
            organization=self.org,
            actor=self.user,
            csv_path=self.csv_path,
            attachments_dir=self.attachments_dir,
        )

        self.assertEqual(result["clients_created"], 2)
        self.assertEqual(result["clients_skipped"], 0)
        self.assertEqual(result["documents_created"], 3)
        # Record 3980 has a subtable row repeating the 2 attachments, which are correctly skipped
        self.assertEqual(result["documents_skipped"], 2)

        # Verify Personal client
        cabrera = Client.objects.get(organization=self.org, driver_license="566019972")
        self.assertEqual(cabrera.first_name, "Daniel")
        self.assertEqual(cabrera.last_name, "Cabrera")
        self.assertEqual(cabrera.middle_name, "Albino")
        self.assertEqual(cabrera.external_key, "566019972")
        self.assertEqual(cabrera.city, "Yonkers")
        self.assertEqual(cabrera.state, "NY")
        self.assertEqual(cabrera.zip_code, "10701")
        self.assertEqual(cabrera.gender, "male")
        self.assertFalse(cabrera.is_commercial)

        # Verify ClientNote
        self.assertTrue(ClientNote.objects.filter(client=cabrera, content="Daniel intake notes").exists())

        # Verify Commercial client
        comm = Client.objects.get(organization=self.org, is_commercial=True)
        self.assertEqual(comm.business_name, "ABS LIMO AND CAR SERVICE CORP")
        self.assertEqual(comm.business_ein, "821839335")
        self.assertEqual(comm.city, "Orangeburg")
        self.assertEqual(comm.state, "NY")
        self.assertEqual(comm.zip_code, "10962")

        # Verify Documents
        cabrera_docs = ServiceDocument.objects.filter(vehicle__client=cabrera)
        self.assertEqual(cabrera_docs.count(), 2)
        comm_docs = ServiceDocument.objects.filter(vehicle__client=comm)
        self.assertEqual(comm_docs.count(), 1)

    def test_reimport_updates_existing_clients_without_duplicates(self):
        # First import
        import_kintone_records(
            organization=self.org,
            actor=self.user,
            csv_path=self.csv_path,
            attachments_dir=self.attachments_dir,
        )
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 2)
        self.assertEqual(ServiceDocument.objects.count(), 3)

        # Second import (same files)
        result2 = import_kintone_records(
            organization=self.org,
            actor=self.user,
            csv_path=self.csv_path,
            attachments_dir=self.attachments_dir,
        )

        # No duplicate clients or documents should be created
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 2)
        self.assertEqual(result2["clients_created"], 0)
        self.assertEqual(result2["clients_skipped"], 2)
        self.assertEqual(result2["documents_created"], 0)
        # All 5 attachment references across the 3 rows are skipped on reimport
        self.assertEqual(result2["documents_skipped"], 5)

    def test_admin_view_get_and_post_server_path(self):
        self.client.force_login(self.user)
        url = reverse("admin:kintone-records-import")

        # GET request
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import Kintone records.csv + Attachments")

        # POST with server path
        post_data = {
            "organization": self.org.id,
            "csv_mode": "server",
            "csv_server_path": self.csv_path,
            "attachments_dir": self.attachments_dir,
        }
        post_response = self.client.post(url, post_data)
        self.assertEqual(post_response.status_code, 302)
        self.assertIn("job=", post_response.url)

        # Extract job_id from redirect url
        job_id = post_response.url.split("job=")[-1]
        status = flatfile_import_status(job_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["status"], "done")
        self.assertEqual(status["results"]["clients_created"], 2)

        # Test JSON status polling endpoint
        json_response = self.client.get(f"{url}?job={job_id}&format=json")
        self.assertEqual(json_response.status_code, 200)
        json_data = json_response.json()
        self.assertEqual(json_data["status"], "done")

    def test_management_command(self):
        call_command(
            "import_kintone_records",
            org_id=self.org.id,
            csv=self.csv_path,
            attachments=self.attachments_dir,
            user_id=self.user.id,
        )
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 2)
        self.assertEqual(ServiceDocument.objects.count(), 3)
