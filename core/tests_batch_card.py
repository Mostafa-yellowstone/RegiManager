"""The batch card date grid uses the last year digit, then the month, day, and period."""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.batch_card import batch_card_slots
from core.models import Organization, OrganizationMembership


class BatchCardSlotTests(TestCase):
    def test_2026_puts_6_then_the_date_then_20(self):
        slots = batch_card_slots(datetime.date(2026, 10, 7), "891")
        self.assertEqual(slots["year"], "6")
        self.assertEqual(slots["month"], "10")
        self.assertEqual(slots["day"], "07")
        self.assertEqual(slots["period"], "20")
        self.assertEqual(slots["terminal"], "891")

    def test_terminal_keeps_only_three_digits(self):
        slots = batch_card_slots(datetime.date(1998, 1, 2), "8a912 extra")
        self.assertEqual(slots["year"], "8")
        self.assertEqual(slots["period"], "19")
        self.assertEqual(slots["terminal"], "891")

    def test_short_terminal_leaves_the_later_boxes_blank(self):
        slots = batch_card_slots(datetime.date(2103, 3, 4), "7")
        self.assertEqual(slots["year"], "3")
        self.assertEqual(slots["period"], "21")
        self.assertEqual(slots["terminal"], "7  ")


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class BatchCardPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="batchcard", password="password123")
        self.org = Organization.objects.create(
            name="Xpress Plates",
            business_owner_name="Essam Abdelkhalek",
            city="NYC",
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
        )

    def test_page_shows_the_organization_and_owner(self):
        self.client.login(username="batchcard", password="password123")
        response = self.client.get(reverse("batch-number-card"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Xpress Plates")
        self.assertContains(response, "Essam Abdelkhalek")
        self.assertContains(response, "size: A4 landscape")
        self.assertContains(response, 'id="batchPhone"')
        self.assertContains(response, 'id="linePhoneArea"')
        self.assertContains(response, 'id="linePhoneRest"')
