"""History of quote engine runs. Stores validation issues and results only, never the request (it holds license numbers and VINs)."""
from django.conf import settings
from django.db import models


class QuoteEngineRun(models.Model):
    lead = models.ForeignKey("InsuranceQuoteLead", on_delete=models.CASCADE, related_name="engine_runs")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    line_of_business = models.CharField(max_length=20, blank=True, default="")
    blocked = models.BooleanField(default=False)
    issues = models.JSONField(default=list, blank=True)
    results = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class QuoteEngineJob(models.Model):
    """A quote run in the background. It can wait for a person to type the carrier login code.

    The code is stored encrypted only while it is needed and is cleared as soon as the run reads it.
    """

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        WAITING_OTP = "waiting_otp", "Waiting for the login code"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    lead = models.ForeignKey("InsuranceQuoteLead", on_delete=models.CASCADE, related_name="engine_jobs")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING, db_index=True)
    spend_approved = models.BooleanField(default=False)
    otp_carrier = models.CharField(max_length=60, blank=True, default="")
    otp_hint_email = models.CharField(max_length=200, blank=True, default="", help_text="Display only: where the code is sent.")
    otp_code_enc = models.TextField(blank=True, default="")
    otp_cancelled = models.BooleanField(default=False)
    message = models.CharField(max_length=300, blank=True, default="")
    run = models.ForeignKey(QuoteEngineRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
