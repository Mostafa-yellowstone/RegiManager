from django.contrib import admin

from ..models import MotorclubB2BPartner, MotorclubConfig, MotorclubMembership


@admin.register(MotorclubConfig)
class MotorclubConfigAdmin(admin.ModelAdmin):
    list_display = ("organization", "tier_35_provider_take", "tier_50_provider_take", "updated_at")
    search_fields = ("organization__name",)


@admin.register(MotorclubB2BPartner)
class MotorclubB2BPartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "contact_name", "is_active", "created_at")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "contact_name")


@admin.register(MotorclubMembership)
class MotorclubMembershipAdmin(admin.ModelAdmin):
    list_display = ("membership_number", "client", "tier", "channel", "status", "psb_profit", "organization")
    list_filter = ("organization", "channel", "status", "tier")
    search_fields = ("membership_number", "client__first_name", "client__last_name")
    autocomplete_fields = ("client",)
