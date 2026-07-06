"""Public insurance intake form with LOB-specific validation."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .insurance_intake_constants import (
    EZLYNX_QUOTE_TYPE_CHOICES,
    map_ezlynx_quote_type_to_insurance_type,
    insurance_intake_type_choices,
    is_commercial_auto,
    is_personal_auto,
    requires_business_fields,
    requires_vehicle_fields,
)
from .models import InsuranceIntake, InsurancePolicy
from .source_choices import INSURANCE_SOURCE_CHOICES
from .us_states import US_STATES


class InsuranceIntakeForm(forms.ModelForm):
    insurance_type = forms.ChoiceField(
        choices=insurance_intake_type_choices,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_insurance_type"}),
    )
    source = forms.ChoiceField(
        choices=[(c["key"], c["label"]) for c in INSURANCE_SOURCE_CHOICES],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    business_type = forms.ChoiceField(
        choices=InsurancePolicy.BusinessTypeChoices.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    state = forms.ChoiceField(
        choices=US_STATES,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = InsuranceIntake
        fields = [
            "insurance_type",
            "source",
            "business_type",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "dob",
            "driver_license",
            "business_name",
            "business_ein",
            "dot_number",
            "fleet_vehicle_count",
            "street_address",
            "city",
            "state",
            "zip_code",
            "vin",
            "year",
            "make",
            "model",
            "current_carrier",
            "prior_policy_number",
            "requested_effective_date",
            "intake_note",
            "driver_license_file",
            "vehicle_registration_file",
            "other_docs_file",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control", "autocomplete": "tel"}),
            "dob": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "driver_license": forms.TextInput(attrs={"class": "form-control"}),
            "business_name": forms.TextInput(attrs={"class": "form-control"}),
            "business_ein": forms.TextInput(attrs={"class": "form-control"}),
            "dot_number": forms.TextInput(attrs={"class": "form-control"}),
            "fleet_vehicle_count": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "street_address": forms.TextInput(attrs={"class": "form-control", "autocomplete": "street-address"}),
            "city": forms.TextInput(attrs={"class": "form-control", "autocomplete": "address-level2"}),
            "zip_code": forms.TextInput(attrs={"class": "form-control", "autocomplete": "postal-code"}),
            "vin": forms.TextInput(attrs={"class": "form-control", "maxlength": 17}),
            "year": forms.NumberInput(attrs={"class": "form-control", "min": 1900, "max": 2100}),
            "make": forms.TextInput(attrs={"class": "form-control"}),
            "model": forms.TextInput(attrs={"class": "form-control"}),
            "current_carrier": forms.TextInput(attrs={"class": "form-control"}),
            "prior_policy_number": forms.TextInput(attrs={"class": "form-control"}),
            "requested_effective_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "intake_note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "driver_license_file": forms.ClearableFileInput(attrs={"class": "form-control-file"}),
            "vehicle_registration_file": forms.ClearableFileInput(attrs={"class": "form-control-file"}),
            "other_docs_file": forms.ClearableFileInput(attrs={"class": "form-control-file"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)
        for name in ("current_carrier", "prior_policy_number", "intake_note", "dot_number"):
            self.fields[name].required = False
        self.fields["business_type"].initial = InsurancePolicy.BusinessTypeChoices.NEW_BUSINESS
        self.fields["insurance_type"].initial = "auto_personal"

    def clean(self):
        cleaned = super().clean()
        insurance_type = cleaned.get("insurance_type") or ""

        required_always = [
            "first_name",
            "last_name",
            "phone_number",
            "email",
            "street_address",
            "city",
            "state",
            "zip_code",
            "source",
            "requested_effective_date",
        ]
        for field in required_always:
            if not cleaned.get(field):
                self.add_error(field, "This field is required.")

        if is_personal_auto(insurance_type):
            for field in ("dob", "driver_license", "vin", "year", "make", "model"):
                if not cleaned.get(field):
                    self.add_error(field, "Required for personal auto insurance.")

        if is_commercial_auto(insurance_type):
            for field in ("business_name", "business_ein"):
                if not cleaned.get(field):
                    self.add_error(field, "Required for commercial auto / fleet insurance.")
            has_vehicle = all(cleaned.get(f) for f in ("vin", "year", "make", "model"))
            fleet_count = cleaned.get("fleet_vehicle_count")
            if not has_vehicle and not fleet_count:
                raise ValidationError(
                    "Provide primary vehicle details (VIN, year, make, model) or fleet vehicle count."
                )
            if insurance_type == "trucking" and not cleaned.get("dot_number"):
                self.add_error("dot_number", "DOT number is required for trucking.")

        if requires_business_fields(insurance_type) and not is_commercial_auto(insurance_type):
            for field in ("business_name", "business_ein"):
                if not cleaned.get(field):
                    self.add_error(field, "Required for this line of business.")

        if requires_vehicle_fields(insurance_type) and not is_personal_auto(insurance_type) and not is_commercial_auto(insurance_type):
            pass

        return cleaned


class InsuranceIntakeEzlynxCaptureForm(forms.Form):
    """Step 1 capture for EZLynx dual portal — mirrors the CQ getting-started fields."""

    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
    )
    phone_number = forms.CharField(
        max_length=20,
        label="Home phone",
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "tel", "placeholder": "e.g. 914-555-1234"}),
    )
    zip_code = forms.CharField(
        max_length=10,
        label="ZIP code",
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "postal-code"}),
    )
    quote_type = forms.ChoiceField(
        choices=EZLYNX_QUOTE_TYPE_CHOICES,
        label="Quote type",
        widget=forms.Select(attrs={"class": "form-control"}),
        initial="auto",
    )

    def save_intake(self, organization):
        from django.utils import timezone

        from .models import InsuranceIntake

        quote_type = self.cleaned_data["quote_type"]
        insurance_type = map_ezlynx_quote_type_to_insurance_type(quote_type)
        note_parts = [f"EZLynx online quote ({quote_type.replace('_', ' ')})"]
        if quote_type == "both":
            note_parts.append("Requested auto and home coverage")

        return InsuranceIntake.objects.create(
            organization=organization,
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            email=self.cleaned_data["email"],
            phone_number=self.cleaned_data["phone_number"],
            zip_code=self.cleaned_data["zip_code"],
            insurance_type=insurance_type,
            source="website",
            requested_effective_date=timezone.localdate(),
            intake_note=" — ".join(note_parts),
            additional_data={
                "portal_mode": "ezlynx_dual",
                "ezlynx_quote_type": quote_type,
                "capture_step": "completed",
            },
        )
