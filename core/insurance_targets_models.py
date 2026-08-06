"""Insurance monthly targets, per-LOB goals, and market premium assumptions."""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class InsuranceMonthlyTarget(models.Model):
    """Organization-level premium/commission goals for a calendar month."""

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_monthly_targets",
    )
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    premium_target = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commission_target = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, blank=True
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "year", "month"],
                name="uniq_insurance_monthly_target_org_ym",
            )
        ]
        verbose_name = "Insurance monthly target"
        verbose_name_plural = "Insurance monthly targets"

    def __str__(self):
        return f"{self.organization_id} {self.year}-{self.month:02d}"


class InsuranceLineTarget(models.Model):
    """Per line-of-business target within a monthly goal."""

    monthly_target = models.ForeignKey(
        InsuranceMonthlyTarget,
        on_delete=models.CASCADE,
        related_name="line_targets",
    )
    insurance_type = models.CharField(max_length=50, db_index=True)
    premium_target = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commission_target = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, blank=True
    )
    market_avg_premium = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional market assumption used by the planner for this month.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["insurance_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["monthly_target", "insurance_type"],
                name="uniq_insurance_line_target_month_type",
            )
        ]
        verbose_name = "Insurance line target"
        verbose_name_plural = "Insurance line targets"

    def __str__(self):
        return f"{self.monthly_target_id}:{self.insurance_type}"


class InsuranceMarketPremiumAssumption(models.Model):
    """Org-level default market average premium per insurance type."""

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_market_assumptions",
    )
    insurance_type = models.CharField(max_length=50, db_index=True)
    avg_premium = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["insurance_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "insurance_type"],
                name="uniq_insurance_market_assumption_org_type",
            )
        ]
        verbose_name = "Insurance market premium assumption"
        verbose_name_plural = "Insurance market premium assumptions"

    def __str__(self):
        return f"{self.organization_id}:{self.insurance_type}=${self.avg_premium}"
