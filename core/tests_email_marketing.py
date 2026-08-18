"""Tests for Email Marketing module."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

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

    def test_render_does_not_wrap_space_letterhead(self):
        org = Organization.objects.create(
            name="Brand PSB",
            city="Albany",
            state="NY",
            email="hello@brand.test",
            phone_number="555-0100",
            insurance_intake_display_name="Xpress Insurance Solutions",
        )
        from core.email_branding import email_brand_for_org

        contact = EmailMarketingContact(
            name="Jane Doe",
            email="jane@example.com",
        )
        html = render_campaign_html(
            "<p>Hello {{name}}</p>",
            "",
            contact,
            brand=email_brand_for_org(org),
            logo_mode="data",
        )
        self.assertIn("Hello Jane Doe", html)
        self.assertNotIn("Xpress Insurance Solutions", html)
        self.assertNotIn("hello@brand.test", html)
        self.assertNotIn("©", html)


class EmailBrandingAttachTests(TestCase):
    def test_invalid_logo_bytes_do_not_raise(self):
        from django.core.mail import EmailMultiAlternatives

        from core.email_branding import attach_brand_logo

        message = EmailMultiAlternatives("Hi", "body", "from@test.com", ["to@test.com"])
        self.assertFalse(attach_brand_logo(message, {"logo_bytes": b"not-an-image"}))

    def test_valid_logo_attaches_and_sends(self):
        from io import BytesIO

        from django import VERSION
        from django.core import mail
        from django.core.mail import EmailMultiAlternatives
        from PIL import Image

        from core.email_branding import LOGO_CID, attach_brand_logo

        buf = BytesIO()
        Image.new("RGB", (8, 8), "#0d9488").save(buf, format="PNG")
        message = EmailMultiAlternatives("Hi", "body", "from@test.com", ["to@test.com"])
        message.attach_alternative(f'<img src="cid:{LOGO_CID}">', "text/html")
        self.assertTrue(attach_brand_logo(message, {"logo_bytes": buf.getvalue()}))
        self.assertEqual(len(message.attachments), 1)
        if VERSION[0] >= 6:
            self.assertNotIn("mixed_subtype", message.__dict__)
        message.send()
        self.assertEqual(len(mail.outbox), 1)


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
            role=OrganizationMembership.Role.AGENT,
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

    def test_create_list_via_home_post(self):
        self.client.login(username="owner", password="pass12345")
        response = self.client.post(
            reverse("email-marketing-home"),
            {"action": "create_list", "name": "Newsletter", "description": "Test", "accent_color": "#2563eb"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EmailMarketingList.objects.filter(name="Newsletter").exists())

    def test_create_duplicate_list_shows_error(self):
        self.client.login(username="owner", password="pass12345")
        url = reverse("email-marketing-home")
        self.client.post(url, {"action": "create_list", "name": "Dup", "accent_color": "#2563eb"})
        response = self.client.post(url, {"action": "create_list", "name": "Dup", "accent_color": "#2563eb"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailMarketingList.objects.filter(name="Dup").count(), 1)

    def test_bulk_assign_creates_a_separate_task_per_contact(self):
        from core.agent_portal_models import AgentTask

        target = User.objects.create_user(username="insagent", password="pass12345")
        target_mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=target,
            role=OrganizationMembership.Role.INSURANCE_AGENT,
            is_active=True,
            can_deal_with_insurance=True,
            can_view_spaces=True,
        )
        first = EmailMarketingContact.objects.create(
            organization=self.org,
            marketing_list=self.list,
            name="Ada Lopez",
            email="ada@test.com",
            phone="555-1111",
            address_line1="10 Pine St",
            city="Albany",
            state="NY",
            zip_code="12207",
            website="https://ada.example",
            notes="Prefers afternoon calls",
        )
        second = EmailMarketingContact.objects.create(
            organization=self.org,
            marketing_list=self.list,
            name="Ben Ortiz",
            email="ben@test.com",
            phone="555-2222",
            city="Troy",
            state="NY",
        )
        self.client.login(username="owner", password="pass12345")
        response = self.client.post(
            reverse("email-marketing-assign-task", args=[self.list.id]),
            {
                "assigned_to": target_mem.id,
                "title": "Follow selected leads",
                "description": "Call each record this week",
                "contact_ids": f"{first.id},{second.id}",
            },
        )
        self.assertEqual(response.status_code, 302)
        tasks = list(AgentTask.objects.filter(assigned_to=target_mem).order_by("id"))
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].title, "Follow selected leads: Ada Lopez")
        self.assertEqual(tasks[1].title, "Follow selected leads: Ben Ortiz")
        self.assertEqual(list(tasks[0].email_marketing_contacts.values_list("name", flat=True)), ["Ada Lopez"])
        self.assertEqual(list(tasks[1].email_marketing_contacts.values_list("name", flat=True)), ["Ben Ortiz"])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.assigned_task_id, tasks[0].id)
        self.assertEqual(second.assigned_task_id, tasks[1].id)
        self.client.login(username="insagent", password="pass12345")
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()
        board = self.client.get(reverse("agent-portal-tasks-board"))
        self.assertEqual(board.status_code, 200)
        self.assertNotContains(board, "Record 1 of 2")
        self.assertContains(board, "Ada Lopez")
        self.assertContains(board, "555-1111")
        self.assertContains(board, "10 Pine St")
        self.assertContains(board, "Prefers afternoon calls")
        self.assertContains(board, "Ben Ortiz")
        self.assertContains(board, "555-2222")
