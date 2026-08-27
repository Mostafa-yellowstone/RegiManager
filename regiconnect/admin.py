from django.contrib import admin

from .models import (
    Appointment,
    BindTransaction,
    CanonicalQuote,
    CertificationRun,
    Connection,
    Connector,
    ConnectorJob,
    DeadLetterItem,
    MarketProfile,
    PolicyConnectivity,
    ProducerCode,
    QuoteLeadConnectivity,
    RatingJob,
    RatingRequest,
    Submission,
)


@admin.register(Connector)
class ConnectorAdmin(admin.ModelAdmin):
    list_display = ("slug", "display_name", "version", "missing_carrier_spec")


@admin.register(MarketProfile)
class MarketProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "company", "market_type", "market_channel", "status")
    list_filter = ("status", "market_type", "market_channel")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "market", "state", "status")


@admin.register(ProducerCode)
class ProducerCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "organization", "market", "state")


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "market", "connector", "environment", "status")
    exclude = ()
    readonly_fields = ("credential_reference",)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "status", "external_reference", "created_at")


@admin.register(ConnectorJob)
class ConnectorJobAdmin(admin.ModelAdmin):
    list_display = ("id", "operation", "status", "attempt", "correlation_id")


@admin.register(DeadLetterItem)
class DeadLetterAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_at")


@admin.register(CertificationRun)
class CertificationRunAdmin(admin.ModelAdmin):
    list_display = ("id", "connection", "status", "started_at")


@admin.register(RatingRequest)
class RatingRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "client", "status", "state", "created_at")
    list_filter = ("status",)


@admin.register(RatingJob)
class RatingJobAdmin(admin.ModelAdmin):
    list_display = ("id", "rating_request", "market", "status", "eligibility")
    list_filter = ("status", "eligibility")


@admin.register(CanonicalQuote)
class CanonicalQuoteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "organization",
        "market",
        "status",
        "quote_source",
        "premium_class",
        "premium",
        "total",
        "version",
        "created_at",
    )
    list_filter = ("status", "quote_source", "premium_class", "organization")
    search_fields = ("external_reference", "provider_slug", "id")
    raw_id_fields = (
        "organization",
        "submission",
        "rating_request",
        "rating_job",
        "connection",
        "market",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


@admin.register(BindTransaction)
class BindTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "organization",
        "quote",
        "status",
        "external_reference",
        "created_at",
    )
    list_filter = ("status", "organization")
    search_fields = ("idempotency_key", "correlation_id", "external_reference")
    raw_id_fields = ("organization", "quote", "submission", "connection")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


@admin.register(QuoteLeadConnectivity)
class QuoteLeadConnectivityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lead",
        "quote_source",
        "connectivity_status",
        "premium",
        "external_reference",
    )
    list_filter = ("quote_source",)
    search_fields = ("external_reference", "lead__client_name", "connectivity_status")
    raw_id_fields = ("lead", "submission", "market", "quote")


@admin.register(PolicyConnectivity)
class PolicyConnectivityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "policy",
        "external_policy_number",
        "carrier_reference",
        "connectivity_status",
        "last_sync_at",
    )
    search_fields = (
        "external_policy_number",
        "carrier_reference",
        "policy__policy_number",
    )
    raw_id_fields = ("policy", "submission", "bind")
