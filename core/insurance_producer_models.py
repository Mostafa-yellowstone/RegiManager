"""Insurance producers: outside/inside sellers paid a share of each policy they bring in."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class InsuranceProducer(models.Model):
    class RateBasis(models.TextChoices):
        COMMISSION = "commission", "% of agency commission"
        PREMIUM = "premium", "% of premium"

    class PayoutMode(models.TextChoices):
        ONCE = "once", "Paid once (full amount)"
        MONTHLY = "monthly", "Paid monthly"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_producers",
    )
    name = models.CharField(max_length=160)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    license_number = models.CharField(max_length=80, blank=True, default="")
    default_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Default producer percentage, copied to each new policy (editable per policy).",
    )
    rate_basis = models.CharField(
        max_length=20,
        choices=RateBasis.choices,
        default=RateBasis.COMMISSION,
    )
    default_payout = models.CharField(
        max_length=20,
        choices=PayoutMode.choices,
        default=PayoutMode.ONCE,
    )
    notes = models.TextField(blank=True, default="")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_producer",
        help_text="Login used by the producer to open their read-only portal.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_insurance_producer_org_name",
            )
        ]
        verbose_name = "Insurance producer"
        verbose_name_plural = "Insurance producers"

    def __str__(self):
        return self.name

    @property
    def initials(self) -> str:
        parts = [p for p in (self.name or "").split() if p]
        if not parts:
            return "P"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class InsuranceProducerPayout(models.Model):
    """Money paid to a producer for one policy (negative amount = deduction / recovery)."""

    class Kind(models.TextChoices):
        PAYMENT = "payment", "Payment"
        DEDUCTION = "deduction", "Deduction (cancelled policy)"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        ZELLE = "zelle", "Zelle"
        CHECK = "check", "Check"
        BANK = "bank", "Bank transfer"
        OFFSET = "offset", "Offset"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_producer_payouts",
    )
    producer = models.ForeignKey(
        InsuranceProducer,
        on_delete=models.CASCADE,
        related_name="payouts",
    )
    policy = models.ForeignKey(
        "InsurancePolicy",
        on_delete=models.CASCADE,
        related_name="producer_payouts",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PAYMENT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField()
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    batch_reference = models.CharField(max_length=40, blank=True, default="")
    bank_transaction = models.ForeignKey(
        "BankTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="producer_payouts",
        help_text="Bank entry recorded for this payout (shared by every row of a settlement).",
    )
    note = models.CharField(max_length=255, blank=True, default="")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-id"]
        indexes = [
            models.Index(fields=["producer", "policy"], name="core_prodpay_prod_pol_idx"),
            models.Index(fields=["organization", "paid_on"], name="core_prodpay_org_date_idx"),
        ]
        verbose_name = "Producer payout"
        verbose_name_plural = "Producer payouts"

    def __str__(self):
        return f"{self.producer} {self.amount} on {self.paid_on}"


class InsurancePolicyPremiumChange(models.Model):
    """Premium history for a policy (endorsements), so commission changes are traceable."""

    policy = models.ForeignKey(
        "InsurancePolicy",
        on_delete=models.CASCADE,
        related_name="premium_changes",
    )
    old_premium = models.DecimalField(max_digits=12, decimal_places=2)
    new_premium = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Policy premium change"
        verbose_name_plural = "Policy premium changes"

    @property
    def difference(self) -> Decimal:
        return (self.new_premium or Decimal("0")) - (self.old_premium or Decimal("0"))
