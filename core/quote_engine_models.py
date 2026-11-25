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
