from django.contrib import admin

from .models import (
    Appointment,
    CertificationRun,
    Connection,
    Connector,
    ConnectorJob,
    DeadLetterItem,
    MarketProfile,
    ProducerCode,
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
