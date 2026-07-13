"""Tests for TLC unified accounting engine."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Organization, Space
from core.tlc_accounting import (
    apply_cancellation_accounting,
    apply_endorsement_accounting,
    build_accounting_snapshot,
    policy_commission_earned,
    policy_expected_commission,
    policy_written_premium,
    prepare_endorsement_amounts,
    sync_installment_accounting,
)
from core.tlc_installments import build_installment_row
from core.tlc_models import (
    TLCEndorsement,
    TLCInstallment,
    TLCPolicy,
    TLCPremiumBreakdown,
)
from core.tlc_profitability import build_policy_profitability


class TLCAccountingTests(TestCase):
    def setUp(self):
        org = Organization.objects.create(name="Acct Org", city="NY", state="NY")
        space = Space.objects.create(organization=org, key="tlc", label="TLC")
        self.policy = TLCPolicy.objects.create(
            organization=org,
            space=space,
            policy_number="ACCT-001",
            status=TLCPolicy.Status.ACTIVE,
            commission_rate=Decimal("10.00"),
            effective_date=date(2026, 1, 1),
            expiration_date=date(2027, 1, 1),
        )
        TLCPremiumBreakdown.objects.create(
            policy=self.policy,
            total_written_premium=Decimal("1000.00"),
            down_payment=Decimal("200.00"),
            monthly_installment=Decimal("100.00"),
            number_of_installments=8,
            installment_fee=Decimal("5.00"),
        )
        self.policy.save()

    def _add_paid_installment(self, number: int, gross: str, *, fee: str = "5.00") -> TLCInstallment:
        row = build_installment_row(
            self.policy,
            Decimal(gross),
            installment_fee=Decimal(fee),
            apply_fee=number > 1,
        )
        return TLCInstallment.objects.create(
            policy=self.policy,
            installment_number=number,
            due_date=date(2026, number, 1),
            amount=row["amount"],
            installment_fee=row["installment_fee"],
            commission_amount=row["commission_amount"],
            is_paid=True,
            payment_date=date(2026, number, 2),
            balance=Decimal("0.00"),
            notes="DEPOSIT" if number == 1 else f"BILL # {number - 1}",
        )

    def test_endorsement_updates_written_premium_and_expected_commission(self):
        from core.tlc_accounting import prepare_endorsement_amounts

        amounts = prepare_endorsement_amounts(
            self.policy,
            new_written_premium=Decimal("1100.00"),
            endorsement_fee=Decimal("25.00"),
            commission_difference=Decimal("10.00"),
        )
        TLCEndorsement.objects.create(
            policy=self.policy,
            premium_difference=amounts["premium_difference"],
            written_premium_before=amounts["written_premium_before"],
            written_premium_after=amounts["written_premium_after"],
            endorsement_fee=amounts["endorsement_fee"],
            commission_difference=amounts["commission_difference"],
        )
        apply_endorsement_accounting(self.policy)
        self.policy.refresh_from_db()
        self.assertEqual(policy_written_premium(self.policy), Decimal("1100.00"))
        self.assertEqual(policy_expected_commission(self.policy), Decimal("110.00"))

    def test_endorsement_decrease_written_premium(self):
        amounts = prepare_endorsement_amounts(
            self.policy,
            new_written_premium=Decimal("900.00"),
        )
        self.assertEqual(amounts["premium_difference"], Decimal("-100.00"))
        self.assertEqual(amounts["written_premium_after"], Decimal("900.00"))

    def test_paid_installments_roll_into_collections_and_earned_commission(self):
        self._add_paid_installment(1, "200.00", fee="0.00")
        self._add_paid_installment(2, "105.00")
        sync_installment_accounting(self.policy)
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.amount_collected_from_client, Decimal("305.00"))
        self.assertEqual(policy_commission_earned(self.policy), Decimal("30.00"))

    def test_cancellation_records_unearned_commission_and_voids_future_bills(self):
        self._add_paid_installment(1, "200.00", fee="0.00")
        TLCInstallment.objects.create(
            policy=self.policy,
            installment_number=2,
            due_date=date(2026, 6, 1),
            amount=Decimal("95.00"),
            installment_fee=Decimal("5.00"),
            commission_amount=Decimal("9.50"),
            balance=Decimal("100.00"),
        )
        metrics = apply_cancellation_accounting(self.policy, date(2026, 7, 1))
        self.policy.refresh_from_db()
        self.assertGreater(metrics["unearned_commission"], Decimal("0.00"))
        self.assertGreater(metrics["return_premium"], Decimal("0.00"))
        self.assertEqual(self.policy.commission_chargeback, metrics["unearned_commission"])
        future = self.policy.installments.get(installment_number=2)
        self.assertEqual(future.balance, Decimal("0.00"))

    def test_profitability_does_not_double_count_commission(self):
        self._add_paid_installment(1, "200.00", fee="0.00")
        self._add_paid_installment(2, "105.00")
        snapshot = build_policy_profitability(self.policy)
        gross = Decimal(snapshot["gross_agency_revenue"])
        earned = Decimal(snapshot["commission_earned"])
        installment_commission = Decimal(snapshot["installment_commission_collected"])
        fees = Decimal(snapshot["installment_fees_collected"])
        self.assertEqual(earned, installment_commission)
        self.assertEqual(gross, earned + fees)

    def test_accounting_snapshot_pending_commission_after_partial_payment(self):
        self._add_paid_installment(1, "200.00", fee="0.00")
        snap = build_accounting_snapshot(self.policy)
        self.assertEqual(snap["expected_commission"], Decimal("100.00"))
        self.assertEqual(snap["earned_commission"], Decimal("20.00"))
        self.assertEqual(snap["pending_commission"], Decimal("80.00"))
