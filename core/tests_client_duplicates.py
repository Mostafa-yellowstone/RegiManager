"""Tests for duplicate client detection."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.client_duplicates import (
    find_duplicate_client,
    parse_person_display_name,
    validate_new_client_not_duplicate,
)
from core.client_matching import DuplicateClientError, resolve_client_for_display_name
from core.forms import ClientForm
from core.models import Client, Organization, OrganizationMembership

User = get_user_model()


class ClientDuplicateTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Dup Org", city="NY", state="NY")
        self.user = User.objects.create_user(username="dup_user", password="pass")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

    def test_parse_person_display_name_splits_middle(self):
        self.assertEqual(parse_person_display_name("John A Smith"), ("John", "A", "Smith"))
        self.assertEqual(parse_person_display_name("John Smith"), ("John", "", "Smith"))

    def test_blocks_same_full_name_case_insensitive(self):
        Client.objects.create(
            organization=self.org,
            first_name="bob",
            middle_name="",
            last_name="builder",
            gender="male",
        )
        error = validate_new_client_not_duplicate(
            self.org,
            first_name="Bob",
            middle_name="",
            last_name="Builder",
        )
        self.assertIsNotNone(error)

    def test_allows_same_first_last_different_middle(self):
        Client.objects.create(
            organization=self.org,
            first_name="John",
            middle_name="Ann",
            last_name="Smith",
            gender="male",
        )
        duplicate = find_duplicate_client(
            self.org,
            first_name="John",
            middle_name="",
            last_name="Smith",
        )
        self.assertIsNone(duplicate)

    def test_allows_same_name_different_driver_license(self):
        Client.objects.create(
            organization=self.org,
            first_name="John",
            middle_name="",
            last_name="Smith",
            driver_license="DL111",
            gender="male",
        )
        duplicate = find_duplicate_client(
            self.org,
            first_name="John",
            middle_name="",
            last_name="Smith",
            driver_license="DL222",
        )
        self.assertIsNone(duplicate)

    def test_blocks_same_driver_license(self):
        Client.objects.create(
            organization=self.org,
            first_name="Jane",
            middle_name="",
            last_name="Doe",
            driver_license="dl999",
            gender="female",
        )
        duplicate = find_duplicate_client(
            self.org,
            first_name="Janet",
            middle_name="",
            last_name="Other",
            driver_license="DL999",
        )
        self.assertIsNotNone(duplicate)

    def test_edit_client_allows_same_identity(self):
        client = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            middle_name="Ann",
            last_name="Doe",
            driver_license="DL123",
            gender="female",
        )
        error = validate_new_client_not_duplicate(
            self.org,
            first_name="Jane",
            middle_name="Ann",
            last_name="Doe",
            driver_license="DL123",
            exclude_client_id=client.id,
        )
        self.assertIsNone(error)

    def test_edit_client_form_valid_for_same_name(self):
        client = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            middle_name="Ann",
            last_name="Doe",
            driver_license="DL123",
            gender="female",
            phone_number="5551112222",
            state="NY",
        )
        form = ClientForm(
            {
                "organization": self.org.id,
                "source": "walk-in",
                "first_name": "Jane",
                "middle_name": "Ann",
                "last_name": "Doe",
                "gender": "female",
                "driver_license": "DL123",
                "phone_number": "5551112222",
                "state": "NY",
            },
            instance=client,
            organizations=Organization.objects.filter(id=self.org.id),
        )
        self.assertTrue(form.is_valid())

    def test_insurance_reuses_exact_name_match(self):
        existing = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            middle_name="",
            last_name="Doe",
            gender="female",
        )
        client = resolve_client_for_display_name(self.org, "Jane Doe", source="insurance")
        self.assertEqual(client.id, existing.id)
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)

    def test_insurance_rejects_ambiguous_same_name(self):
        Client.objects.create(
            organization=self.org,
            first_name="John",
            middle_name="",
            last_name="Smith",
            driver_license="DL1",
            gender="male",
        )
        Client.objects.create(
            organization=self.org,
            first_name="John",
            middle_name="",
            last_name="Smith",
            driver_license="DL2",
            gender="male",
        )
        with self.assertRaises(DuplicateClientError):
            resolve_client_for_display_name(self.org, "John Smith", source="insurance")

    def test_check_client_name_ajax_respects_middle_name(self):
        Client.objects.create(
            organization=self.org,
            first_name="John",
            middle_name="Ann",
            last_name="Smith",
            gender="male",
        )
        self.client.login(username="dup_user", password="pass")
        response = self.client.get(
            reverse("check-client-name"),
            {
                "first_name": "John",
                "middle_name": "",
                "last_name": "Smith",
                "org_id": self.org.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["exists"])

        response = self.client.get(
            reverse("check-client-name"),
            {
                "first_name": "John",
                "middle_name": "Ann",
                "last_name": "Smith",
                "org_id": self.org.id,
            },
        )
        self.assertTrue(response.json()["exists"])
