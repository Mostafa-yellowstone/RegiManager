"""Tests for transaction fee math and outstanding balance accuracy."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client as TestClient, TestCase
from django.urls import reverse

from core.models import Client, Organization, OrganizationMembership, Referral, ServiceRecord, Vehicle
from core.transaction_amounts import (
    apply_transaction_amounts,
    compute_credit_card_fee,
    compute_referral_balance,
    compute_service_fee,
    quantize_money,
)


class TransactionAmountMathTests(TestCase):
    def test_quantize_half_up(self):
        self.assertEqual(quantize_money("10.004"), Decimal("10.00"))
        self.assertEqual(quantize_money("10.005"), Decimal("10.01"))

    def test_single_cc_fee_on_full_base(self):
        base = Decimal("100.00")
        self.assertEqual(
            compute_credit_card_fee(base_total=base, payment_method="visa"),
            Decimal("3.50"),
        )

    def test_split_cc_fee_on_each_paid_portion(self):
        cc = compute_credit_card_fee(
            base_total=Decimal("200.00"),
            payment_method="visa",
            payment_method_2="cash",
            paid_amount=Decimal("103.50"),
            paid_amount_2=Decimal("50.00"),
        )
        self.assertEqual(cc, Decimal("1.81"))

    def test_sub_penny_dust_snaps_to_zero_not_one_cent(self):
        self.assertEqual(
            compute_referral_balance(Decimal("100.00"), Decimal("99.996")),
            Decimal("0.00"),
        )

    def test_genuine_one_cent_balance_preserved(self):
        self.assertEqual(
            compute_referral_balance(Decimal("100.01"), Decimal("100.00")),
            Decimal("0.01"),
        )

    def test_overpayment_stays_negative(self):
        self.assertEqual(
            compute_referral_balance(Decimal("100.00"), Decimal("120.00")),
            Decimal("-20.00"),
        )

    def test_apply_transaction_amounts_full_pay_visa_zero_balance(self):
        record = ServiceRecord(
            processing_fee=Decimal("86.15"),
            payment_method="visa",
            paid_amount=Decimal("89.17"),
        )
        apply_transaction_amounts(record)
        self.assertEqual(record.credit_card_fee, Decimal("3.02"))
        self.assertEqual(record.service_fee, Decimal("89.17"))
        self.assertEqual(record.referral_balance, Decimal("0.00"))
        self.assertTrue(record.is_referral_paid)


class TransactionBalanceViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="balanceuser", password="password123")
        self.org = Organization.objects.create(name="Balance Org", city="NYC")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
        )
        self.referral = Referral.objects.create(
            organization=self.org,
            name="Metro Dealer",
            category="dealer",
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Pat",
            last_name="Driver",
            referral=self.referral,
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="BALVIN0000000001",
            vehicle_number="VEH-BAL-1",
        )
        self.http = TestClient()
        self.http.login(username="balanceuser", password="password123")

    def _post_transaction(self, **extra):
        data = {
            "transaction_date": "2026-06-15",
            "service_type": "vehicle_registration",
            "status": "pending",
            "payment_method": "cash",
            "payment_method_2": "",
            "paid_amount_2": "",
            "terminal_number": "",
            "transaction_type": "OLRS",
            "processing_fee": "100.00",
            "dmv_fee": "50.00",
            "sales_tax": "10.00",
            "dmv_sales_tax": "5.00",
            "credit_card_fee": "0.00",
            "other_fees": "0.00",
            "other_dmv_fee": "0.00",
            "paid_amount": "165.00",
            "referral_balance": "0.01",
            "notes": "",
        }
        data.update(extra)
        return self.http.post(reverse("start-process", args=[self.vehicle.id]), data)

    def test_full_cash_payment_has_zero_outstanding(self):
        response = self._post_transaction()
        self.assertEqual(response.status_code, 302)
        record = ServiceRecord.objects.get(vehicle=self.vehicle)
        self.assertEqual(record.service_fee, Decimal("165.00"))
        self.assertEqual(record.paid_amount, Decimal("165.00"))
        self.assertEqual(record.referral_balance, Decimal("0.00"))
        self.assertTrue(record.is_referral_paid)

    def test_full_visa_payment_has_zero_outstanding(self):
        base = Decimal("86.15")
        cc = compute_credit_card_fee(base_total=base, payment_method="visa")
        grand = base + cc
        response = self._post_transaction(
            processing_fee="86.15",
            dmv_fee="0.00",
            sales_tax="0.00",
            dmv_sales_tax="0.00",
            payment_method="visa",
            paid_amount=str(grand),
            credit_card_fee=str(cc),
        )
        self.assertEqual(response.status_code, 302)
        record = ServiceRecord.objects.get(vehicle=self.vehicle)
        self.assertEqual(record.credit_card_fee, cc)
        self.assertEqual(record.service_fee, grand)
        self.assertEqual(record.referral_balance, Decimal("0.00"))
        self.assertTrue(record.is_referral_paid)

    def test_partial_payment_keeps_correct_balance(self):
        response = self._post_transaction(paid_amount="100.00")
        self.assertEqual(response.status_code, 302)
        record = ServiceRecord.objects.get(vehicle=self.vehicle)
        self.assertEqual(record.referral_balance, Decimal("65.00"))
        self.assertFalse(record.is_referral_paid)

    def test_js_style_rounded_cc_fee_post_still_zeros_balance(self):
        """Simulate browser-posted fee strings that previously left $0.01 outstanding."""
        response = self._post_transaction(
            processing_fee="86.15",
            dmv_fee="0.00",
            sales_tax="0.00",
            dmv_sales_tax="0.00",
            payment_method="visa",
            credit_card_fee="3.02",
            paid_amount="89.17",
            referral_balance="0.01",
        )
        self.assertEqual(response.status_code, 302)
        record = ServiceRecord.objects.get(vehicle=self.vehicle)
        self.assertEqual(record.referral_balance, Decimal("0.00"))
        self.assertTrue(record.is_referral_paid)

    def test_split_payment_full_pay_zero_balance(self):
        p2_base = Decimal("50.00")
        p1_base = Decimal("100.00")
        fee1 = quantize_money(p1_base * Decimal("0.035"))
        fee2 = Decimal("0.00")
        p2_inclusive = p2_base + fee2
        p1_inclusive = p1_base + fee1
        total_paid = p1_inclusive + p2_inclusive
        cc_total = fee1 + fee2
        response = self._post_transaction(
            processing_fee="150.00",
            dmv_fee="0.00",
            sales_tax="0.00",
            dmv_sales_tax="0.00",
            payment_method="visa",
            payment_method_2="cash",
            paid_amount=str(total_paid),
            paid_amount_2=str(p2_inclusive),
            credit_card_fee=str(cc_total),
            referral_balance="0.00",
        )
        self.assertEqual(response.status_code, 302)
        record = ServiceRecord.objects.get(vehicle=self.vehicle)
        self.assertEqual(record.referral_balance, Decimal("0.00"))
        self.assertTrue(record.is_referral_paid)

    def test_saved_record_recomputes_service_fee_on_resave(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            processing_fee=Decimal("100.00"),
            payment_method="visa",
            paid_amount=Decimal("103.50"),
        )
        record.refresh_from_db()
        self.assertEqual(record.credit_card_fee, Decimal("3.50"))
        self.assertEqual(compute_service_fee(record), Decimal("103.50"))
        self.assertEqual(record.referral_balance, Decimal("0.00"))
