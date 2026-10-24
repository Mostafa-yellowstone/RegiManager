"""DMV-to-insurance radar: insurance opportunities found in the office's DMV work."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class InsuranceRadarItem(models.Model):
    class Signal(models.TextChoices):
        NEW_REGISTRATION = "new_registration", "New registration"
        OUTSIDE_EXPIRING = "outside_expiring", "Insured elsewhere, expiring"
        REGISTRATION_RENEWAL = "registration_renewal", "Registration renewal"
        PLATES_SURRENDERED = "plates_surrendered", "Plates surrendered"
        DMV_ONLY = "dmv_only", "DMV-only client"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DONE = "done", "Done"
        DISMISSED = "dismissed", "Dismissed"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_radar_items",
    )
    client = models.ForeignKey("Client", on_delete=models.CASCADE, related_name="radar_items")
    vehicle = models.ForeignKey(
        "Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="radar_items",
    )
    service_record = models.ForeignKey(
        "ServiceRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="radar_items",
    )
    policy = models.ForeignKey(
        "InsurancePolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="radar_items",
    )
    signal = models.CharField(max_length=30, choices=Signal.choices)
    signal_key = models.CharField(max_length=80)
    signal_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=300, blank=True, default="")
    referred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_radar_referrals",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_radar_items",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    won = models.BooleanField(default=False)
    note = models.TextField(blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "signal_key"], name="uniq_radar_signal_per_org"),
        ]
        indexes = [models.Index(fields=["organization", "status", "signal"])]

    def __str__(self):
        return f"{self.get_signal_display()} · {self.client_id}"

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.OPEN
