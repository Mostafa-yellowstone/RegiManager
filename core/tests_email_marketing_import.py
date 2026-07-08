"""Tests for Email Marketing import column matching."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.email_marketing_import import (
    build_column_mapping,
    parse_contact_import_file,
)


class EmailMarketingImportTests(TestCase):
    def test_csv_import_maps_columns(self):
        content = "name,email,address_line1,city,state\nJohn,john@test.com,1 St,Buffalo,NY\n"
        upload = SimpleUploadedFile("contacts.csv", content.encode("utf-8"), content_type="text/csv")
        result = parse_contact_import_file(upload)
        self.assertEqual(len(result.contacts), 1)
        self.assertEqual(result.contacts[0]["name"], "John")
        self.assertEqual(result.contacts[0]["email"], "john@test.com")
        self.assertEqual(result.contacts[0]["city"], "Buffalo")

    def test_fuzzy_header_names(self):
        content = (
            "Full Name,E-Mail Address,Phone Number,Street Address,City,State,ZIP\n"
            "Jane Doe,jane@example.com,5185550100,100 Main St,Albany,NY,12207\n"
        )
        upload = SimpleUploadedFile("contacts.csv", content.encode("utf-8"), content_type="text/csv")
        result = parse_contact_import_file(upload)
        self.assertEqual(len(result.contacts), 1)
        self.assertEqual(result.contacts[0]["name"], "Jane Doe")
        self.assertEqual(result.contacts[0]["email"], "jane@example.com")
        self.assertEqual(result.contacts[0]["phone"], "5185550100")
        self.assertEqual(result.contacts[0]["address_line1"], "100 Main St")
        self.assertEqual(result.contacts[0]["zip_code"], "12207")

    def test_first_and_last_name_columns(self):
        content = "First Name,Last Name,Email\nBob,Smith,bob@test.com\n"
        upload = SimpleUploadedFile("contacts.csv", content.encode("utf-8"), content_type="text/csv")
        result = parse_contact_import_file(upload)
        self.assertEqual(len(result.contacts), 1)
        self.assertEqual(result.contacts[0]["name"], "Bob Smith")

    def test_missing_columns_still_imports(self):
        content = "Customer,Mail\nAcme Co,info@acme.com\n"
        upload = SimpleUploadedFile("contacts.csv", content.encode("utf-8"), content_type="text/csv")
        result = parse_contact_import_file(upload)
        self.assertEqual(len(result.contacts), 1)
        self.assertEqual(result.contacts[0]["name"], "Acme Co")
        self.assertEqual(result.contacts[0]["email"], "info@acme.com")

    def test_semicolon_delimited_csv(self):
        content = "name;email\nSam;sam@test.com\n"
        upload = SimpleUploadedFile("contacts.csv", content.encode("utf-8"), content_type="text/csv")
        result = parse_contact_import_file(upload)
        self.assertEqual(len(result.contacts), 1)
        self.assertEqual(result.contacts[0]["email"], "sam@test.com")

    def test_build_column_mapping_fuzzy(self):
        mapping = build_column_mapping(["Full Name", "E-mail", "Mobile Phone", "Unknown Col"])
        self.assertEqual(mapping["Full Name"], "name")
        self.assertEqual(mapping["E-mail"], "email")
        self.assertEqual(mapping["Mobile Phone"], "phone")
        self.assertNotIn("Unknown Col", mapping)

    def test_xlsx_import(self):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["Contact Name", "Email Address", "Cell"])
        ws.append(["Excel User", "excel@test.com", "5559990000"])
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        upload = SimpleUploadedFile(
            "contacts.xlsx",
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        result = parse_contact_import_file(upload)
        self.assertEqual(len(result.contacts), 1)
        self.assertEqual(result.contacts[0]["name"], "Excel User")
        self.assertEqual(result.contacts[0]["phone"], "5559990000")
