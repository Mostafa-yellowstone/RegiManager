import importlib
from datetime import date
from decimal import Decimal

from django.apps import apps
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.insurance_desk import EndorsementError, record_transaction
from core.insurance_desk_models import InsurancePolicyTransaction
from core.insurance_producer_models import InsuranceProducer
from core.insurance_space_metrics import period_stats
from core.insurance_wholesalers import WholesalerInputError, wholesaler_for_policy
from core.models import (
    Client,
    InsuranceCompany,
    InsurancePolicy,
    InsuranceWholesaler,
    Notification,
)
from core.tests_insurance_area import InsuranceAreaBase


class EndorsementBase(InsuranceAreaBase):
    def setUp(self):
        super().setUp()
        self.customer = Client.objects.create(organization=self.org, first_name="Endo", last_name="Client")
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Carrier A")
        today = timezone.localdate()
        self.policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.customer,
            insurance_company=self.company,
            policy_number="END-1",
            premium=Decimal("1000.00"),
            commission_rate=Decimal("10.00"),
            stage="bound",
            status="active",
            bound_date=today,
            start_date=today,
            end_date=date(today.year + 1, 1, 1),
            added_by=self.agent,
        )


class EndorsementLifecycleTests(EndorsementBase):
    def _endorse(self, **extra):
        self.client.force_login(self.owner)
        data = {
            "desk_action": "transaction",
            "kind": "endorsement",
            "effective_date": timezone.localdate().isoformat(),
            "new_premium": "1200.00",
            "note": "Added a driver",
        }
        data.update(extra)
        return self.client.post(reverse("insurance-policy-desk", args=[self.policy.id]), data)

    def test_endorsement_keeps_policy_bound_and_updates_premium_and_commission(self):
        self._endorse()
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.stage, "bound")
        self.assertEqual(self.policy.premium, Decimal("1200.00"))
        self.assertEqual(self.policy.commission_amount, Decimal("120.00"))
        tx = InsurancePolicyTransaction.objects.get(policy=self.policy, kind="endorsement")
        self.assertEqual((tx.old_premium, tx.new_premium), (Decimal("1000.00"), Decimal("1200.00")))
        self.assertEqual(self.policy.premium_changes.count(), 1)

    def test_endorsed_policy_counts_in_period_totals(self):
        self._endorse()
        today = timezone.localdate()
        stats = period_stats(InsurancePolicy.objects.filter(organization=self.org), today.replace(day=1), today)
        self.assertEqual(stats["premium"], 1200.0)
        self.assertEqual(stats["earned_commission"], 120.0)
        self.assertEqual(stats["bound"], 1)

    def test_owners_and_agent_get_an_endorsement_notification(self):
        self._endorse()
        notes = Notification.objects.filter(event_type="policy_endorsed", policy=self.policy)
        self.assertEqual(set(notes.values_list("user_id", flat=True)), {self.owner.id, self.agent.id})
        note = notes.first()
        self.assertEqual(note.title, "Policy endorsed")
        self.assertIn("$1,000.00 → $1,200.00", note.message)
        self.assertIn("+$200.00", note.message)
        self.assertEqual(note.action_url, reverse("insurance-policy-detail", args=[self.policy.id]))

    def test_endorsement_needs_a_new_premium(self):
        response = self._endorse(new_premium="")
        self.assertEqual(response.status_code, 302)
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.premium, Decimal("1000.00"))
        self.assertFalse(InsurancePolicyTransaction.objects.filter(policy=self.policy).exists())
        self.assertFalse(Notification.objects.filter(event_type="policy_endorsed").exists())

    def test_quote_cannot_be_endorsed(self):
        self.policy.stage = "quote"
        self.policy.save()
        with self.assertRaises(EndorsementError):
            record_transaction(self.policy, kind="endorsement", user=self.owner, new_premium=Decimal("1500"))

    def test_edit_modal_endorsement_stage_records_an_endorsement(self):
        self.client.force_login(self.owner)
        today = timezone.localdate()
        self.client.post(
            reverse("edit-insurance-policy", args=[self.policy.id]),
            {
                "client_name": "Endo Client",
                "insurance_company": self.company.id,
                "policy_number": "END-1",
                "premium": "900.00",
                "broker_fee": "0",
                "commission_rate": "10",
                "stage": "endorsement",
                "status": "active",
                "bound_date": today.isoformat(),
                "start_date": today.isoformat(),
                "end_date": date(today.year + 1, 1, 1).isoformat(),
                "insurance_period_months": "6",
            },
        )
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.stage, "bound")
        self.assertEqual(self.policy.premium, Decimal("900.00"))
        tx = InsurancePolicyTransaction.objects.get(policy=self.policy, kind="endorsement")
        self.assertEqual(tx.new_premium - tx.old_premium, Decimal("-100.00"))
        self.assertTrue(Notification.objects.filter(event_type="policy_endorsed", user=self.agent).exists())

    def test_finance_page_lists_the_endorsement(self):
        self._endorse()
        response = self.client.get(reverse("insurance-finance"))
        self.assertContains(response, "Recent endorsements")
        self.assertContains(response, "+$200.00")
        self.assertContains(response, "+$20.00")

    def test_endorsement_stage_filter_finds_endorsed_bound_policies(self):
        self._endorse()
        response = self.client.get(reverse("insurance-policies"), {"stage": "endorsement", "all_dates": "1"})
        self.assertContains(response, '<td class="ipc-mono">END-1</td>')


class DefaultCommissionTests(EndorsementBase):
    def _add(self, rate):
        self.client.force_login(self.owner)
        today = timezone.localdate()
        self.client.post(
            reverse("add-insurance-policy"),
            {
                "organization": self.org.id,
                "client_name": "Endo Client",
                "insurance_company": self.company.id,
                "policy_number": f"NEW-{rate or 'blank'}",
                "premium": "500.00",
                "broker_fee": "0",
                "commission_rate": rate,
                "stage": "bound",
                "status": "active",
                "bound_date": today.isoformat(),
                "start_date": today.isoformat(),
                "end_date": date(today.year + 1, 1, 1).isoformat(),
                "insurance_period_months": "6",
            },
        )
        return InsurancePolicy.objects.get(policy_number=f"NEW-{rate or 'blank'}")

    def test_blank_or_zero_commission_uses_ten_percent(self):
        for raw in ("", "0"):
            policy = self._add(raw)
            self.assertEqual(policy.commission_rate, Decimal("10.00"))
            self.assertEqual(policy.commission_amount, Decimal("50.00"))

    def test_typed_commission_rate_is_kept(self):
        policy = self._add("12")
        self.assertEqual(policy.commission_rate, Decimal("12.00"))
        self.assertEqual(policy.commission_amount, Decimal("60.00"))

    def test_model_default_is_ten_percent(self):
        self.policy.commission_rate = None
        self.policy.save()
        self.assertEqual(self.policy.commission_rate, Decimal("10.00"))
        self.assertEqual(self.policy.commission_amount, Decimal("100.00"))

    def test_migration_moves_fifteen_percent_policies_to_ten(self):
        producer = InsuranceProducer.objects.create(organization=self.org, name="Pro", default_rate=Decimal("50"))
        InsurancePolicy.objects.filter(pk=self.policy.pk).update(
            commission_rate=Decimal("15.00"),
            commission_amount=Decimal("150.00"),
            producer=producer,
            producer_rate=Decimal("50.00"),
            producer_rate_basis="commission",
            stage="endorsement",
        )
        kept = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.customer,
            policy_number="KEEP-12",
            premium=Decimal("1000.00"),
            commission_rate=Decimal("12.00"),
            stage="bound",
            bound_date=timezone.localdate(),
            start_date=timezone.localdate(),
            end_date=date(timezone.localdate().year + 1, 1, 1),
        )
        migration = importlib.import_module("core.migrations.0222_endorsements_bound_and_commission_default")
        migration.forwards(apps, None)
        self.policy.refresh_from_db()
        kept.refresh_from_db()
        self.assertEqual(self.policy.stage, "bound")
        self.assertEqual(self.policy.commission_rate, Decimal("10.00"))
        self.assertEqual(self.policy.commission_amount, Decimal("100.00"))
        self.assertEqual(self.policy.producer_commission_amount, Decimal("50.00"))
        self.assertEqual(kept.commission_rate, Decimal("12.00"))
        self.assertEqual(kept.commission_amount, Decimal("120.00"))


class WholesalerTests(EndorsementBase):
    def setUp(self):
        super().setUp()
        self.other_company = InsuranceCompany.objects.create(organization=self.org, name="Carrier B")
        self.ws1 = InsuranceWholesaler.objects.create(organization=self.org, name="Wholesale One")
        self.ws2 = InsuranceWholesaler.objects.create(organization=self.org, name="Wholesale Two")
        self.ws1.companies.add(self.company)
        self.ws2.companies.add(self.company, self.other_company)

    def test_same_company_can_sit_under_several_wholesalers(self):
        self.assertEqual(set(self.company.wholesalers.all()), {self.ws1, self.ws2})
        self.assertEqual(wholesaler_for_policy(self.org, self.company, str(self.ws1.id)), self.ws1)
        self.assertIsNone(wholesaler_for_policy(self.org, self.company, ""))
        with self.assertRaises(WholesalerInputError):
            wholesaler_for_policy(self.org, self.other_company, str(self.ws1.id))

    def _add(self, company, wholesaler):
        self.client.force_login(self.owner)
        today = timezone.localdate()
        return self.client.post(
            reverse("add-insurance-policy"),
            {
                "organization": self.org.id,
                "client_name": "Endo Client",
                "insurance_company": company.id,
                "wholesaler": wholesaler,
                "policy_number": "WS-1",
                "premium": "800",
                "broker_fee": "0",
                "stage": "bound",
                "status": "active",
                "bound_date": today.isoformat(),
                "start_date": today.isoformat(),
                "end_date": date(today.year + 1, 1, 1).isoformat(),
                "insurance_period_months": "6",
            },
        )

    def test_add_policy_saves_the_wholesaler(self):
        self._add(self.company, self.ws1.id)
        self.assertEqual(InsurancePolicy.objects.get(policy_number="WS-1").wholesaler, self.ws1)

    def test_add_policy_rejects_a_wholesaler_the_company_is_not_listed_under(self):
        self._add(self.other_company, self.ws1.id)
        self.assertFalse(InsurancePolicy.objects.filter(policy_number="WS-1").exists())

    def test_add_policy_modal_lists_wholesalers_with_their_companies(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("insurance-policies"))
        self.assertContains(response, 'id="policyWholesaler"')
        self.assertContains(response, f'data-companies="{self.company.id},{self.other_company.id}"')

    def test_owner_manages_wholesalers_from_the_companies_page(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("insurance-wholesaler-save"),
            {"name": "Third WS", "companies": [self.company.id, self.other_company.id]},
        )
        third = InsuranceWholesaler.objects.get(name="Third WS")
        self.assertEqual(set(third.companies.all()), {self.company, self.other_company})
        page = self.client.get(reverse("insurance-companies"))
        self.assertContains(page, "Third WS")
        self.assertContains(page, "via Third WS")
        self.client.post(reverse("insurance-wholesaler-delete", args=[third.id]))
        self.assertFalse(InsuranceWholesaler.objects.filter(id=third.id).exists())

    def test_duplicate_wholesaler_name_is_rejected(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("insurance-wholesaler-save"), {"name": "wholesale one"})
        self.assertEqual(InsuranceWholesaler.objects.filter(name__iexact="wholesale one").count(), 1)

    def test_agent_without_finance_cannot_manage_wholesalers(self):
        self.client.force_login(self.agent)
        response = self.client.post(reverse("insurance-wholesaler-save"), {"name": "Sneaky"})
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("insurance-wholesaler-delete", args=[self.ws1.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(InsuranceWholesaler.objects.filter(id=self.ws1.id).exists())


class ProducerPageTests(EndorsementBase):
    def test_producer_page_shows_the_new_forms(self):
        producer = InsuranceProducer.objects.create(organization=self.org, name="Sara Ahmed", default_rate=Decimal("20"))
        self.client.force_login(self.owner)
        response = self.client.get(reverse("insurance-producer-detail", args=[producer.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No portal login yet")
        self.assertContains(response, 'class="prd-segment"')
        self.assertContains(response, 'id="rpSummary"')
