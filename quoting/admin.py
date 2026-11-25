from django.contrib import admin

from quoting.models import QuoteAttempt, QuoteJob


class QuoteAttemptInline(admin.TabularInline):
    model = QuoteAttempt
    extra = 0
    can_delete = False
    readonly_fields = (
        "carrier_key",
        "carrier_name",
        "status",
        "blocker_code",
        "detail",
        "missing",
        "quote_number",
        "term_premium",
        "term_months",
        "source",
    )


@admin.register(QuoteJob)
class QuoteJobAdmin(admin.ModelAdmin):
    list_display = ("applicant_label", "mode", "status", "organization", "created_at")
    list_filter = ("mode", "status", "jurisdiction")
    readonly_fields = ("created_at",)
    inlines = [QuoteAttemptInline]
