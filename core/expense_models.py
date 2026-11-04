"""Operating expenses and customizable expense categories for Financial Intelligence BI."""

from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

DEFAULT_EXPENSE_LABELS = [
    "Rent & Lease",
    "Utilities & Electric",
    "Office Supplies & Printing",
    "Software & Subscriptions",
    "Salaries & Payroll",
    "Marketing & Advertising",
    "Insurance & Legal",
    "Merchant & Bank Fees",
    "Repairs & Maintenance",
    "Miscellaneous",
]


class ExpenseLabel(models.Model):
    """
    Categorization label for operating expenses (e.g. Rent, Utilities, Software, Office Supplies).
    Scoped per organization so each agency can customize their expense categories dynamically.
    """

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="expense_labels",
    )
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_org_expense_label",
            )
        ]
        verbose_name = "Expense Label"
        verbose_name_plural = "Expense Labels"

    def __str__(self):
        return self.name


class Expense(models.Model):
    """
    Operational expense record deducted from DMV gross profit to calculate Net Profit.
    """

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    label = models.ForeignKey(
        ExpenseLabel,
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField(default=timezone.now, db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_expenses",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        indexes = [
            models.Index(fields=["organization", "expense_date"], name="core_expense_org_date_idx"),
        ]

    def __str__(self):
        return f"{self.label.name}: ${self.amount} ({self.expense_date})"


def ensure_default_expense_labels(organization):
    """Ensure standard starter expense labels exist for an organization."""
    if not organization:
        return
    existing = set(
        ExpenseLabel.objects.filter(organization=organization).values_list("name", flat=True)
    )
    to_create = [
        ExpenseLabel(organization=organization, name=name)
        for name in DEFAULT_EXPENSE_LABELS
        if name not in existing
    ]
    if to_create:
        ExpenseLabel.objects.bulk_create(to_create, ignore_conflicts=True)
