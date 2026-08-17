"""Tests for email campaign delivery dispatch."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from core.email_marketing_tasks import (
    dispatch_email_campaign_batch,
    email_delivery_configured,
    execute_email_campaign_batch,
)
from core.models import (
    EmailCampaign,
    EmailCampaignBatch,
    EmailCampaignRecipient,
    EmailMarketingContact,
    EmailMarketingList,
    Organization,
    OrganizationMembership,
)

User = get_user_model()


@override_settings(
    DEBUG=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="RegiManager <test@example.com>",
    EMAIL_HOST_USER="test@example.com",
    CELERY_TASK_ALWAYS_EAGER=True,
)
class EmailCampaignDeliveryTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Mail PSB", city="Albany", state="NY", email="psb@example.com")
        self.user = User.objects.create_user(username="owner", password="pass12345")
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.marketing_list = EmailMarketingList.objects.create(
            organization=self.org,
            name="List",
            created_by=self.user,
        )
        self.contact = EmailMarketingContact.objects.create(
            organization=self.org,
            marketing_list=self.marketing_list,
            name="Jane",
            email="jane@example.com",
        )
        self.campaign = EmailCampaign.objects.create(
            organization=self.org,
            marketing_list=self.marketing_list,
            name="Welcome",
            subject="Hello {{name}}",
            html_content="<p>Hi {{name}}</p>",
            created_by=self.user,
        )
        self.batch = EmailCampaignBatch.objects.create(
            campaign=self.campaign,
            sent_by=self.user,
            recipient_count=1,
        )
        EmailCampaignRecipient.objects.create(
            batch=self.batch,
            campaign=self.campaign,
            contact=self.contact,
            email=self.contact.email,
        )

    def test_email_delivery_configured(self):
        self.assertTrue(email_delivery_configured())

    def test_execute_sends_and_updates_counts(self):
        result = execute_email_campaign_batch(self.batch.id)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jane@example.com"])
        self.assertIn("Jane", mail.outbox[0].subject)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("Mail PSB", html)
        self.assertIn("RegiManager", html)
        self.assertIn("©", html)

        self.batch.refresh_from_db()
        self.assertEqual(self.batch.sent_count, 1)
        recipient = self.batch.recipient_logs.get()
        self.assertEqual(recipient.status, EmailCampaignRecipient.Status.SENT)

    @patch("core.email_marketing_tasks._celery_workers_available", return_value=False)
    def test_dispatch_without_worker_sends_immediately(self, _workers):
        mail.outbox.clear()
        status = dispatch_email_campaign_batch(self.batch.id)
        self.assertEqual(status, "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.sent_count, 1)
