from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Client, Referral, ServiceRecord, Vehicle
from .policies import user_organization_ids


class TenantScopedSerializerMixin:
    """Limit every writable related field to records inside the caller's own PSBs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        org_ids = user_organization_ids(user) if user is not None else []
        scopes = {
            "client": lambda: Client.objects.filter(organization_id__in=org_ids),
            "vehicle": lambda: Vehicle.objects.filter(client__organization_id__in=org_ids),
            "referral": lambda: Referral.objects.filter(organization_id__in=org_ids),
            "handled_by": lambda: get_user_model().objects.filter(
                organization_memberships__organization_id__in=org_ids,
                organization_memberships__is_active=True,
            ).distinct(),
        }
        for name, build in scopes.items():
            field = self.fields.get(name)
            if field is not None and not field.read_only and hasattr(field, "queryset"):
                field.queryset = build()


class ClientSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """API serializer — excludes sensitive fields (SSN, files, soft-delete)."""

    class Meta:
        model = Client
        fields = [
            "id",
            "organization",
            "source",
            "referral",
            "first_name",
            "last_name",
            "middle_name",
            "driver_license",
            "dob",
            "phone_number",
            "building_no",
            "street_address",
            "apartment",
            "city",
            "state",
            "zip_code",
            "county",
            "residence_building_no",
            "residence_street_address",
            "residence_apartment",
            "residence_city",
            "residence_zip_code",
            "residence_county",
            "email",
            "gender",
            "is_commercial",
            "business_name",
            "business_ein",
            "created_at",
        ]
        read_only_fields = ["id", "organization", "created_at"]


class VehicleSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            "id",
            "client",
            "vehicle_number",
            "plate_number",
            "vin",
            "year",
            "make",
            "model",
            "vehicle_type",
            "body_type",
            "fuel_type",
            "plate_type",
            "color",
            "registration_expiration_date",
            "insurance_expiration_date",
            "is_priority",
            "is_legacy_vin",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ServiceRecordSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = ServiceRecord
        fields = [
            "id",
            "organization",
            "handled_by",
            "vehicle",
            "client_name",
            "client_identifier",
            "client_address",
            "vehicle_number",
            "plate_number",
            "vin",
            "license_number",
            "driver_license_number",
            "phone_no",
            "email",
            "terminal_number",
            "transaction_type",
            "service_type",
            "status",
            "payment_method",
            "payment_method_2",
            "source",
            "referral",
            "processing_fee",
            "referral_commission",
            "dmv_fee",
            "sales_tax",
            "dmv_sales_tax",
            "credit_card_fee",
            "other_fees",
            "other_dmv_fee",
            "service_fee",
            "referral_balance",
            "is_referral_paid",
            "expected_payment_date",
            "notes",
            "receipt_number",
            "transaction_date",
            "case_id",
            "paid_amount",
            "paid_amount_2",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "organization",
            "handled_by",
            "receipt_number",
            "case_id",
            "service_fee",
            "referral_balance",
            "referral_commission",
            "created_at",
            "updated_at",
        ]
