"""Tests for TLC payment capture and receipt generation."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Organization, OrganizationMembership, Space
from core.tlc_models import TLCInstallment, TLCPaymentTransaction, TLCPolicy, TLCReceipt
from core.tlc_payments import record_tlc_payment

User = get_user_model()


class TLCPaymentReceiptTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Xpress Insurance Solutions Inc.",
            city="Queens",
            state="NY",
            insurance_intake_display_name="Xpress Insurance Solutions",
        )
        self.owner = User.objects.create_user(username="tlcpay", password="pass12345")
        self.membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
            can_view_spaces=True,
            can_deal_with_tlc=True,
        )
        self.space = Space.objects.create(organization=self.org, key="tlc", label="TLC")
        self.membership.accessible_spaces.add(self.space)
        self.policy = TLCPolicy.objects.create(
            organization=self.org,
            space=self.space,
            policy_number="PCA-PAY-1",
            named_insured="Test Driver",
            status=TLCPolicy.Status.ACTIVE,
            carrier="Hereford Insurance Company",
            added_by=self.owner,
        )
        self.installment = TLCInstallment.objects.create(
            policy=self.policy,
            installment_number=1,
            due_date="2026-04-24",
            amount=Decimal("383.46"),
            installment_fee=Decimal("20.00"),
            balance=Decimal("403.46"),
            notes="Bill # 1",
        )
        self.client.login(username="tlcpay", password="pass12345")
        session = self.client.session
        session["active_organization_id"] = self.org.id
        session.save()

    def test_record_payment_marks_installment_and_creates_receipt(self):
        txn, receipt = record_tlc_payment(
            self.policy,
            user=self.owner,
            payment_date=self.installment.due_date,
            installment_id=self.installment.id,
            splits=[
                {
                    "payment_method": "visa",
                    "amount": Decimal("300.00"),
                    "reference_number": "AUTH1",
                    "approval_number": "APP1",
                    "last_four": "4588",
                    "notes": "Approved",
                    "sort_order": 0,
                },
                {
                    "payment_method": "cash",
                    "amount": Decimal("103.46"),
                    "reference_number": "R441",
                    "approval_number": "",
                    "last_four": "",
                    "notes": "Received",
                    "sort_order": 1,
                },
            ],
        )
        self.installment.refresh_from_db()
        self.assertTrue(self.installment.is_paid)
        self.assertEqual(self.installment.payment_date, self.installment.due_date)
        self.assertEqual(txn.transaction_type, TLCPaymentTransaction.TransactionType.SPLIT_PAYMENT)
        self.assertEqual(txn.splits.count(), 2)
        self.assertTrue(receipt.receipt_number.startswith("XIS-"))
        self.assertTrue(receipt.pdf_file)
        self.assertEqual(receipt.snapshot_json["payment"]["amount_received"], "403.46")

    def test_collect_payment_view_creates_invoice(self):
        response = self.client.post(
            reverse("record-tlc-payment", args=[self.policy.id]),
            {
                "installment_id": str(self.installment.id),
                "payment_date": "2026-04-24",
                "payment_time": "14:30",
                "split_method": ["cash"],
                "split_amount": ["403.46"],
                "split_reference": [""],
                "split_approval": [""],
                "split_last_four": [""],
                "split_notes": [""],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TLCReceipt.objects.filter(policy=self.policy).exists())
        detail = self.client.get(
            reverse("tlc-policy-detail", args=[self.space.id, self.policy.id]) + "?tab=invoices"
        )
        self.assertContains(detail, "Invoices")
        receipt = TLCReceipt.objects.get(policy=self.policy)
        self.assertContains(detail, receipt.receipt_number)
        pdf = self.client.get(reverse("tlc-receipt-pdf", args=[receipt.id]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
