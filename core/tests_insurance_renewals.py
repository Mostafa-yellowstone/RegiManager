from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.insurance_producers import add_months
from core.insurance_renewals import reminder_due, renewal_history, sync_renewals, today_board
from core.models import (
    Client,
    DailyPaymentTransaction,
    InsuranceCompany,
    InsurancePolicy,
    InsurancePolicyInstallment,
    InsurancePolicyVehicle,
    InsuranceRenewal,
    InsuranceRenewalSettings,
    Organization,
    OrganizationMembership,
    Space,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class RenewalBase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.org = Organization.objects.create(name="Renew Org", city="NYC", phone_number="7185550100")
        Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        self.owner = User.objects.create_user(username="rn-owner", password="x", first_name="Olga", last_name="Owner")
        self.agent = User.objects.create_user(username="rn-agent", password="x", first_name="Adam", last_name="Agent")
        self.other_agent = User.objects.create_user(username="rn-agent2", password="x")
        OrganizationMembership.objects.create(
            user=self.owner, organization=self.org, role=OrganizationMembership.Role.OWNER, is_active=True,
            can_use_insurance=True,
        )
        for user in (self.agent, self.other_agent):
            OrganizationMembership.objects.create(
                user=user, organization=self.org, role=OrganizationMembership.Role.AGENT, is_active=True,
                can_use_insurance=True,
            )
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Acme Mutual")
        self.other_company = InsuranceCompany.objects.create(organization=self.org, name="Beta Insurance")
        self.customer = Client.objects.create(
            organization=self.org, first_name="mia", last_name="Stone", email="mia@example.com", phone_number="(718) 555-0199"
        )

    def policy(self, number="P-1", *, days=20, added_by=None, stage="bound", status="active", **extra):
        end = self.today + timedelta(days=days)
        start = add_months(end, -6)
        return InsurancePolicy.objects.create(
            organization=self.org,
            client=extra.pop("client", self.customer),
            policy_number=number,
            insurance_company=extra.pop("company", self.company),
            premium=extra.pop("premium", Decimal("1200.00")),
            commission_rate=Decimal("10"),
            start_date=start,
            end_date=end,
            bound_date=start,
            stage=stage,
            status=status,
            added_by=added_by or self.agent,
            insurance_period_months=6,
            **extra,
        )


class SyncTests(RenewalBase):
    def test_cards_only_for_bound_active_policies_inside_the_window(self):
        due = self.policy("DUE", days=20)
        self.policy("FAR", days=90)
        self.policy("QUOTE", days=10, stage="quote")
        self.policy("GONE", days=10, status="inactive")
        self.policy("OLD", days=-45)
        expired_recently = self.policy("LATE", days=-5)

        sync_renewals(self.org, today=self.today)

        numbers = set(InsuranceRenewal.objects.values_list("policy__policy_number", flat=True))
        self.assertEqual(numbers, {"DUE", "LATE"})
        card = due.renewal
        self.assertEqual(card.assigned_to, self.agent)
        self.assertEqual(card.expiration_date, due.end_date)
        self.assertEqual(card.stage, InsuranceRenewal.Stage.UPCOMING)
        self.assertTrue(InsuranceRenewal.objects.filter(policy=expired_recently).exists())

    def test_sync_is_idempotent_and_follows_the_window_setting(self):
        self.policy("P", days=80)
        sync_renewals(self.org, today=self.today)
        self.assertEqual(InsuranceRenewal.objects.count(), 0)
        InsuranceRenewalSettings.objects.update_or_create(organization=self.org, defaults={"window_days": 90})
        sync_renewals(self.org, today=self.today)
        sync_renewals(self.org, today=self.today)
        self.assertEqual(InsuranceRenewal.objects.count(), 1)

    def test_open_card_follows_policy_date_and_closes_when_policy_goes_inactive(self):
        p = self.policy("P", days=20)
        sync_renewals(self.org, today=self.today)
        p.end_date = self.today + timedelta(days=25)
        p.save()
        sync_renewals(self.org, today=self.today)
        card = InsuranceRenewal.objects.get(policy=p)
        self.assertEqual(card.expiration_date, p.end_date)

        p.status = "inactive"
        p.inactive_date = self.today
        p.save()
        sync_renewals(self.org, today=self.today)
        card.refresh_from_db()
        self.assertEqual(card.stage, InsuranceRenewal.Stage.LOST)
        self.assertTrue(card.closed_at)

    def test_reminder_due_uses_the_latest_unsent_offset(self):
        p = self.policy("P", days=14)
        sync_renewals(self.org, today=self.today)
        card = p.renewal
        offsets = [45, 30, 15, 7]
        self.assertEqual(reminder_due(card, offsets, self.today), 15)
        card.reminders_sent = "45,30,15"
        self.assertIsNone(reminder_due(card, offsets, self.today))
        self.assertEqual(reminder_due(card, offsets, self.today + timedelta(days=8)), 7)


class RenewalPagesTests(RenewalBase):
    def test_sidebar_has_renewals_and_page_lists_cards(self):
        self.policy("LIST-1", days=10)
        self.client.force_login(self.owner)
        res = self.client.get(reverse("insurance-renewals"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, f'href="{reverse("insurance-renewals")}"')
        self.assertContains(res, "LIST-1")
        self.assertContains(res, "Stone")

    def test_agent_sees_own_cards_by_default_and_office_on_request(self):
        self.policy("MINE", days=10, added_by=self.agent)
        self.policy("THEIRS", days=10, added_by=self.other_agent)
        self.client.force_login(self.agent)
        res = self.client.get(reverse("insurance-renewals"))
        self.assertContains(res, "MINE")
        self.assertNotContains(res, "THEIRS")
        res = self.client.get(reverse("insurance-renewals"), {"scope": "all"})
        self.assertContains(res, "THEIRS")

    def test_agent_cannot_work_another_agents_card(self):
        p = self.policy("THEIRS", days=10, added_by=self.other_agent)
        sync_renewals(self.org)
        card = p.renewal
        self.client.force_login(self.agent)
        self.assertEqual(self.client.get(reverse("insurance-renewal-detail", args=[card.id])).status_code, 200)
        res = self.client.post(reverse("insurance-renewal-action", args=[card.id]), {"action": "contact", "kind": "call"})
        self.assertEqual(res.status_code, 403)
        res = self.client.post(reverse("insurance-renewal-renew", args=[card.id]), {"premium": "100"})
        self.assertEqual(res.status_code, 403)

    def test_cards_from_another_office_are_hidden(self):
        other = Organization.objects.create(name="Elsewhere")
        c = Client.objects.create(organization=other, first_name="X", last_name="Y")
        p = InsurancePolicy.objects.create(
            organization=other, client=c, policy_number="FOREIGN", premium=Decimal("1"),
            start_date=self.today, end_date=self.today + timedelta(days=5), stage="bound",
        )
        sync_renewals(other)
        self.client.force_login(self.owner)
        res = self.client.get(reverse("insurance-renewal-detail", args=[p.renewal.id]))
        self.assertEqual(res.status_code, 404)

    def test_log_call_moves_upcoming_to_contacted(self):
        p = self.policy("P", days=10)
        sync_renewals(self.org)
        card = p.renewal
        self.client.force_login(self.agent)
        url = reverse("insurance-renewal-action", args=[card.id])
        self.client.post(url, {"action": "contact", "kind": "call", "note": "Left a voicemail"})
        card.refresh_from_db()
        self.assertEqual(card.stage, InsuranceRenewal.Stage.CONTACTED)
        self.assertEqual(card.contact_count, 1)
        self.assertTrue(card.events.filter(kind="call", note="Left a voicemail").exists())

        res = self.client.post(url, {"action": "contact", "kind": "text"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(res.json()["ok"], True)

    def test_stage_snooze_assign_and_lost(self):
        p = self.policy("P", days=10)
        sync_renewals(self.org)
        card = p.renewal
        url = reverse("insurance-renewal-action", args=[card.id])

        self.client.force_login(self.agent)
        self.client.post(url, {"action": "stage", "stage": "requoting"})
        self.client.post(url, {"action": "snooze", "days": "3"})
        res = self.client.post(url, {"action": "assign", "assigned_to": self.other_agent.id})
        self.assertEqual(res.status_code, 403)
        card.refresh_from_db()
        self.assertEqual(card.stage, "requoting")
        self.assertEqual(card.snoozed_until, self.today + timedelta(days=3))

        self.client.force_login(self.owner)
        self.client.post(url, {"action": "assign", "assigned_to": self.other_agent.id})
        card.refresh_from_db()
        self.assertEqual(card.assigned_to, self.other_agent)

        self.client.post(url, {"action": "lost", "reason": "price", "note": "Found cheaper"})
        card.refresh_from_db()
        self.assertEqual(card.stage, "lost")
        self.assertEqual(card.lost_reason, "price")

        self.client.post(url, {"action": "reopen"})
        card.refresh_from_db()
        self.assertEqual(card.stage, "upcoming")


class RenewTests(RenewalBase):
    def test_renew_creates_linked_next_term_with_vehicles(self):
        p = self.policy("R-1", days=10, producer=None)
        InsurancePolicyVehicle.objects.create(policy=p, auto_number=1, year=2020, make="Toyota", vin="1HGCM82633A004352")
        sync_renewals(self.org)
        card = p.renewal
        self.client.force_login(self.agent)
        res = self.client.post(
            reverse("insurance-renewal-renew", args=[card.id]),
            {"premium": "1350.00", "policy_number": "R-2", "insurance_company": self.company.id, "copy_vehicles": "1"},
        )
        self.assertRedirects(res, reverse("insurance-renewal-detail", args=[card.id]), fetch_redirect_response=False)
        card.refresh_from_db()
        new = card.new_policy
        self.assertEqual(card.stage, "renewed")
        self.assertEqual(new.policy_number, "R-2")
        self.assertEqual(new.premium, Decimal("1350.00"))
        self.assertEqual(new.start_date, p.end_date)
        self.assertEqual(new.end_date, add_months(p.end_date, 6))
        self.assertEqual(new.business_type, "renewal")
        self.assertEqual(new.stage, "bound")
        self.assertEqual(new.added_by, self.agent)
        self.assertEqual(new.policy_vehicles.get().vin, "1HGCM82633A004352")
        self.assertEqual([t.id for t in renewal_history(new)], [p.id, new.id])
        self.assertEqual([t.id for t in renewal_history(p)], [p.id, new.id])

        res = self.client.post(reverse("insurance-renewal-renew", args=[card.id]), {"premium": "1"})
        self.assertEqual(InsurancePolicy.objects.filter(client=self.customer).count(), 2)

    def test_changing_company_makes_it_a_rewrite_and_unchecked_copy_skips_vehicles(self):
        p = self.policy("R-1", days=10)
        InsurancePolicyVehicle.objects.create(policy=p, auto_number=1, make="Honda")
        sync_renewals(self.org)
        self.client.force_login(self.owner)
        self.client.post(
            reverse("insurance-renewal-renew", args=[p.renewal.id]),
            {"premium": "900", "insurance_company": self.other_company.id, "copy_vehicles": ["0"]},
        )
        card = InsuranceRenewal.objects.get(policy=p)
        self.assertEqual(card.stage, "rewritten")
        self.assertEqual(card.new_policy.business_type, "rewrite")
        self.assertEqual(card.new_policy.insurance_company, self.other_company)
        self.assertFalse(card.new_policy.policy_vehicles.exists())

    def test_renew_rejects_missing_premium_and_foreign_company(self):
        p = self.policy("R-1", days=10)
        sync_renewals(self.org)
        foreign = InsuranceCompany.objects.create(organization=Organization.objects.create(name="O2"), name="Foreign")
        self.client.force_login(self.owner)
        url = reverse("insurance-renewal-renew", args=[p.renewal.id])
        self.client.post(url, {"premium": ""})
        self.client.post(url, {"premium": "10", "insurance_company": foreign.id})
        self.assertEqual(InsurancePolicy.objects.count(), 1)
        self.assertEqual(InsuranceRenewal.objects.get().stage, "upcoming")

    def test_link_an_already_entered_policy(self):
        p = self.policy("OLD", days=10)
        sync_renewals(self.org)
        newer = InsurancePolicy.objects.create(
            organization=self.org, client=self.customer, policy_number="NEW", insurance_company=self.company,
            premium=Decimal("1100"), start_date=p.end_date, end_date=add_months(p.end_date, 6), stage="bound",
            business_type="renewal",
        )
        self.client.force_login(self.owner)
        self.client.post(reverse("insurance-renewal-link", args=[p.renewal.id]), {"policy_id": newer.id})
        card = InsuranceRenewal.objects.get(policy=p)
        self.assertEqual(card.stage, "renewed")
        self.assertEqual(card.new_policy, newer)


class EmailAndSettingsTests(RenewalBase):
    def test_email_reminder_is_sent_and_logged(self):
        p = self.policy("E-1", days=14)
        sync_renewals(self.org)
        card = p.renewal
        self.client.force_login(self.agent)
        detail = self.client.get(reverse("insurance-renewal-detail", args=[card.id]))
        self.assertContains(detail, "Hi Mia,")
        self.assertContains(detail, "The 15-day reminder is due")

        self.client.post(
            reverse("insurance-renewal-email", args=[card.id]),
            {"subject": "Your renewal", "body": "Hi Mia,\nPlease call us."},
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["mia@example.com"])
        card.refresh_from_db()
        self.assertEqual(card.stage, "contacted")
        self.assertIn(15, card.sent_offsets())
        self.assertIn(30, card.sent_offsets())
        self.assertTrue(card.events.filter(kind="email").exists())

    def test_email_needs_a_client_address(self):
        self.customer.email = ""
        self.customer.save()
        p = self.policy("E-1", days=14)
        sync_renewals(self.org)
        self.client.force_login(self.agent)
        self.client.post(reverse("insurance-renewal-email", args=[p.renewal.id]), {"subject": "S", "body": "B"})
        self.assertEqual(len(mail.outbox), 0)

    def test_only_managers_change_settings(self):
        url = reverse("insurance-renewal-settings")
        data = {
            "window_days": "45", "reminder_days": "30, 10,10", "daily_collection_target": "2500",
            "email_subject": "Renew {policy_number}", "email_body": "Body", "text_body": "Text",
        }
        self.client.force_login(self.agent)
        self.assertEqual(self.client.post(url, data).status_code, 403)
        self.client.force_login(self.owner)
        self.client.post(url, data)
        s = InsuranceRenewalSettings.objects.get(organization=self.org)
        self.assertEqual(s.window_days, 45)
        self.assertEqual(s.reminder_days, "30,10")
        self.assertEqual(s.daily_collection_target, Decimal("2500.00"))
        self.assertEqual(s.email_subject, "Renew {policy_number}")

        self.client.post(url, {**data, "window_days": "2"})
        self.assertEqual(InsuranceRenewalSettings.objects.get(organization=self.org).window_days, 45)


class TodayBoardTests(RenewalBase):
    def test_home_shows_today_board_sections(self):
        p = self.policy("HOME-1", days=5)
        InsurancePolicyInstallment.objects.create(
            policy=p, installment_number=2, due_date=self.today - timedelta(days=2), amount=Decimal("150")
        )
        DailyPaymentTransaction.objects.create(
            organization=self.org, client=self.customer, transaction_date=self.today, amount=Decimal("300"),
            payment_type="monthly_payment", payment_method="cash",
        )
        self.client.force_login(self.owner)
        res = self.client.get(reverse("insurance-home"))
        self.assertContains(res, "Expiring policies")
        self.assertContains(res, "HOME-1")
        self.assertContains(res, "Missed")
        self.assertContains(res, "$300.00")
        self.assertContains(res, "Birthdays &amp; anniversaries")

    def test_board_scopes_agents_to_their_own_work(self):
        self.policy("MINE", days=5, added_by=self.agent)
        self.policy("THEIRS", days=5, added_by=self.other_agent)
        board = today_board(self.org, self.agent, mine=True)
        self.assertEqual([r["card"].policy.policy_number for r in board["expiring"]], ["MINE"])
        board = today_board(self.org, self.owner, mine=False)
        self.assertEqual(len(board["expiring"]), 2)

    def test_birthday_and_client_anniversary(self):
        soon = self.today + timedelta(days=2)
        self.customer.dob = date(1990, soon.month, min(soon.day, 28))
        self.customer.save()
        p = self.policy("ANNIV", days=150)
        p.bound_date = date(self.today.year - 3, self.today.month, min(self.today.day, 28))
        p.save()
        board = today_board(self.org, self.owner, mine=False)
        kinds = {row["kind"] for row in board["celebrations"]}
        if soon.day <= 28:
            self.assertIn("birthday", kinds)
        if self.today.day <= 28:
            self.assertIn("anniversary", kinds)

    def test_collection_goal_falls_back_to_last_week_average(self):
        DailyPaymentTransaction.objects.create(
            organization=self.org, client=self.customer, transaction_date=self.today - timedelta(days=1),
            amount=Decimal("700"), payment_type="misc", payment_method="cash",
        )
        board = today_board(self.org, self.owner, mine=False)
        self.assertEqual(board["collection_target"], Decimal("100.00"))
        self.assertEqual(board["collection_target_label"], "Last 7-day average")
        InsuranceRenewalSettings.objects.update_or_create(
            organization=self.org, defaults={"daily_collection_target": Decimal("500")}
        )
        board = today_board(self.org, self.owner, mine=False)
        self.assertEqual(board["collection_target"], Decimal("500"))


class RetentionTests(RenewalBase):
    def test_retention_view_counts_kept_and_lost(self):
        won = self.policy("WON", days=5)
        lost = self.policy("LOST", days=6, premium=Decimal("800"))
        self.policy("OPEN", days=7)
        sync_renewals(self.org)
        self.client.force_login(self.owner)
        self.client.post(reverse("insurance-renewal-renew", args=[won.renewal.id]), {"premium": "1300"})
        self.client.post(
            reverse("insurance-renewal-action", args=[lost.renewal.id]), {"action": "lost", "reason": "price"}
        )
        res = self.client.get(reverse("insurance-renewals"), {"view": "retention"})
        total = res.context["rn_retention"].total
        self.assertEqual((total.won, total.lost, total.open), (1, 1, 1))
        self.assertEqual(total.rate, 50)
        self.assertEqual(total.kept_premium, Decimal("1300.00"))
        self.assertEqual(total.lost_premium, Decimal("800.00"))
        self.assertContains(res, "Price too high")

        closed = self.client.get(reverse("insurance-renewals"), {"view": "closed"})
        self.assertContains(closed, "WON")
        self.assertContains(closed, "LOST")
