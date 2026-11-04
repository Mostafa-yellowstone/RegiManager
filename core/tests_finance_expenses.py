from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Organization,
    OrganizationMembership,
    ServiceRecord,
    Expense,
    ExpenseLabel,
)
from core.expense_models import ensure_default_expense_labels


@override_settings(SECURE_SSL_REDIRECT=False)
class FinanceExpensesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner_user",
            email="owner@example.com",
            password="testpassword123",
        )
        self.organization = Organization.objects.create(
            name="Alpha DMV Services",
            is_active=True,
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
            can_view_reports=True,
        )
        self.client = Client()
        self.client.login(username="owner_user", password="testpassword123")

    def test_ensure_default_labels_and_creation(self):
        ensure_default_expense_labels(self.organization)
        labels = ExpenseLabel.objects.filter(organization=self.organization)
        self.assertGreater(labels.count(), 0)
        self.assertTrue(labels.filter(name="Rent & Lease").exists())

    def test_add_expense_label_ajax(self):
        url = reverse("finance-add-expense-label")
        response = self.client.post(
            url,
            {"name": "Coffee & Snacks", "organization_id": self.organization.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["label"]["name"], "Coffee & Snacks")
        self.assertTrue(ExpenseLabel.objects.filter(name="Coffee & Snacks", organization=self.organization).exists())

    def test_save_expense_and_net_profit_calculation(self):
        label = ExpenseLabel.objects.create(
            organization=self.organization,
            name="Office Supplies",
        )

        # Create a ServiceRecord with processing fee (DMV Gross Profit = $150.00)
        ServiceRecord.objects.create(
            organization=self.organization,
            handled_by=self.user,
            service_type="vehicle_registration",
            status="completed",
            service_fee=Decimal("200.00"),
            processing_fee=Decimal("150.00"),
            transaction_date=timezone.localdate(),
        )

        # Save an expense ($50.00)
        save_url = reverse("finance-save-expense")
        response = self.client.post(
            save_url,
            {
                "label_id": label.id,
                "amount": "50.00",
                "expense_date": timezone.localdate().strftime("%Y-%m-%d"),
                "description": "Printer ink",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")

        # Verify expense in DB
        self.assertEqual(Expense.objects.count(), 1)
        exp = Expense.objects.first()
        self.assertEqual(exp.amount, Decimal("50.00"))

        # Verify finance hub computes gross profit ($150) - expenses ($50) = net profit ($100)
        hub_url = reverse("finance-hub")
        hub_response = self.client.get(hub_url)
        self.assertEqual(hub_response.status_code, 200)
        self.assertEqual(hub_response.context["dmv_gross_profit"], Decimal("150.00"))
        self.assertEqual(hub_response.context["total_expenses"], Decimal("50.00"))
        self.assertEqual(hub_response.context["net_profit"], Decimal("100.00"))

    def test_delete_expense(self):
        label = ExpenseLabel.objects.create(
            organization=self.organization,
            name="Utilities",
        )
        expense = Expense.objects.create(
            organization=self.organization,
            label=label,
            amount=Decimal("75.00"),
            created_by=self.user,
        )

        delete_url = reverse("finance-delete-expense", kwargs={"expense_id": expense.id})
        response = self.client.post(delete_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Expense.objects.filter(id=expense.id).exists())
