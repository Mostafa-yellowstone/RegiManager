from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.insurance_producers import (
    add_months,
    build_policy_ledger,
    months_elapsed,
    settlement_plan,
    summarize_producer,
)
from core.models import (
    Client,
    InsuranceCompany,
    InsurancePolicy,
    InsurancePolicyPremiumChange,
    InsuranceProducer,
    InsuranceProducerPayout,
    Organization,
    OrganizationMembership,
    Space,
)

User = get_user_model()


class ProducerBase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Producer PSB", city="Yonkers", state="NY")
        self.space = Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        self.owner = User.objects.create_user(username="prd_owner", password="pass12345")
        owner_mem = OrganizationMembership.objects.create(
            can_use_insurance=True,
            organization=self.org, user=self.owner, role=OrganizationMembership.Role.OWNER,
            is_active=True, can_view_spaces=True,
        )
        owner_mem.accessible_spaces.add(self.space)
        self.agent = User.objects.create_user(username="prd_agent", password="pass12345")
        self.agent_mem = OrganizationMembership.objects.create(
            can_use_insurance=True,
            organization=self.org,
            user=self.agent,
            role=OrganizationMembership.Role.INSURANCE_AGENT,
            is_active=True,
            can_deal_with_insurance=True,
            can_view_spaces=True,
        )
        self.agent_mem.accessible_spaces.add(self.space)
        self.client_obj = Client.objects.create(organization=self.org, first_name="Mia", last_name="Stone")
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Acme Mutual")
        self.producer = InsuranceProducer.objects.create(
            organization=self.org,
            name="Sara Ahmed",
            default_rate=Decimal("50.00"),
            rate_basis="commission",
            default_payout="once",
        )
        self.today = timezone.localdate()

    def policy(self, number="P-1", *, producer=None, rate="50.00", basis="commission", payout="once",
               premium="1200.00", start=None, months=12, status="active", stage="bound", inactive=None,
               insurance_type="", business_type="new_business"):
        start = start or self.today
        return InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            policy_number=number,
            insurance_company=self.company,
            premium=Decimal(premium),
            commission_rate=Decimal("15.00"),
            stage=stage,
            status=status,
            insurance_type=insurance_type,
            business_type=business_type,
            start_date=start,
            end_date=add_months(start, months),
            insurance_period_months=months,
            inactive_date=inactive,
            bound_date=start,
            producer=producer if producer is not None else self.producer,
            producer_rate=Decimal(rate),
            producer_rate_basis=basis,
            producer_payout=payout,
        )


class ProducerMathTests(ProducerBase):
    def test_commission_and_premium_basis(self):
        on_commission = self.policy("C-1")
        self.assertEqual(on_commission.commission_amount, Decimal("180.00"))
        self.assertEqual(on_commission.producer_commission_amount, Decimal("90.00"))
        on_premium = self.policy("C-2", rate="5.00", basis="premium")
        self.assertEqual(on_premium.producer_commission_amount, Decimal("60.00"))

    def test_no_producer_means_no_producer_amount(self):
        p = InsurancePolicy.objects.create(
            organization=self.org, client=self.client_obj, policy_number="N-1", insurance_company=self.company,
            premium=Decimal("500"), commission_rate=Decimal("10"), start_date=self.today,
            end_date=add_months(self.today, 6), bound_date=self.today,
        )
        self.assertIsNone(p.producer_commission_amount)

    def test_months_elapsed_counts_first_month_on_start(self):
        start = date(2026, 1, 15)
        self.assertEqual(months_elapsed(start, date(2026, 1, 14), 12), 0)
        self.assertEqual(months_elapsed(start, date(2026, 1, 15), 12), 1)
        self.assertEqual(months_elapsed(start, date(2026, 2, 14), 12), 1)
        self.assertEqual(months_elapsed(start, date(2026, 2, 15), 12), 2)
        self.assertEqual(months_elapsed(start, date(2028, 1, 1), 12), 12)

    def test_monthly_accrual_and_remaining(self):
        start = add_months(self.today, -2)
        p = self.policy("M-1", payout="monthly", start=start)
        lg = build_policy_ledger(p, [], today=self.today)
        self.assertEqual(lg.per_month, Decimal("7.50"))
        self.assertEqual(lg.months_earned, 3)
        self.assertEqual(lg.earned_to_date, Decimal("22.50"))
        self.assertEqual(lg.due_now, Decimal("22.50"))
        self.assertEqual(lg.remaining, Decimal("90.00"))
        self.assertEqual(lg.upcoming, Decimal("67.50"))
        self.assertEqual(lg.next_payment_date, add_months(start, 3))

    def test_monthly_accrual_does_not_compound_rounding(self):
        p = self.policy("M-2", payout="monthly", premium="1500.00", start=add_months(self.today, -7))
        lg = build_policy_ledger(p, [], today=self.today)
        self.assertEqual(lg.per_month, Decimal("9.38"))
        self.assertEqual(lg.months_earned, 8)
        self.assertEqual(lg.earned_to_date, Decimal("75.00"))

    def test_inactive_policy_overpaid_becomes_deduction(self):
        start = self.today - timedelta(days=100)
        p = self.policy("X-1", start=start, months=12)
        InsuranceProducerPayout.objects.create(
            organization=self.org, producer=self.producer, policy=p, amount=Decimal("90.00"), paid_on=start
        )
        p.status = "inactive"
        p.inactive_date = start + (p.end_date - start) / 2
        p.save()
        lg = build_policy_ledger(p, list(p.producer_payouts.all()), today=self.today)
        self.assertGreater(lg.owes_back, Decimal("40"))
        self.assertLess(lg.owes_back, Decimal("50"))
        self.assertEqual(lg.status_key, "owes_back")

    def test_quote_policy_earns_nothing(self):
        p = self.policy("Q-1", stage="quote")
        lg = build_policy_ledger(p, [], today=self.today)
        self.assertEqual(lg.due_now, Decimal("0.00"))
        self.assertEqual(lg.status_key, "not_bound")

    def test_settlement_nets_deductions_against_due(self):
        start = self.today - timedelta(days=100)
        cancelled = self.policy("S-1", start=start)
        InsuranceProducerPayout.objects.create(
            organization=self.org, producer=self.producer, policy=cancelled, amount=Decimal("90.00"), paid_on=start
        )
        cancelled.status = "inactive"
        cancelled.inactive_date = start + timedelta(days=10)
        cancelled.save()
        self.policy("S-2")
        summary = summarize_producer(self.producer, today=self.today)
        self.assertEqual(summary.due_now, Decimal("90.00"))
        rows = settlement_plan(summary)
        net = sum(amount for _, _, amount in rows)
        self.assertEqual(net, summary.net_payable)
        self.assertTrue(any(kind == "deduction" for _, kind, _ in rows))


class ProducerPolicyFormTests(ProducerBase):
    def _post(self, user, url, **extra):
        self.client.force_login(user)
        data = {
            "organization": self.org.id,
            "client_name": "Mia Stone",
            "insurance_company": self.company.id,
            "policy_number": "F-1",
            "premium": "1000.00",
            "broker_fee": "0",
            "commission_rate": "10",
            "stage": "bound",
            "status": "active",
            "business_type": "auto_renewal",
            "bound_date": self.today.isoformat(),
            "start_date": self.today.isoformat(),
            "end_date": add_months(self.today, 6).isoformat(),
            "insurance_period_months": "6",
        }
        data.update(extra)
        return self.client.post(url, data)

    def test_add_policy_with_producer_uses_defaults_and_override(self):
        self._post(self.owner, reverse("add-insurance-policy"), has_producer="1",
                   producer=str(self.producer.id), producer_rate="40", producer_payout="monthly")
        p = InsurancePolicy.objects.get(policy_number="F-1")
        self.assertEqual(p.business_type, "auto_renewal")
        self.assertEqual(p.producer, self.producer)
        self.assertEqual(p.producer_rate, Decimal("40"))
        self.assertEqual(p.producer_payout, "monthly")
        self.assertEqual(p.producer_commission_amount, Decimal("40.00"))

    def test_agent_without_finance_gets_producer_default_rate(self):
        self._post(self.agent, reverse("add-insurance-policy"), has_producer="1",
                   producer=str(self.producer.id), producer_rate="99")
        p = InsurancePolicy.objects.get(policy_number="F-1")
        self.assertEqual(p.producer_rate, Decimal("50.00"))

    def test_checkbox_without_producer_is_rejected(self):
        self._post(self.owner, reverse("add-insurance-policy"), has_producer="1", producer="")
        self.assertFalse(InsurancePolicy.objects.filter(policy_number="F-1").exists())

    def test_endorsement_premium_change_is_logged_and_recalculates(self):
        p = self.policy("E-1", premium="1200.00")
        self._post(
            self.owner, reverse("edit-insurance-policy", args=[p.id]),
            policy_number="E-1", premium="1500.00", commission_rate="15", stage="endorsement",
            has_producer="1", producer=str(self.producer.id), producer_rate="50",
            start_date=p.start_date.isoformat(), end_date=p.end_date.isoformat(), insurance_period_months="12",
        )
        p.refresh_from_db()
        self.assertEqual(p.producer_commission_amount, Decimal("112.50"))
        change = InsurancePolicyPremiumChange.objects.get(policy=p)
        self.assertEqual((change.old_premium, change.new_premium), (Decimal("1200.00"), Decimal("1500.00")))

    def test_edit_json_hides_producer_rate_from_non_finance(self):
        p = self.policy("J-1")
        p.added_by = self.agent
        p.save()
        self.client.force_login(self.agent)
        data = self.client.get(reverse("edit-insurance-policy", args=[p.id])).json()
        self.assertEqual(data["producer_id"], self.producer.id)
        self.assertEqual(data["producer_rate"], "")


class ProducerStaffPageTests(ProducerBase):
    def test_tab_and_profile_render_for_finance(self):
        self.policy("T-1")
        self.client.force_login(self.owner)
        res = self.client.get(reverse("insurance-producers"))
        self.assertContains(res, "tab-producers")
        self.assertContains(res, "Sara Ahmed")
        self.assertContains(res, "Auto-Renewal")
        res = self.client.get(reverse("insurance-producer-detail", args=[self.producer.id]))
        self.assertContains(res, "T-1")
        self.assertContains(res, "Pay everything due")

    def test_agent_without_finance_cannot_open_producer(self):
        self.client.force_login(self.agent)
        res = self.client.get(reverse("insurance-producer-detail", args=[self.producer.id]))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.client.get(reverse("insurance-producers")).status_code, 403)
        res = self.client.get(reverse("insurance-policies"))
        self.assertNotContains(res, f'href="{reverse("insurance-producers")}"')

    def test_add_producer_with_login_and_settle(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("add-insurance-producer"), {
            "organization": self.org.id, "name": "Omar Lee", "default_rate": "10",
            "rate_basis": "premium", "default_payout": "once",
            "create_login": "1", "username": "omar.prod", "password": "Prod-Login-7731",
        })
        omar = InsuranceProducer.objects.get(name="Omar Lee")
        self.assertEqual(omar.user.username, "omar.prod")
        self.assertTrue(omar.user.check_password("Prod-Login-7731"))
        self.policy("SET-1", producer=omar, rate="10", basis="premium")
        self.client.post(reverse("settle-insurance-producer", args=[omar.id]), {"method": "zelle"})
        payout = InsuranceProducerPayout.objects.get(producer=omar)
        self.assertEqual(payout.amount, Decimal("120.00"))
        self.assertEqual(summarize_producer(omar).due_now, Decimal("0.00"))

    def test_non_finance_page_does_not_expose_producer_rates(self):
        self.client.force_login(self.agent)
        res = self.client.get(reverse("insurance-policies"))
        self.assertContains(res, "Sara Ahmed")
        self.assertNotContains(res, "data-rate=")

    def test_invalid_payout_date_is_rejected(self):
        p = self.policy("D-1")
        self.client.force_login(self.owner)
        self.client.post(reverse("record-insurance-producer-payout", args=[self.producer.id]), {
            "policy": p.id, "amount": "10", "paid_on": "not-a-date", "method": "cash",
        })
        self.assertFalse(InsuranceProducerPayout.objects.exists())

    def test_weak_or_bad_login_is_rejected(self):
        self.client.force_login(self.owner)
        url = reverse("set-insurance-producer-login", args=[self.producer.id])
        self.client.post(url, {"username": "bad name!", "password": "Prod-Login-7731"})
        self.client.post(url, {"username": "sara.prod", "password": "12345678"})
        self.producer.refresh_from_db()
        self.assertIsNone(self.producer.user_id)

    def test_staff_login_linked_to_producer_is_never_disabled(self):
        self.producer.user = self.agent
        self.producer.save()
        self.client.force_login(self.owner)
        self.client.post(reverse("set-insurance-producer-login", args=[self.producer.id]), {"action": "disable"})
        self.client.post(reverse("edit-insurance-producer", args=[self.producer.id]), {
            "name": "Sara Ahmed", "default_rate": "50", "rate_basis": "commission", "default_payout": "once",
        })
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.is_active)

    def test_producer_pages_are_not_cached(self):
        self.client.force_login(self.owner)
        res = self.client.get(reverse("insurance-producer-detail", args=[self.producer.id]))
        self.assertIn("no-store", res.get("Cache-Control", ""))

    def test_client_profile_shows_commission_status_only_for_finance(self):
        p = self.policy("CP-1")
        p.commission_received = True
        p.save()
        self.client.force_login(self.owner)
        res = self.client.get(reverse("client-detail", args=[self.client_obj.id]))
        self.assertContains(res, "Carrier commission")
        self.assertContains(res, "Producer paid")


class ProducerPortalTests(ProducerBase):
    def setUp(self):
        super().setUp()
        self.prod_user = User.objects.create_user(username="sara.prod", password="longpass123")
        self.producer.user = self.prod_user
        self.producer.save()
        self.other = InsuranceProducer.objects.create(organization=self.org, name="Other Producer")

    def test_portal_shows_only_own_policies(self):
        self.policy("MINE-1")
        self.policy("THEIRS-1", producer=self.other)
        self.client.force_login(self.prod_user)
        res = self.client.get(reverse("producer-portal"))
        self.assertContains(res, "MINE-1")
        self.assertNotContains(res, "THEIRS-1")

    def test_producer_is_kept_inside_portal(self):
        self.client.force_login(self.prod_user)
        self.assertRedirects(self.client.get(reverse("login")), reverse("producer-portal"))
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("producer-portal"))
        res = self.client.get(reverse("insurance-producer-detail", args=[self.producer.id]))
        self.assertRedirects(res, reverse("producer-portal"))

    def test_staff_user_is_not_restricted(self):
        self.client.force_login(self.owner)
        res = self.client.get(reverse("producer-portal"))
        self.assertRedirects(res, reverse("dashboard"), fetch_redirect_response=False)

    def test_producer_can_change_password(self):
        self.client.force_login(self.prod_user)
        self.client.post(reverse("producer-portal-password"), {
            "old_password": "longpass123", "new_password1": "Fresh-Pass-9921", "new_password2": "Fresh-Pass-9921",
        })
        self.prod_user.refresh_from_db()
        self.assertTrue(self.prod_user.check_password("Fresh-Pass-9921"))


def _pdf_text(response) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    return "".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages)


class ProducerStatementTests(ProducerBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("producer-statement-pdf")
        self.p1 = self.policy("STMT-1")
        InsuranceProducerPayout.objects.create(
            organization=self.org, producer=self.producer, policy=self.p1, kind="payment",
            amount=Decimal("40.00"), paid_on=self.today, method="zelle", recorded_by=self.owner,
        )

    def test_staff_statement_pdf(self):
        self.client.force_login(self.owner)
        res = self.client.get(self.url, {"producer": self.producer.id})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertIn("no-store", res["Cache-Control"])
        text = _pdf_text(res)
        self.assertIn("Sara Ahmed", text)
        self.assertIn("STMT-1", text)
        self.assertIn("40.00", text)
        self.assertIn("Active", text)
        self.assertIn("New Business", text)
        self.assertIn(self.p1.start_date.strftime("%m/%d/%Y"), text)
        self.assertIn(self.p1.end_date.strftime("%m/%d/%Y"), text)
        self.assertNotIn(self.p1.end_date.strftime("%b %d, %Y"), text)
        self.assertNotIn("Bound", text)
        self.assertNotIn("bound", text)

    def test_inactive_policy_status_omits_stage(self):
        start = date(2024, 3, 15)
        cancelled_on = date(2024, 6, 2)
        inactive = self.policy("STMT-OFF", status="inactive", inactive=cancelled_on, start=start)
        self.client.force_login(self.owner)
        res = self.client.get(self.url, {"producer": self.producer.id})
        self.assertEqual(res.status_code, 200)
        text = _pdf_text(res)
        self.assertIn("Inactive", text)
        self.assertIn(inactive.start_date.strftime("%m/%d/%Y"), text)
        self.assertIn(inactive.end_date.strftime("%m/%d/%Y"), text)
        self.assertNotIn(inactive.start_date.strftime("%b %d, %Y"), text)
        self.assertNotIn(cancelled_on.strftime("%b %d, %Y"), text)
        self.assertNotIn(cancelled_on.strftime("%m/%d/%Y"), text)
        self.assertNotIn("Bound", text)
        self.assertNotIn("bound", text)

    def test_pending_and_rejected_keep_real_status(self):
        self.policy("STMT-PEND", status="pending", stage="quote")
        self.policy("STMT-REJ", status="rejected", stage="endorsement")
        self.client.force_login(self.owner)
        res = self.client.get(self.url, {"producer": self.producer.id})
        self.assertEqual(res.status_code, 200)
        text = _pdf_text(res)
        self.assertIn("Pending", text)
        self.assertIn("Rejected", text)
        self.assertNotIn("Bound", text)
        self.assertNotIn("Quote", text)
        self.assertNotIn("Endorsement", text)

    def test_statement_shows_policy_type_and_business(self):
        from core.models import InsuranceTypeOption

        InsuranceTypeOption.objects.create(organization=self.org, key="fleet", label="Fleet")
        auto = self.policy("STMT-AUTO", insurance_type="auto_personal", business_type="new_business")
        commercial = self.policy("STMT-COM", insurance_type="commercial_auto", business_type="renewal")
        rewrite = self.policy("STMT-RW", insurance_type="trucking", business_type="rewrite")
        auto_renewal = self.policy("STMT-AR", insurance_type="home_owners", business_type="auto_renewal")
        custom = self.policy("STMT-FLEET", insurance_type="fleet", business_type="new_business")
        self.client.force_login(self.owner)
        res = self.client.get(self.url, {"producer": self.producer.id})
        self.assertEqual(res.status_code, 200)
        text = _pdf_text(res)
        self.assertIn("AUTO PERSONAL", text)
        self.assertIn("COMMERCIAL AUTO", text)
        self.assertIn("TRUCKING", text)
        self.assertIn("HOME OWNERS", text)
        self.assertIn("Fleet", text)
        self.assertIn("New Business", text)
        self.assertIn("Rewrite", text)
        self.assertIn("Auto-Renewal", text)
        self.assertGreaterEqual(text.count("Renewal"), 2)
        for policy in (auto, commercial, rewrite, auto_renewal, custom):
            self.assertIn(policy.start_date.strftime("%m/%d/%Y"), text)
            self.assertIn(policy.end_date.strftime("%m/%d/%Y"), text)
            self.assertNotIn(policy.end_date.strftime("%b %d, %Y"), text)

    def test_statement_with_reversed_or_bad_dates(self):
        self.client.force_login(self.owner)
        later = (self.today + timedelta(days=30)).isoformat()
        earlier = (self.today - timedelta(days=30)).isoformat()
        res = self.client.get(self.url, {"producer": self.producer.id, "start_date": later, "end_date": earlier})
        self.assertEqual(res.status_code, 200)
        self.assertIn("STMT-1", _pdf_text(res))
        res = self.client.get(self.url, {"producer": self.producer.id, "start_date": "2026-13-45"})
        self.assertEqual(res.status_code, 200)

    def test_non_finance_agent_is_blocked(self):
        self.client.force_login(self.agent)
        self.assertEqual(self.client.get(self.url, {"producer": self.producer.id}).status_code, 403)

    def test_missing_or_foreign_producer(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(self.url, {"producer": "abc"}).status_code, 404)
        other_org = Organization.objects.create(name="Elsewhere", state="NY")
        foreign = InsuranceProducer.objects.create(organization=other_org, name="Foreign")
        self.assertEqual(self.client.get(self.url, {"producer": foreign.id}).status_code, 403)

    def test_reporting_center_lists_producers_for_finance_only(self):
        space_url = reverse("insurance-reports")
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(space_url), "Open statement PDF")
        self.client.force_login(self.agent)
        self.assertNotContains(self.client.get(space_url), "Open statement PDF")

    def test_producer_downloads_only_own_statement(self):
        prod_user = User.objects.create_user(username="sara.stmt", password="longpass123")
        self.producer.user = prod_user
        self.producer.save()
        other = InsuranceProducer.objects.create(organization=self.org, name="Other Producer")
        self.policy("OTHER-1", producer=other)
        self.client.force_login(prod_user)
        portal = self.client.get(reverse("producer-portal"))
        self.assertContains(portal, reverse("producer-portal-statement"))
        res = self.client.get(reverse("producer-portal-statement"), {"producer": other.id})
        self.assertEqual(res.status_code, 200)
        text = _pdf_text(res)
        self.assertIn("STMT-1", text)
        self.assertNotIn("OTHER-1", text)
        self.assertNotIn("Other Producer", text)
        # Staff report URL stays closed to producers.
        self.assertNotEqual(self.client.get(self.url, {"producer": other.id}).status_code, 200)

    def test_paused_producer_cannot_download(self):
        prod_user = User.objects.create_user(username="sara.paused", password="longpass123")
        self.producer.user = prod_user
        self.producer.is_active = False
        self.producer.save()
        self.client.force_login(prod_user)
        res = self.client.get(reverse("producer-portal-statement"))
        self.assertNotEqual(res.status_code, 200)


class ProducerPayoutExtrasTests(ProducerBase):
    def setUp(self):
        from core.models import BankAccount

        super().setUp()
        self.p1 = self.policy("BANK-1")
        self.account = BankAccount.objects.create(
            organization=self.org, account_name="Operating", bank_name="Chase", balance=Decimal("1000.00")
        )
        self.client.force_login(self.owner)
        self.record_url = reverse("record-insurance-producer-payout", args=[self.producer.id])

    def _record(self, amount, **extra):
        data = {"policy": self.p1.id, "amount": amount, "method": "zelle", **extra}
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.record_url, data)

    def test_payment_logs_bank_expense_and_delete_restores_balance(self):
        self._record("90.00", bank_account=self.account.id)
        payout = InsuranceProducerPayout.objects.get(policy=self.p1)
        entry = payout.bank_transaction
        self.assertIsNotNone(entry)
        self.assertEqual(entry.transaction_type, "expense_debit_transfer")
        self.assertEqual(entry.category, "Producer Commission")
        self.assertEqual(entry.amount, Decimal("90.00"))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("910.00"))

        self.client.post(reverse("delete-insurance-producer-payout", args=[payout.id]))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("1000.00"))
        self.assertFalse(type(entry).objects.filter(id=entry.id).exists())

    def test_repayment_logs_bank_income(self):
        self._record("-25.00", bank_account=self.account.id)
        entry = InsuranceProducerPayout.objects.get(policy=self.p1).bank_transaction
        self.assertEqual(entry.transaction_type, "income_credit_transfer")
        self.assertEqual(entry.category, "Producer Repayment")
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("1025.00"))

    def test_settlement_uses_one_bank_entry_and_resyncs(self):
        self.policy("BANK-2")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("settle-insurance-producer", args=[self.producer.id]),
                {"method": "zelle", "bank_account": self.account.id},
            )
        payouts = list(InsuranceProducerPayout.objects.filter(producer=self.producer))
        self.assertEqual(len(payouts), 2)
        entry_ids = {p.bank_transaction_id for p in payouts}
        self.assertEqual(len(entry_ids), 1)
        entry = payouts[0].bank_transaction
        self.assertEqual(entry.amount, Decimal("180.00"))
        self.client.post(reverse("delete-insurance-producer-payout", args=[payouts[0].id]))
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("90.00"))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("910.00"))

    def test_foreign_bank_account_is_rejected(self):
        from core.models import BankAccount

        other_org = Organization.objects.create(name="Elsewhere", state="NY")
        foreign = BankAccount.objects.create(organization=other_org, account_name="Theirs", balance=Decimal("50"))
        self._record("90.00", bank_account=foreign.id)
        self.assertFalse(InsuranceProducerPayout.objects.filter(policy=self.p1).exists())
        foreign.refresh_from_db()
        self.assertEqual(foreign.balance, Decimal("50.00"))

    def test_no_bank_account_means_no_entry(self):
        self._record("90.00")
        self.assertIsNone(InsuranceProducerPayout.objects.get(policy=self.p1).bank_transaction)
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("1000.00"))

    def test_email_notice_sent_when_requested(self):
        from django.core import mail

        self.producer.email = "sara@example.com"
        self.producer.save()
        self._record("90.00", notify="1")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["sara@example.com"])
        self.assertIn("90.00", message.subject)
        self.assertIn("BANK-1", message.body)

    def test_no_email_without_opt_in_or_address(self):
        from django.core import mail

        self._record("90.00", notify="1")
        self.producer.email = "sara@example.com"
        self.producer.save()
        self._record("10.00")
        self.assertEqual(len(mail.outbox), 0)

    def test_detail_page_shows_bank_and_notify_options(self):
        res = self.client.get(reverse("insurance-producer-detail", args=[self.producer.id]))
        self.assertContains(res, "Operating")
        self.assertContains(res, 'name="notify"')
        self.assertContains(res, "This producer has no email address.")
