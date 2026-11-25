"""Saved quote jobs. Portal passwords are not a field on these models."""

from django.conf import settings
from django.db import models


class QuoteJob(models.Model):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="ny_auto_quote_jobs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ny_auto_quote_jobs",
    )
    mode = models.CharField(max_length=16)
    line = models.CharField(max_length=40)
    jurisdiction = models.CharField(max_length=2)
    status = models.CharField(max_length=32)
    applicant_label = models.CharField(max_length=200, blank=True, default="")
    intake = models.JSONField(default=dict, blank=True)
    missing = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "NY auto quote job"
        verbose_name_plural = "NY auto quote jobs"

    def __str__(self):
        return f"{self.applicant_label or 'Quote'} · {self.status}"


class QuoteAttempt(models.Model):
    job = models.ForeignKey(QuoteJob, on_delete=models.CASCADE, related_name="attempts")
    carrier_key = models.CharField(max_length=40)
    carrier_name = models.CharField(max_length=120)
    status = models.CharField(max_length=32)
    blocker_code = models.CharField(max_length=64, blank=True, default="")
    detail = models.TextField(blank=True, default="")
    missing = models.JSONField(default=list, blank=True)
    quote_number = models.CharField(max_length=64, blank=True, default="")
    term_premium = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    term_months = models.PositiveSmallIntegerField(null=True, blank=True)
    source = models.CharField(max_length=16, blank=True, default="")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.carrier_name} · {self.status}"
