from decimal import Decimal
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .models import Organization, ServiceRecord, CustomServiceType, CustomSourceType, Referral, Client, Vehicle, ClientIntake
from .source_choices import build_form_source_choices




class OrganizationChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} - {obj.address_line}, {obj.city}, {obj.state}"


class AgentSignupForm(UserCreationForm):
    invite_code = forms.CharField(max_length=20, label="PSB Invite Code", help_text="Enter the invite code provided by your PSB admin.")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email", "password1", "password2")

    def clean_invite_code(self):
        code = self.cleaned_data["invite_code"].strip()
        try:
            org = Organization.objects.get(invite_code__iexact=code)
            return org
        except Organization.DoesNotExist:
            raise forms.ValidationError("Invalid invite code. Please check with your PSB admin.")


class DMVAuthenticationForm(AuthenticationForm):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autofocus": True}))


class ServiceRecordForm(forms.ModelForm):
    organization = OrganizationChoiceField(
        queryset=Organization.objects.none(),
        empty_label="Select PSB",
        label="PSB"
    )

    service_type = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    
    source = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    referral_select = forms.ChoiceField(
        choices=[("", "Select Existing Referral..."), ("new", "+ Create New Referral")],
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    referral_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"placeholder": "Referral Name", "class": "form-control"}))
    referral_address = forms.CharField(widget=forms.TextInput(attrs={"placeholder": "Referral Address", "class": "form-control"}), required=False)
    referral_phone_no = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"placeholder": "(000) 000 - 0000", "class": "form-control phone-mask"}))
    referral_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"placeholder": "Referral Email", "class": "form-control"}))

    class Meta:
        model = ServiceRecord
        fields = [
            "organization",
            "client_name",
            "client_identifier",
            "client_address",
            "terminal_number",
            "vehicle_number",
            "transaction_type",
            "plate_number",
            "vin",
            "license_number",
            "driver_license_number",
            "phone_no",
            "email",
            "service_type",
            "source",
            "payment_method",
            "status",
            "processing_fee",
            "dmv_fee",
            "sales_tax",
            "credit_card_fee",
            "other_fees",
            "referral_balance",
            "paid_amount",
            "notes",
        ]
        widgets = {
            "notes": forms.TextInput(attrs={"placeholder": "Any additional notes"}),
            "phone_no": forms.TextInput(attrs={"class": "phone-mask", "placeholder": "(000) 000 - 0000"}),
        }
        
    field_order = [
        "organization",
        "client_name",
        "client_identifier",
        "client_address",
        "terminal_number",
        "vehicle_number",
        "transaction_type",
        "plate_number",
        "vin",
        "license_number",
        "driver_license_number",
        "phone_no",
        "email",
        "service_type",
        "source",
        "payment_method",
        "status",
        "processing_fee",
        "dmv_fee",
        "sales_tax",
        "credit_card_fee",
        "other_fees",
        "referral_select",
        "referral_name",
        "referral_address",
        "referral_phone_no",
        "referral_email",
        "referral_balance",
        "paid_amount",
        "referral_email",
        "notes",
    ]

    def __init__(self, *args, **kwargs):
        organizations = kwargs.pop("organizations", Organization.objects.none())
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = organizations.order_by("name", "city", "state")
        
        self.fields["referral_select"].label = "Referral Entity"
        self.fields["referral_balance"].label = "Referral Outstanding Balance"
        
        base_choices = list(ServiceRecord.SERVICE_TYPES)
        source_choices = build_form_source_choices(
            organizations,
            [
                ("walk-in", "Walk-in"),
                ("website", "Website"),
                ("referral", "Referral Entity"),
                ("other", "Other"),
            ],
        )

        if organizations.exists():
            custom_types = CustomServiceType.objects.filter(organization__in=organizations)
            for ct in custom_types:
                base_choices.append((ct.key, ct.label))

        self.fields["service_type"].choices = base_choices
        self.fields["source"].choices = source_choices
        
        referral_choices = [("", "Select Existing Referral Entity..."), ("new", "+ Create New Referral Entity")]
        if organizations.exists():
            referrals = Referral.objects.filter(organization__in=organizations).order_by('name')
            for d in referrals:
                referral_choices.insert(1, (str(d.id), d.name))
        self.fields["referral_select"].choices = referral_choices
        self.fields["referral_phone_no"].widget.attrs.update({"class": "phone-mask", "placeholder": "(000) 000 - 0000"})
        
        if organizations.count() == 1:
            org = organizations.first()
            self.fields["organization"].initial = org
            self.fields["organization"].disabled = True
            self.fields["organization"].widget.attrs["title"] = f"You are acting under {org.name}"
            self.fields["organization"].widget.attrs["style"] = "background-color: #f8fafc; cursor: not-allowed; color: #475569; border-color: #e2e8f0; appearance: none; -webkit-appearance: none; -moz-appearance: none; pointer-events: none;"

        self.fields["credit_card_fee"].widget.attrs["readonly"] = True
        self.fields["credit_card_fee"].widget.attrs["style"] = "background-color: #f1f5f9; cursor: not-allowed;"

        for field_name, field in self.fields.items():
            current_class = field.widget.attrs.get("class", "")
            if "form-control" not in current_class:
                field.widget.attrs["class"] = f"{current_class} form-control".strip()
class ClientForm(forms.ModelForm):
    organization = OrganizationChoiceField(
        queryset=Organization.objects.none(),
        empty_label="Select PSB",
        label="PSB"
    )
    source = forms.ChoiceField(choices=[], required=False)
    referral_select = forms.ChoiceField(
        choices=[("", "Select Existing Referral...")],
        required=False,
    )
    referral_name = forms.CharField(max_length=150, required=False)
    referral_category = forms.ChoiceField(choices=Referral.CATEGORY_CHOICES, required=False)
    referral_address = forms.CharField(required=False)
    referral_phone_no = forms.CharField(max_length=20, required=False)
    referral_email = forms.EmailField(required=False)
    referral_website = forms.URLField(required=False)
    referral_balance = forms.DecimalField(max_digits=10, decimal_places=2, initial=0.00, required=False)

    class Meta:
        model = Client
        fields = [
            "organization", "source",
            "is_commercial", "business_name", "business_ein",
            "last_name", "first_name", "middle_name",
            "ssn", "driver_license", "dob", "phone_number",
            "building_no", "street_address", "apartment",
            "city", "state", "zip_code", "county",
            "email", "gender"
        ]
        widgets = {
            "dob": forms.DateInput(attrs={"type": "date"}),
            "mv82_file": forms.FileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png"}),
            "phone_number": forms.TextInput(attrs={"placeholder": "(000) 000 - 0000", "class": "phone-mask"}),
            "county": forms.Select(choices=[
                ("", "Select County..."),
                ("Albany", "Albany"), ("Allegany", "Allegany"), ("Bronx", "Bronx"), ("Broome", "Broome"),
                ("Cattaraugus", "Cattaraugus"), ("Cayuga", "Cayuga"), ("Chautauqua", "Chautauqua"),
                ("Chemung", "Chemung"), ("Chenango", "Chenango"), ("Clinton", "Clinton"),
                ("Columbia", "Columbia"), ("Cortland", "Cortland"), ("Delaware", "Delaware"),
                ("Dutchess", "Dutchess"), ("Erie", "Erie"), ("Essex", "Essex"), ("Franklin", "Franklin"),
                ("Fulton", "Fulton"), ("Genesee", "Genesee"), ("Greene", "Greene"), ("Hamilton", "Hamilton"),
                ("Herkimer", "Herkimer"), ("Jefferson", "Jefferson"), ("Kings", "Kings (Brooklyn)"),
                ("Lewis", "Lewis"), ("Livingston", "Livingston"), ("Madison", "Madison"), ("Monroe", "Monroe"),
                ("Montgomery", "Montgomery"), ("Nassau", "Nassau"), ("New York", "New York (Manhattan)"),
                ("Niagara", "Niagara"), ("Oneida", "Oneida"), ("Onondaga", "Onondaga"), ("Ontario", "Ontario"),
                ("Orange", "Orange"), ("Orleans", "Orleans"), ("Oswego", "Oswego"), ("Otsego", "Otsego"),
                ("Putnam", "Putnam"), ("Queens", "Queens"), ("Rensselaer", "Rensselaer"),
                ("Richmond", "Richmond (Staten Island)"), ("Rockland", "Rockland"), ("Saint Lawrence", "Saint Lawrence"),
                ("Saratoga", "Saratoga"), ("Schenectady", "Schenectady"), ("Schoharie", "Schoharie"),
                ("Schuyler", "Schuyler"), ("Seneca", "Seneca"), ("Steuben", "Steuben"), ("Suffolk", "Suffolk"),
                ("Sullivan", "Sullivan"), ("Tioga", "Tioga"), ("Tompkins", "Tompkins"), ("Ulster", "Ulster"),
                ("Warren", "Warren"), ("Washington", "Washington"), ("Wayne", "Wayne"), ("Westchester", "Westchester"),
                ("Wyoming", "Wyoming"), ("Yates", "Yates")
            ])
        }

    def __init__(self, *args, **kwargs):
        organizations = kwargs.pop("organizations", Organization.objects.none())
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = organizations
        self.fields["phone_number"].required = True
        
        is_commercial = False
        if self.data:
            is_commercial = self.data.get('is_commercial') in ['on', 'true', True]
        elif self.instance and self.instance.pk:
            is_commercial = self.instance.is_commercial
            
        if is_commercial:
            self.fields["first_name"].required = False
            self.fields["last_name"].required = False
            self.fields["gender"].required = False
            self.fields["state"].required = False
        else:
            self.fields["first_name"].required = True
            self.fields["last_name"].required = True
            self.fields["gender"].required = True
        
        if organizations.count() == 1:
            self.fields["organization"].initial = organizations.first()
            self.fields["organization"].disabled = True
            self.fields["organization"].widget.attrs["style"] = "background-color: #f8fafc; cursor: not-allowed; color: #475569; border-color: #e2e8f0; appearance: none; pointer-events: none;"
        
        self.fields["source"].choices = build_form_source_choices(
            organizations,
            [
                ("walk-in", "Walk-in"),
                ("website", "Website"),
                ("dealer", "Dealer"),
                ("referral", "Referral"),
                ("other", "Other"),
            ],
        )

        referral_choices = [("", "--- Select Partner ---"), ("new", "+ Create New Partner")]
        if organizations.exists():
            referrals = Referral.objects.filter(organization__in=organizations).order_by('name')
            for d in referrals:
                referral_choices.insert(1, (str(d.id), d.name))
        self.fields["referral_select"].choices = referral_choices
        if self.instance.pk and self.instance.referral_id:
            self.fields["referral_select"].initial = str(self.instance.referral_id)
        self.fields["referral_phone_no"].widget.attrs.update({"class": "phone-mask", "placeholder": "(000) 000 - 0000"})
        # self.fields["referral_balance"].widget.attrs["readonly"] = True
        for field_name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "form-control"
            else:
                field.widget.attrs["class"] += " form-control"

    def clean(self):
        cleaned_data = super().clean()
        is_commercial = cleaned_data.get("is_commercial", False)
        
        if is_commercial:
            # Clear individual-field errors AND pop values unconditionally.
            # Hidden individual fields always POST "" — if left in cleaned_data
            # the empty string reaches _post_clean/full_clean which rejects blank=False.
            for f in ['first_name', 'last_name', 'gender', 'state']:
                self._errors.pop(f, None)
                cleaned_data.pop(f, None)

            business_name = cleaned_data.get("business_name", "").strip()
            business_ein = cleaned_data.get("business_ein", "").strip()
            if not business_name:
                self.add_error("business_name", "Business name is required for commercial accounts.")

            # Direct assignment overrides the now-popped empty strings.
            if business_name:
                cleaned_data["first_name"] = "Commercial"
                cleaned_data["last_name"] = business_name
            cleaned_data["gender"] = None
            # state is required by the model — default to NY if not provided
            if not cleaned_data.get("state"):
                cleaned_data["state"] = "NY"

            organization = cleaned_data.get("organization")
            if business_name and organization:
                biz_query = Client.objects.filter(
                    organization=organization,
                    is_commercial=True,
                    business_name__iexact=business_name,
                )
                if self.instance and self.instance.pk:
                    biz_query = biz_query.exclude(pk=self.instance.pk)
                if biz_query.exists():
                    raise forms.ValidationError(
                        "A business with this name already exists in this PSB "
                        "(matched case-insensitively)."
                    )
        else:
            first_name = cleaned_data.get("first_name")
            last_name = cleaned_data.get("last_name")
            gender = cleaned_data.get("gender")
            if not first_name:
                self.add_error("first_name", "First name is required.")
            if not last_name:
                self.add_error("last_name", "Last name is required.")
            if not gender:
                self.add_error("gender", "Gender is required.")
            
            organization = cleaned_data.get("organization")
            if first_name and last_name and organization:
                existing_query = Client.objects.filter(
                    organization=organization,
                    is_commercial=False,
                    first_name__iexact=first_name.strip(),
                    last_name__iexact=last_name.strip(),
                )
                if self.instance and self.instance.pk:
                    existing_query = existing_query.exclude(pk=self.instance.pk)
                if existing_query.exists():
                    raise forms.ValidationError(
                        "A client with this first and last name already exists in this PSB "
                        "(names are matched case-insensitively)."
                    )

                dl = cleaned_data.get("driver_license", "").strip().upper()
                if dl:
                    dl_query = Client.objects.filter(
                        organization=organization,
                        driver_license__iexact=dl,
                    )
                    if self.instance and self.instance.pk:
                        dl_query = dl_query.exclude(pk=self.instance.pk)
                    if dl_query.exists():
                        raise forms.ValidationError(
                            "A client with this driver license already exists in this PSB."
                        )

        referral_select = cleaned_data.get("referral_select")
        referral_name = (cleaned_data.get("referral_name") or "").strip()
        organization = cleaned_data.get("organization")
        if referral_select == "new" and referral_name and organization:
            if Referral.objects.filter(
                organization=organization,
                name__iexact=referral_name,
            ).exists():
                self.add_error(
                    "referral_name",
                    "A partner with this name already exists — select it from the list instead.",
                )
        return cleaned_data

    def clean_mv82_file(self):
        file = self.cleaned_data.get('mv82_file')
        if file:
            # 1. Strict File Size Limit (5MB)
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError("File size must be under 5MB.")
            
            # 2. Allowed Extensions
            import os
            ext = os.path.splitext(file.name)[1].lower()
            valid_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
            if ext not in valid_extensions:
                raise forms.ValidationError(f"Unsupported file extension: {ext}. Allowed: PDF, JPG, PNG.")
            
            # 3. MIME type checking
            valid_mime_types = ['application/pdf', 'image/jpeg', 'image/png']
            if getattr(file, 'content_type', None) not in valid_mime_types:
                raise forms.ValidationError("Invalid file content type.")
                
            # 4. Auto-Rename for security
            import uuid
            file.name = f"mv82_{uuid.uuid4().hex[:12]}{ext}"
            
        return file


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = [
            "vehicle_type", "plate_type", "vin", "is_legacy_vin", "plate_number",
            "vehicle_number",
            "year", "make", "model",
            "body_type", "color", "weight", "fuel_type",
            "cylinders", "seats",
            "registration_effective_date", "registration_expiration_date", 
            "insurance_company", "insurance_policy_number",
            "insurance_effective_date", "insurance_expiration_date",
            "insurance_monthly_payment",
        ]
        widgets = {
            "registration_effective_date": forms.DateInput(attrs={"type": "date"}),
            "registration_expiration_date": forms.DateInput(attrs={"type": "date"}),
            "insurance_effective_date": forms.DateInput(attrs={"type": "date"}),
            "insurance_expiration_date": forms.DateInput(attrs={"type": "date"}),
            "insurance_monthly_payment": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
        }

    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop("client", None)
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"
        self.fields["vin"].widget.attrs["id"] = "id_vin"
        self.fields["vin"].widget.attrs["maxlength"] = "17"
        self.fields["is_legacy_vin"].widget.attrs["id"] = "id_is_legacy_vin"
        self.fields["is_legacy_vin"].label = "Legacy / pre-1981 VIN"
        self.fields["vehicle_number"].widget.attrs["readonly"] = True
        self.fields["vehicle_number"].widget.attrs["style"] = "background-color: #f8fafc; cursor: not-allowed; color: #64748b;"
        self.fields["insurance_monthly_payment"].required = False
        self.fields["insurance_monthly_payment"].label = "Monthly Payment"
        if self.instance.pk and self.instance.is_legacy_vin:
            self.initial.setdefault("is_legacy_vin", True)
            self.fields["vin"].widget.attrs["maxlength"] = "16"
        elif (
            self.instance.pk
            and self.instance.vin
            and len(self.instance.vin.strip()) < 17
            and not self.instance.is_legacy_vin
        ):
            self.initial.setdefault("is_legacy_vin", True)
            self.fields["vin"].widget.attrs["maxlength"] = "16"

    def clean_vin(self):
        from .vin_validation import normalize_vin, validate_vin, vehicle_type_skips_vin_decode

        raw_vin = self.cleaned_data.get("vin", "")
        legacy = self.cleaned_data.get("is_legacy_vin", False)
        vehicle_type = self.cleaned_data.get("vehicle_type", "passenger")
        manual_type = vehicle_type_skips_vin_decode(vehicle_type) and not legacy
        vin = normalize_vin(raw_vin)
        if not vin:
            raise forms.ValidationError("VIN is required.")

        is_valid, message = validate_vin(vin, legacy=legacy, manual_type=manual_type)
        if not is_valid:
            raise forms.ValidationError(message)

        client = self.client or getattr(self.instance, "client", None)
        if client:
            existing = Vehicle.objects.filter(vin=vin, client=client).first()
            if existing and existing.pk != getattr(self.instance, "pk", None):
                raise forms.ValidationError(
                    f"This client already has a vehicle with VIN {vin} "
                    f"({existing.year} {existing.make} {existing.model})."
                )
        return vin

    def clean(self):
        from .vin_validation import vehicle_type_skips_vin_decode

        cleaned_data = super().clean()
        legacy = cleaned_data.get("is_legacy_vin", False)
        vehicle_type = cleaned_data.get("vehicle_type", "passenger")
        manual_type = vehicle_type_skips_vin_decode(vehicle_type) and not legacy
        if legacy or manual_type:
            missing = []
            if not cleaned_data.get("year"):
                missing.append("year")
            if not (cleaned_data.get("make") or "").strip():
                missing.append("make")
            if not (cleaned_data.get("model") or "").strip():
                missing.append("model")
            message = (
                "Required when using a legacy VIN (decoder cannot auto-fill)."
                if legacy
                else "Required for this vehicle type (decoder is not used)."
            )
            for field_name in missing:
                self.add_error(field_name, message)
        return cleaned_data


class VehicleServiceForm(forms.ModelForm):
    service_type = forms.ChoiceField(choices=[])
    transaction_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="Transaction Date"
    )
    paid_amount = forms.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False,
        label="Total Amount Paid Today",
        widget=forms.NumberInput(attrs={"placeholder": "0.00"})
    )
    paid_amount_2 = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        label="Secondary Paid Amount",
        widget=forms.NumberInput(attrs={"placeholder": "0.00"})
    )
    
    class Meta:
        model = ServiceRecord
        fields = [
            "transaction_date",
            "service_type", "status", "payment_method",
            "payment_method_2", "paid_amount_2",
            "terminal_number", "transaction_type",
            "processing_fee", "dmv_fee", 
            "sales_tax", "dmv_sales_tax", 
            "credit_card_fee",
            "other_fees", "other_dmv_fee",
            "paid_amount", "referral_balance", "notes"
        ]
        labels = {
            "sales_tax": "Sales Tax (PSB)",
            "dmv_sales_tax": "Sales Tax (DMV)",
            "other_fees": "Other (PSB)",
            "other_dmv_fee": "Other (DMV)",
        }


    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        
        base_choices = list(ServiceRecord.SERVICE_TYPES)
        if organization:
            custom_types = CustomServiceType.objects.filter(organization=organization)
            for ct in custom_types:
                base_choices.append((ct.key, ct.label))
        self.fields["service_type"].choices = base_choices

        self.fields["credit_card_fee"].widget.attrs["readonly"] = True
        # referral_balance is always auto-computed in the model's save() — make it readonly display only
        self.fields["referral_balance"].widget.attrs["readonly"] = True
        self.fields["referral_balance"].required = False
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"

    def clean_paid_amount(self):
        val = self.cleaned_data.get("paid_amount")
        if val is None:
            return Decimal("0")
        return val

    def clean_paid_amount_2(self):
        val = self.cleaned_data.get("paid_amount_2")
        if val is None:
            return Decimal("0")
        return val

    def clean(self):
        cleaned_data = super().clean()
        from .transaction_amounts import amounts_from_cleaned_form

        service_fee, balance, cc_fee = amounts_from_cleaned_form(cleaned_data)
        cleaned_data["credit_card_fee"] = cc_fee
        cleaned_data["referral_balance"] = balance
        return cleaned_data

class ClientIntakeForm(forms.ModelForm):
    SOURCE_CHOICES = [
        ("google_search", "Google Search"),
        ("walk_in", "Walk-In"),
        ("meta_platform", "Meta Platform"),
        ("google_campaigns", "Google Campaigns"),
        ("existing_client", "Existing Client"),
        ("dealer", "Dealer / Referral"),
        ("cold_calling", "Cold Calling"),
        ("other", "Other"),
    ]

    source = forms.CharField(
        initial="google_search",
        widget=forms.Select(
            choices=SOURCE_CHOICES,
            attrs={"class": "form-control", "id": "id_source"},
        ),
        label="How did you hear about us?",
        required=True,
    )
    vehicle_type = forms.CharField(
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_vehicle_type"}),
    )
    body_type = forms.CharField(
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_body_type"}),
    )
    fuel_type = forms.CharField(
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_fuel_type"}),
    )
    partner_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Dealer / partner name"}),
    )
    partner_phone = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control phone-mask", "placeholder": "(000) 000-0000"}),
    )
    partner_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"}),
    )
    partner_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Street address, city, state, ZIP"}),
    )
    intake_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 4,
            "placeholder": "Anything else we should know about your registration request?",
            "maxlength": "5000",
        }),
    )
    is_commercial = forms.BooleanField(
        required=False,
        label="This registration is for a business / corporation",
    )

    class Meta:
        model = ClientIntake
        exclude = [
            "organization", "status", "processed_at", "processed_by",
            "additional_data", "requested_services",
            "mv82_file", "dtf802_file", "dtf803_file", "other_docs",
            "selected_referral",
            "partner_name", "partner_phone", "partner_email", "partner_address",
            "intake_note",
            "vehicle_type", "body_type", "fuel_type", "source",
        ]
        widgets = {
            "dob": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "owner_dob": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "co_registrant_dob": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "insurance_effective_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "insurance_expiration_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "First Name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Last Name"}),
            "middle_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Middle Name/Initial"}),
            "business_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Legal business name"}),
            "business_ein": forms.TextInput(attrs={"class": "form-control", "placeholder": "EIN (optional)"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email Address"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control phone-mask", "placeholder": "(000) 000-0000"}),
            "driver_license": forms.TextInput(attrs={"class": "form-control", "placeholder": "ID Number"}),
            "ssn_last_4": forms.TextInput(attrs={"class": "form-control", "placeholder": "Last 4 digits", "maxlength": "4"}),
            "building_no": forms.TextInput(attrs={"class": "form-control", "placeholder": "No."}),
            "street_address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Street Name"}),
            "apartment": forms.TextInput(attrs={"class": "form-control", "placeholder": "Apt/Suite"}),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
            "zip_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "ZIP"}),
            "county": forms.TextInput(attrs={"class": "form-control", "placeholder": "County"}),
            "vin": forms.TextInput(attrs={"class": "form-control", "placeholder": "17-digit VIN", "maxlength": "17"}),
            "year": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Year"}),
            "make": forms.TextInput(attrs={"class": "form-control", "placeholder": "Make"}),
            "model": forms.TextInput(attrs={"class": "form-control", "placeholder": "Model"}),
            "color": forms.TextInput(attrs={"class": "form-control", "placeholder": "Color"}),
            "weight": forms.TextInput(attrs={"class": "form-control", "placeholder": "Weight (lbs)"}),
            "cylinders": forms.TextInput(attrs={"class": "form-control", "placeholder": "No. of Cylinders"}),
            "insurance_company": forms.TextInput(attrs={"class": "form-control", "placeholder": "Insurance Company"}),
            "insurance_policy_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Policy Number"}),
            "insurance_monthly_payment": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "0.00"}
            ),
            "mv82_transaction_type": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. New Registration, Transfer"}),
            "plate_to_transfer": forms.TextInput(attrs={"class": "form-control", "placeholder": "Plate Number"}),
            "owner_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Owner's Full Name"}),
            "owner_nys_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "Owner's NYS ID"}),
            "co_registrant_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Co-Registrant's Name"}),
            "co_registrant_nys_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "Co-Registrant's ID"}),
            "odometer_reading": forms.TextInput(attrs={"class": "form-control", "placeholder": "Current Odometer"}),
            "odometer_status": forms.Select(choices=[("", "Select Status"), ("Actual", "Actual Mileage"), ("Exceeds", "Exceeds Mechanical Limits"), ("Not Actual", "Not Actual Mileage")], attrs={"class": "form-control"}),
            "max_gross_weight": forms.TextInput(attrs={"class": "form-control", "placeholder": "MGW (for trucks)"}),
            "seating_capacity": forms.TextInput(attrs={"class": "form-control", "placeholder": "Seats"}),
            "num_axles": forms.TextInput(attrs={"class": "form-control", "placeholder": "Axles"}),
            "residence_building_no": forms.TextInput(attrs={"class": "form-control", "placeholder": "No."}),
            "residence_street_address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Street"}),
            "residence_city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
            "residence_zip_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "ZIP"}),
            "residence_county": forms.TextInput(attrs={"class": "form-control", "placeholder": "County"}),
            "lienholder_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Lienholder Name"}),
            "lienholder_address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Lienholder Address"}),
            "lien_filing_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "5-digit Code"}),
            "lessor_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Lessor Name"}),
            "lessor_address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Lessor Address"}),
            "insurance_id_card": forms.ClearableFileInput(
                attrs={
                    "class": "intake-pdf-input",
                    "accept": "application/pdf,.pdf",
                    "id": "id_insurance_id_card",
                }
            ),
        }

    def __init__(self, *args, organization=None, **kwargs):
        from .models import Vehicle

        self.organization = organization
        super().__init__(*args, **kwargs)
        self.fields["vehicle_type"].widget.choices = [("", "Select type...")] + list(Vehicle.VEHICLE_TYPES)
        self.fields["body_type"].widget.choices = [("", "Select body style...")] + list(Vehicle.BODY_TYPES)
        self.fields["fuel_type"].widget.choices = list(Vehicle.FUEL_TYPES)

        is_commercial = False
        if self.data:
            is_commercial = self.data.get("is_commercial") in ("on", "true", "True", "1", True)
        elif self.instance and self.instance.pk:
            is_commercial = self.instance.is_commercial

        personal_required = ["first_name", "last_name", "gender"]
        always_required = ["vin", "phone_number", "source"]
        for field_name, field in self.fields.items():
            field.required = False
        for field_name in always_required:
            if field_name in self.fields:
                self.fields[field_name].required = True
        if not is_commercial:
            for field_name in personal_required:
                if field_name in self.fields:
                    self.fields[field_name].required = True

        if not self.data and not self.instance.pk:
            self.fields["source"].initial = "google_search"
            self.fields["vehicle_type"].initial = "passenger"
            self.fields["fuel_type"].initial = "gas"
        if "insurance_monthly_payment" in self.fields:
            self.fields["insurance_monthly_payment"].required = False
            self.fields["insurance_monthly_payment"].label = "Monthly Payment"

    def clean_source(self):
        from .source_choices import norm_source

        raw = (self.data.get("source") if hasattr(self, "data") else None) or self.cleaned_data.get("source") or ""
        source = norm_source(raw)
        if source == "referral":
            return "dealer"
        valid = {key for key, _ in self.SOURCE_CHOICES}
        if source in valid:
            return source
        raise forms.ValidationError("Please select how you heard about us.")

    def clean_body_type(self):
        from .models import Vehicle

        body = (self.cleaned_data.get("body_type") or "").strip()
        if not body:
            return body or None
        valid = {key for key, _ in Vehicle.BODY_TYPES}
        return body if body in valid else "other"

    def clean_vehicle_type(self):
        from .models import Vehicle

        vtype = (self.cleaned_data.get("vehicle_type") or "").strip()
        if not vtype:
            return "passenger"
        valid = {key for key, _ in Vehicle.VEHICLE_TYPES}
        return vtype if vtype in valid else "passenger"

    def clean_intake_note(self):
        note = (self.cleaned_data.get("intake_note") or "").strip()
        return note[:5000]

    def _validate_intake_duplicates(self, cleaned_data):
        if not self.organization:
            return
        from .intake_duplicates import validate_intake_submission_from_form

        duplicate_error = validate_intake_submission_from_form(self.organization, cleaned_data)
        if duplicate_error:
            raise forms.ValidationError(duplicate_error)

    def clean(self):
        cleaned_data = super().clean()
        is_commercial = bool(cleaned_data.get("is_commercial"))
        if self.data.get("is_commercial") in ("on", "true", "True", "1"):
            is_commercial = True
        cleaned_data["is_commercial"] = is_commercial

        if is_commercial:
            for field_name in (
                "first_name",
                "last_name",
                "middle_name",
                "gender",
                "driver_license",
                "ssn_last_4",
                "dob",
            ):
                self._errors.pop(field_name, None)
                cleaned_data.pop(field_name, None)

            business_name = (cleaned_data.get("business_name") or "").strip()
            business_ein = (cleaned_data.get("business_ein") or "").strip()
            if not business_name:
                self.add_error("business_name", "Business name is required for commercial registrations.")
            if not (cleaned_data.get("phone_number") or "").strip():
                self.add_error("phone_number", "Business contact phone is required.")

            cleaned_data["business_name"] = business_name
            cleaned_data["business_ein"] = business_ein
            cleaned_data["first_name"] = "Commercial"
            cleaned_data["last_name"] = business_name or "Business"
            cleaned_data["gender"] = None
        else:
            if not (cleaned_data.get("first_name") or "").strip():
                self.add_error("first_name", "First name is required.")
            if not (cleaned_data.get("last_name") or "").strip():
                self.add_error("last_name", "Last name is required.")
            if not cleaned_data.get("gender"):
                self.add_error("gender", "Gender is required.")
            cleaned_data["business_name"] = ""
            cleaned_data["business_ein"] = ""

        source = cleaned_data.get("source")
        if source != "dealer":
            cleaned_data["partner_name"] = ""
            cleaned_data["partner_phone"] = ""
            cleaned_data["partner_email"] = None
            cleaned_data["partner_address"] = ""
            self._validate_intake_duplicates(cleaned_data)
            return cleaned_data

        ref_select = (self.data.get("referral_select") or "").strip()
        partner_name = (cleaned_data.get("partner_name") or "").strip()
        has_existing = ref_select and ref_select != "new"
        has_new = (ref_select == "new" or not ref_select) and partner_name
        if not has_existing and not has_new:
            raise forms.ValidationError(
                "Please select a dealer / referral partner or add a new one."
            )
        if ref_select == "new" and not partner_name:
            self.add_error("partner_name", "Partner name is required for a new dealer.")
        if has_existing:
            cleaned_data["partner_name"] = ""
            cleaned_data["partner_phone"] = ""
            cleaned_data["partner_email"] = None
            cleaned_data["partner_address"] = ""
        elif has_new:
            cleaned_data["partner_name"] = partner_name
        if ref_select and ref_select not in ("", "new") and self.organization:
            try:
                ref_id = int(ref_select)
            except (TypeError, ValueError):
                raise forms.ValidationError("Invalid dealer selection.")
            from .models import Referral

            if not Referral.objects.filter(id=ref_id, organization=self.organization).exists():
                raise forms.ValidationError("Selected dealer is not valid for this organization.")

        self._validate_intake_duplicates(cleaned_data)
        return cleaned_data

    def clean_insurance_id_card(self):
        upload = self.cleaned_data.get("insurance_id_card")
        if not upload:
            return upload
        name = (upload.name or "").lower()
        if not name.endswith(".pdf"):
            raise forms.ValidationError("Insurance ID card must be a PDF file.")
        content_type = (getattr(upload, "content_type", "") or "").lower()
        if content_type and content_type not in ("application/pdf", "application/x-pdf"):
            raise forms.ValidationError("Insurance ID card must be a PDF file.")
        max_bytes = 50 * 1024 * 1024
        if upload.size > max_bytes:
            raise forms.ValidationError("Insurance ID card must be 50 MB or smaller.")
        return upload

    def apply_partner_and_note_to_instance(self, intake, post_data):
        """Copy non-model-bound partner fields onto the intake record."""
        intake.source = self.cleaned_data.get("source") or intake.source
        intake.vehicle_type = self.cleaned_data.get("vehicle_type") or "passenger"
        intake.body_type = self.cleaned_data.get("body_type")
        intake.fuel_type = self.cleaned_data.get("fuel_type") or "gas"
        intake.intake_note = self.cleaned_data.get("intake_note") or ""
        intake.partner_name = (self.cleaned_data.get("partner_name") or "").strip()
        intake.partner_phone = (self.cleaned_data.get("partner_phone") or "").strip()
        intake.partner_email = self.cleaned_data.get("partner_email") or None
        intake.partner_address = (self.cleaned_data.get("partner_address") or "").strip()

        ref_select = (post_data.get("referral_select") or "").strip()
        if ref_select and ref_select != "new":
            try:
                intake.selected_referral_id = int(ref_select)
            except (TypeError, ValueError):
                intake.selected_referral = None
        else:
            intake.selected_referral = None
        return intake

