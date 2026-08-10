"""Internal Fundamental Quote Pipeline models (replaces public insurance intake)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class InsuranceQuoteLead(models.Model):
    """Fundamental quote lead captured inside Insurance Space."""

    class Stage(models.TextChoices):
        NEW = "new", "New"
        ASSIGNED = "assigned", "Assigned"
        QUOTING = "quoting", "Quoting"
        QUOTED = "quoted", "Quoted"
        WON = "won", "Won"
        LOST = "lost", "Lost"
        CANCELLED = "cancelled", "Cancelled"

    class AssignmentMode(models.TextChoices):
        AUTO = "auto", "Auto"
        MANUAL = "manual", "Manual"
        UNASSIGNED = "unassigned", "Unassigned"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_quote_leads",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_quote_leads_created",
    )
    client_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True, default="")
    insurance_type = models.CharField(max_length=40, blank=True, default="")
    has_prior = models.BooleanField(default=False)
    is_experienced = models.BooleanField(default=False)
    has_accident = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    recommended_companies = models.ManyToManyField(
        "InsuranceCompany",
        blank=True,
        related_name="recommended_on_quote_leads",
    )
    stage = models.CharField(
        max_length=20,
        choices=Stage.choices,
        default=Stage.NEW,
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        "OrganizationMembership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_quote_leads",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    assignment_mode = models.CharField(
        max_length=20,
        choices=AssignmentMode.choices,
        default=AssignmentMode.UNASSIGNED,
    )
    agent_task = models.ForeignKey(
        "AgentTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_leads",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Insurance quote lead"
        verbose_name_plural = "Insurance quote leads"
        indexes = [
            models.Index(fields=["organization", "stage", "-created_at"]),
            models.Index(fields=["organization", "assigned_to", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.client_name} · {self.insurance_type or 'quote'}"


class InsuranceQuoteDistributionConfig(models.Model):
    """Per-org smart distribution settings for quote leads."""

    organization = models.OneToOneField(
        "Organization",
        on_delete=models.CASCADE,
        related_name="quote_distribution_config",
    )
    is_auto_enabled = models.BooleanField(default=True)
    skip_sundays = models.BooleanField(
        default=True,
        help_text="Pause auto-distribution on Sundays (America/New_York).",
    )
    require_attendance_present = models.BooleanField(
        default=True,
        help_text="Exclude agents with no open attendance check-in for the work day.",
    )
    last_assigned_membership = models.ForeignKey(
        "OrganizationMembership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quote distribution config"
        verbose_name_plural = "Quote distribution configs"

    def __str__(self):
        return f"Quote distribution · {self.organization_id}"


class InsuranceAgentOffDay(models.Model):
    """Owner/Manager-scheduled off day — agent excluded from auto distribution."""

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_agent_off_days",
    )
    membership = models.ForeignKey(
        "OrganizationMembership",
        on_delete=models.CASCADE,
        related_name="insurance_off_days",
    )
    off_date = models.DateField(db_index=True)
    reason = models.CharField(max_length=200, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-off_date"]
        verbose_name = "Insurance agent off day"
        verbose_name_plural = "Insurance agent off days"
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "off_date"],
                name="uniq_insurance_agent_off_day",
            )
        ]

    def __str__(self):
        return f"{self.membership_id} off {self.off_date}"
