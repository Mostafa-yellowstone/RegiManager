"""Regression tests for client search ranking and driver-license accuracy."""

from django.contrib.auth.models import User
from django.test import Client as TestClient, TestCase
from django.urls import reverse

from core.client_search import (
    build_full_client_search_q,
    search_clients_ranked,
    serialize_client_search_result,
)
from core.models import Client, Organization, OrganizationMembership, Vehicle


class ClientSearchRankingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="searchrank", password="password123")
        self.org = Organization.objects.create(name="Search Rank Org", city="NYC")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
        )
        self.mercedes = Client.objects.create(
            organization=self.org,
            first_name="Mercedes",
            last_name="Owner",
            phone_number="7185551234",
            driver_license="OLDDL999",
            source="walk-in",
        )
        self.target = Client.objects.create(
            organization=self.org,
            first_name="Correct",
            last_name="Driver",
            phone_number="9175550000",
            driver_license="123456789012",
            source="walk-in",
        )
        Vehicle.objects.create(
            client=self.mercedes,
            vin="MERCEDESVIN000001",
            plate_number="MERC1",
            make="Mercedes-Benz",
        )
        self.http = TestClient()
        self.http.login(username="searchrank", password="password123")

    def test_dashboard_search_by_driver_license_returns_correct_client_first(self):
        response = self.http.get(reverse("client-search-ajax"), {"q": "123456789012"})
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertTrue(results)
        self.assertEqual(results[0]["name"], "Correct Driver")
        self.assertNotEqual(results[0]["name"], "Mercedes Owner")

    def test_dashboard_search_does_not_match_unrelated_phone_substring(self):
        response = self.http.get(reverse("client-search-ajax"), {"q": "5551234"})
        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.json()["results"]]
        self.assertNotIn("Mercedes Owner", names)

    def test_normalized_driver_license_with_dashes_matches_exact_client(self):
        self.target.driver_license = "123-456-789-012"
        self.target.save(update_fields=["driver_license"])
        response = self.http.get(reverse("client-search-ajax"), {"q": "123456789012"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["name"], "Correct Driver")

    def test_all_clients_page_search_by_driver_license(self):
        response = self.http.get(reverse("all-clients"), {"q": "123456789012"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Correct Driver")
        self.assertNotContains(response, "Mercedes Owner")

    def test_search_clients_ranked_prefers_exact_dl_over_name_noise(self):
        ranked = search_clients_ranked(Organization.objects.filter(id=self.org.id), "123456789012")
        self.assertEqual(ranked[0].id, self.target.id)

    def test_build_full_client_search_q_does_not_use_loose_phone_for_dl_digits(self):
        qs = Client.objects.filter(build_full_client_search_q("123456789012"))
        self.assertIn(self.target, qs)
        self.assertNotIn(self.mercedes, qs)

    def test_serialize_client_search_result_uses_driver_license_identifier(self):
        payload = serialize_client_search_result(self.target)
        self.assertEqual(payload["identifier"], "123456789012")
        self.assertIn(str(self.target.id), payload["url"])

    def test_start_process_stays_on_selected_client_vehicle(self):
        vehicle = Vehicle.objects.create(
            client=self.target,
            vin="TARGETVIN000001",
            vehicle_number="VEH-TGT-1",
        )
        response = self.http.post(
            reverse("start-process", args=[vehicle.id]),
            {
                "transaction_date": "2026-06-15",
                "service_type": "vehicle_registration",
                "status": "pending",
                "payment_method": "cash",
                "payment_method_2": "",
                "paid_amount_2": "",
                "terminal_number": "",
                "transaction_type": "OLRS",
                "processing_fee": "100.00",
                "dmv_fee": "0.00",
                "sales_tax": "0.00",
                "dmv_sales_tax": "0.00",
                "credit_card_fee": "0.00",
                "other_fees": "0.00",
                "other_dmv_fee": "0.00",
                "paid_amount": "100.00",
                "referral_balance": "0.00",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        record = vehicle.service_records.latest("id")
        self.assertEqual(record.client_name, "Correct Driver")
        self.assertEqual(record.vehicle_id, vehicle.id)
