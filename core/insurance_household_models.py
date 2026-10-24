"""Households (clients grouped under one roof) and the status of each client's coverage gaps."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class InsuranceHousehold(models.Model):
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_households",
    )
    name = models.CharField(max_length=160)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_households_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InsuranceHouseholdMember(models.Model):
    class Relationship(models.TextChoices):
        PRIMARY = "primary", "Primary"
        SPOUSE = "spouse", "Spouse / partner"
        CHILD = "child", "Child"
        PARENT = "parent", "Parent"
        RELATIVE = "relative", "Relative"
        ROOMMATE = "roommate", "Roommate"
        BUSINESS = "business", "Business"
        OTHER = "other", "Other"

    household = models.ForeignKey(InsuranceHousehold, on_delete=models.CASCADE, related_name="members")
    client = models.OneToOneField(
        "Client",
        on_delete=models.CASCADE,
        related_name="household_membership",
    )
    relationship = models.CharField(max_length=20, choices=Relationship.choices, default=Relationship.OTHER)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_household_members_added",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at", "id"]

    def __str__(self):
        return f"{self.client_id} in {self.household}"


class InsuranceHouseholdDismissal(models.Model):
    """A suggested pair an agent marked as "not related"; never suggested again."""

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_household_dismissals",
    )
    client_low = models.ForeignKey("Client", on_delete=models.CASCADE, related_name="+")
    client_high = models.ForeignKey("Client", on_delete=models.CASCADE, related_name="+")
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["client_low", "client_high"], name="uniq_household_dismissal_pair"),
        ]


class InsuranceCoverageGapStatus(models.Model):
    class Status(models.TextChoices):
        DISMISSED = "dismissed", "Dismissed"
        QUOTED = "quoted", "Quote requested"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_coverage_gap_statuses",
    )
    client = models.ForeignKey("Client", on_delete=models.CASCADE, related_name="coverage_gap_statuses")
    gap_key = models.CharField(max_length=60)
    status = models.CharField(max_length=20, choices=Status.choices)
    lead = models.ForeignKey(
        "InsuranceQuoteLead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coverage_gap_statuses",
    )
    note = models.CharField(max_length=300, blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["client", "gap_key"], name="uniq_coverage_gap_status"),
        ]

    def __str__(self):
        return f"{self.client_id} · {self.gap_key} · {self.status}"
