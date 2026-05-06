from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .models import Organization, ServiceRecord, CustomServiceType, CustomSourceType, CarDealer, Client, Vehicle




class OrganizationChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} - {obj.address_line}, {obj.city}, {obj.state}"


class AgentSignupForm(UserCreationForm):
    invite_code = forms.CharField(max_length=20, label="Agency Invite Code", help_text="Enter the invite code provided by your Agency admin.")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email", "password1", "password2")

    def clean_invite_code(self):
        code = self.cleaned_data["invite_code"].strip()
        try:
            org = Organization.objects.get(invite_code__iexact=code)
            return org
        except Organization.DoesNotExist:
            raise forms.ValidationError("Invalid invite code. Please check with your Agency admin.")


class DMVAuthenticationForm(AuthenticationForm):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autofocus": True}))


class ServiceRecordForm(forms.ModelForm):
    organization = OrganizationChoiceField(
        queryset=Organization.objects.none(),
        empty_label="Select Agency",
        label="Agency"
    )

    service_type = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    
    source = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    dealer_select = forms.ChoiceField(
        choices=[("", "Select Existing Dealership..."), ("new", "+ Create New Dealership")],
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    dealer_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"placeholder": "Dealership Name", "class": "form-control"}))
    dealer_address = forms.CharField(widget=forms.TextInput(attrs={"placeholder": "Dealership Address", "class": "form-control"}), required=False)
    dealer_phone_no = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"placeholder": "Dealer Phone", "class": "form-control"}))
    dealer_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"placeholder": "Dealer Email", "class": "form-control"}))

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
            "dealer_balance",
            "notes",
        ]
        widgets = {
            "notes": forms.TextInput(attrs={"placeholder": "Any additional notes"}),
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
        "dealer_select",
        "dealer_name",
        "dealer_address",
        "dealer_phone_no",
        "dealer_email",
        "dealer_balance",
        "dealer_email",
        "notes",
    ]

    def __init__(self, *args, **kwargs):
        organizations = kwargs.pop("organizations", Organization.objects.none())
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = organizations.order_by("name", "city", "state")
        
        self.fields["dealer_select"].label = "Dealership"
        self.fields["dealer_balance"].label = "Dealer Outstanding Balance"
        
        base_choices = list(ServiceRecord.SERVICE_TYPES)
        source_choices = [
            ("walk-in", "Walk-in"),
            ("website", "Website"),
            ("car dealer", "Car Dealer"),
            ("referral", "Referral"),
        ]
        
        if organizations.exists():
            custom_types = CustomServiceType.objects.filter(organization__in=organizations)
            for ct in custom_types:
                base_choices.append((ct.key, ct.label))
                
            custom_sources = CustomSourceType.objects.filter(organization__in=organizations)
            for cs in custom_sources:
                source_choices.append((cs.label.lower(), cs.label))
                
        self.fields["service_type"].choices = base_choices
        self.fields["source"].choices = source_choices
        
        dealer_choices = [("", "Select Existing Dealership..."), ("new", "+ Create New Dealership")]
        if organizations.exists():
            dealers = CarDealer.objects.filter(organization__in=organizations).order_by('name')
            for d in dealers:
                dealer_choices.insert(1, (str(d.id), d.name))
        self.fields["dealer_select"].choices = dealer_choices
        
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
        empty_label="Select Agency",
        label="Agency"
    )
    source = forms.ChoiceField(choices=[], required=False)
    dealer_select = forms.ChoiceField(
        choices=[("", "Select Existing Dealership..."), ("new", "+ Create New Dealership")],
        required=False,
    )
    dealer_name = forms.CharField(max_length=150, required=False)
    dealer_address = forms.CharField(required=False)
    dealer_phone_no = forms.CharField(max_length=20, required=False)
    dealer_email = forms.EmailField(required=False)

    class Meta:
        model = Client
        fields = [
            "organization", "source", "is_partner",
            "last_name", "first_name", "middle_name",
            "ssn", "driver_license", "dob", "phone_number",
            "building_no", "street_address", "apartment",
            "city", "state", "zip_code", "county",
            "email", "gender"
        ]
        widgets = {
            "dob": forms.DateInput(attrs={"type": "date"}),
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
        
        if organizations.count() == 1:
            self.fields["organization"].initial = organizations.first()
            self.fields["organization"].disabled = True
            self.fields["organization"].widget.attrs["style"] = "background-color: #f8fafc; cursor: not-allowed; color: #475569; border-color: #e2e8f0; appearance: none; pointer-events: none;"
        
        source_choices = [
            ("walk-in", "Walk-in"),
            ("website", "Website"),
            ("car dealer", "Car Dealer"),
            ("referral", "Referral"),
        ]
        if organizations.exists():
            custom_sources = CustomSourceType.objects.filter(organization__in=organizations)
            for cs in custom_sources:
                source_choices.append((cs.label.lower(), cs.label))
        self.fields["source"].choices = source_choices

        dealer_choices = [("", "Select Existing Dealership..."), ("new", "+ Create New Dealership")]
        if organizations.exists():
            dealers = CarDealer.objects.filter(organization__in=organizations).order_by('name')
            for d in dealers:
                dealer_choices.insert(1, (str(d.id), d.name))
        self.fields["dealer_select"].choices = dealer_choices

        for field_name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "form-control"
            else:
                field.widget.attrs["class"] += " form-control"

    def clean(self):
        cleaned_data = super().clean()
        first_name = cleaned_data.get("first_name")
        last_name = cleaned_data.get("last_name")
        organization = cleaned_data.get("organization")
        
        if first_name and last_name and organization:
            existing = Client.objects.filter(
                first_name__iexact=first_name, 
                last_name__iexact=last_name,
                organization=organization
            ).exists()
            if existing and not self.instance.pk:
                raise forms.ValidationError(f"A client named {first_name} {last_name} already exists in this Agency.")
        return cleaned_data


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = [
            "vehicle_type", "plate_type", "vin", "plate_number",
            "vehicle_number", "dl_number",
            "year", "make", "model",
            "body_type", "color", "weight", "fuel_type",
            "cylinders", "seats",
            "registration_effective_date", "registration_expiration_date", 
            "insurance_company", "insurance_policy_number", 
            "insurance_effective_date", "insurance_expiration_date"
        ]
        widgets = {
            "registration_effective_date": forms.DateInput(attrs={"type": "date"}),
            "registration_expiration_date": forms.DateInput(attrs={"type": "date"}),
            "insurance_effective_date": forms.DateInput(attrs={"type": "date"}),
            "insurance_expiration_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"
        self.fields["vin"].widget.attrs["id"] = "id_vin"
        self.fields["vehicle_number"].widget.attrs["readonly"] = True
        self.fields["vehicle_number"].widget.attrs["style"] = "background-color: #f8fafc; cursor: not-allowed; color: #64748b;"

    def clean_vin(self):
        vin = self.cleaned_data.get("vin", "").strip().upper()
        if not vin:
            raise forms.ValidationError("VIN is required.")
        existing = Vehicle.objects.filter(vin=vin).first()
        if existing and existing.pk != getattr(self.instance, "pk", None):
            raise forms.ValidationError(
                f"This VIN already exists! It belongs to {existing.client} "
                f"({existing.year} {existing.make} {existing.model})."
            )
        return vin


class VehicleServiceForm(forms.ModelForm):
    service_type = forms.ChoiceField(choices=[])
    total_paid = forms.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False,
        label="Total Amount Paid Today",
        widget=forms.NumberInput(attrs={"placeholder": "0.00"})
    )
    
    class Meta:
        model = ServiceRecord
        fields = [
            "service_type", "status", "payment_method",
            "terminal_number", "transaction_type",
            "processing_fee", "dmv_fee", "sales_tax", "credit_card_fee",
            "total_paid", "dealer_balance", "notes"
        ]


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
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"
