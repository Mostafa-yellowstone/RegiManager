"""Tests for Email Marketing module."""

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.email_marketing_import import parse_contact_import_file
from core.email_marketing_personalize import render_campaign_html
from core.models import (
    EmailCampaign,
    EmailMarketingContact,
    EmailMarketingList,
    Organization,
    OrganizationMembership,
)

User = get_user_model()


class EmailMarketingPersonalizeTests(TestCase):
    def test_render_replaces_tokens(self):
        contact = EmailMarketingContact(
            name="Jane Doe",
            address_line1="100 Main St",
            city="Albany",
            state="NY",
            email="jane@example.com",
        )
        html = render_campaign_html(
            "<p>Hello {{name}} from {{city}}, {{state}}</p>",
            "p { color: blue; }",
            contact,
        )
        self.assertIn("Jane Doe", html)
        self.assertIn("Albany", html)
        self.assertIn("color: blue", html)


class EmailMarketingImportTests(TestCase):
    def test_csv_import_maps_columns(self):
        content = "name,email,address_line1,city,state\nJohn,john@test.com,1 St,Buffalo,NY\n"
        upload = SimpleUploadedFile("contacts.csv", content.encode("utf-8"), content_type="text/csv")
        rows = parse_contact_import_file(upload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "John")
        self.assertEqual(rows[0]["email"], "john@test.com")
        self.assertEqual(rows[0]["city"], "Buffalo")


@override_settings(DEBUG=True)
class EmailMarketingAccessTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Marketing PSB", city="Albany", state="NY")
        self.owner = User.objects.create_user(username="owner", password="pass12345")
        self.agent = User.objects.create_user(username="agent", password="pass12345")
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.agent_mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.agent,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
            can_manage_email_marketing=True,
        )
        self.list = EmailMarketingList.objects.create(
            organization=self.org,
            name="VIP",
            created_by=self.owner,
        )

    def test_owner_can_open_home(self):
        self.client.login(username="owner", password="pass12345")
        response = self.client.get(reverse("email-marketing-home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email Marketing")

    def test_agent_without_permission_denied(self):
        self.agent_mem.can_manage_email_marketing = False
        self.agent_mem.save()
        self.client.login(username="agent", password="pass12345")
        response = self.client.get(reverse("email-marketing-home"))
        self.assertEqual(response.status_code, 403)

    def test_workspace_crm_tab(self):
        EmailMarketingContact.objects.create(
            organization=self.org,
            marketing_list=self.list,
            name="Contact One",
            email="one@test.com",
        )
        self.client.login(username="owner", password="pass12345")
        url = reverse("email-marketing-workspace", args=[self.list.id])
        response = self.client.get(url + "?tab=crm")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contact One")

    def test_save_campaign(self):
        self.client.login(username="owner", password="pass12345")
        response = self.client.post(
            reverse("email-marketing-save-campaign", args=[self.list.id]),
            {
                "name": "Spring Promo",
                "subject": "Hello {{name}}",
                "html_content": "<p>Hi {{name}}</p>",
                "css_content": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EmailCampaign.objects.filter(name="Spring Promo").exists())
