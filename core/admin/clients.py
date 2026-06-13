from django.contrib import admin

from ..models import Client, ClientIntake, SiteNews, Vehicle


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "phone_number", "organization", "referral", "created_at")
    list_filter = ("organization", "state", "source", "created_at")
    search_fields = ("first_name", "last_name", "email", "phone_number", "driver_license")
    autocomplete_fields = ("referral",)
    ordering = ("-created_at",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("vin", "year", "make", "model", "plate_number", "client", "created_at")
    list_filter = ("vehicle_type", "fuel_type", "plate_type", "client__organization", "created_at")
    search_fields = ("vin", "plate_number", "make", "model", "client__first_name", "client__last_name")
    autocomplete_fields = ("client",)
    ordering = ("-created_at",)


@admin.register(ClientIntake)
class ClientIntakeAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "organization", "status", "source", "created_at", "processed_by")
    list_filter = ("status", "organization", "source")
    search_fields = ("first_name", "last_name", "vin", "email", "phone_number")
    readonly_fields = ("created_at", "processed_at", "processed_by")
    ordering = ("-created_at",)


@admin.register(SiteNews)
class SiteNewsAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "is_active", "published_by", "created_at")
    list_filter = ("is_active", "organization")
    search_fields = ("title", "content", "organization__name")
    autocomplete_fields = ("organization", "published_by")
    ordering = ("-created_at",)
