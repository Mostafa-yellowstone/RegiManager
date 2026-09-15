from django import forms
from django.contrib import admin

from ..models import Client, ClientIntake, Organization, SiteNews, Vehicle
from ..source_choices import FORM_SOURCE_CHOICES, build_form_source_choices, norm_source


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "phone_number", "organization", "source", "referral", "created_at")
    list_filter = ("organization", "state", "source", "created_at")
    search_fields = ("first_name", "last_name", "email", "phone_number", "driver_license")
    autocomplete_fields = ("referral",)
    ordering = ("-created_at",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "source":
            choices = list(
                build_form_source_choices(Organization.objects.all(), list(FORM_SOURCE_CHOICES))
            )
            # Preserve legacy hyphenated values already stored on clients.
            if not any(value == "walk-in" for value, _ in choices):
                choices.append(("walk-in", "Walk-In (legacy)"))

            object_id = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
            if object_id:
                current = (
                    Client.all_objects.filter(pk=object_id)
                    .values_list("source", flat=True)
                    .first()
                )
                if current and not any(norm_source(value) == norm_source(current) for value, _ in choices):
                    choices.append((current, current))

            return forms.ChoiceField(
                choices=choices,
                required=True,
                label="Source",
                help_text="How this client found the business.",
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)


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
