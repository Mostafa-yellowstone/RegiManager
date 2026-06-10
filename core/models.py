from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils import timezone
from django.utils.crypto import get_random_string
import uuid
from decimal import Decimal

def generate_invite_code():
    return get_random_string(8).upper()


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(blank=True, null=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save()

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)


class Organization(models.Model):
    name = models.CharField(max_length=120)
    logo = models.ImageField(upload_to="organization_logos/", blank=True, null=True)
    address_line = models.CharField(max_length=180, blank=True, default="")
    city = models.CharField(max_length=80, blank=True, default="")
    state = models.CharField(max_length=80, blank=True, default="")
    phone_number = models.CharField(max_length=20, blank=True, default="", help_text="PSB contact number for clients.")
    psbc_license = models.CharField(
        max_length=60,
        blank=True,
        default="",
        help_text="PSB license number printed on service receipts under PSBC No.",
    )
    invite_code = models.CharField(max_length=20, unique=True, default=generate_invite_code)
    portal_token = models.CharField(max_length=64, unique=True, blank=True, null=True)
    max_agents = models.IntegerField(default=5, help_text="Maximum number of agents allowed for this PSB.")
    is_automation_enabled = models.BooleanField(default=False, help_text="Enable Automation Hub features for this PSB.")
    is_active = models.BooleanField(default=True, help_text="Enable or disable this PSB account.")
    show_review_button = models.BooleanField(default=False, verbose_name="Show Review Button on Success Page", help_text="Add a custom review button to the intake completion page.")
    review_link = models.URLField(max_length=500, blank=True, null=True, verbose_name="Review/Custom Link", help_text="The URL that the review button will link to.")
    insurance_space_password = models.CharField(max_length=128, blank=True, default="", help_text="Password to access locked insurance space.")
    insurance_space_locked = models.BooleanField(default=False, help_text="Is the insurance space password-locked?")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("name", "address_line", "city", "state")
        verbose_name = "PSB"
        verbose_name_plural = "PSBs"

    def save(self, *args, **kwargs):
        if not self.portal_token:
            self.portal_token = get_random_string(32)
        super().save(*args, **kwargs)

    def __str__(self):
        location = ", ".join(part for part in [self.city, self.state] if part)
        return f"{self.name} ({location})" if location else self.name


class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MEMBER = "member", "Agent"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    can_view_reports = models.BooleanField(default=False, help_text="Can this agent view PSB reports?")
    can_view_net_profit = models.BooleanField(default=False, help_text="Can this agent view net profit?")
    can_manage_referrals = models.BooleanField(default=False, help_text="Can this agent manage referral partners?")
    can_trigger_automation = models.BooleanField(default=False, help_text="Can this user manually trigger the automation scan?")
    is_active = models.BooleanField(default=True, help_text="Enable or disable this agent in this PSB.")
    signature = models.ImageField(upload_to="agent_signatures/", blank=True, null=True, help_text="Agent signature image to be displayed on receipts.")
    can_view_spaces = models.BooleanField(
        default=False,
        help_text="Can this member (including PSB owners) view the main Spaces page?",
    )
    can_deal_with_insurance = models.BooleanField(default=False, help_text="Can this agent deal with insurance and appear in the insurance workspace?")
    can_deal_with_motorclub = models.BooleanField(
        default=False,
        help_text="Can this member sell and manage Motor Club roadside memberships?",
    )
    can_delete_receipt = models.BooleanField(default=False, help_text="Can this agent delete/remove receipt records from the service list?")
    can_view_commission = models.BooleanField(default=False, help_text="Can this agent view commission rate, commission amount, and agency profit in the insurance space?")
    can_view_banking = models.BooleanField(default=False, help_text="Can this agent view the banking section in the insurance space?")
    can_manage_news = models.BooleanField(default=False, help_text="Can this agent add, edit, or delete news/announcements?")
    can_manage_knowledge_hub = models.BooleanField(default=False, help_text="Can this agent add or delete materials in the Knowledge Hub?")
    can_manage_documents = models.BooleanField(
        default=False,
        help_text="Can this agent create folders, document types, and records in the Documents space?",
    )
    accessible_spaces = models.ManyToManyField(
        "Space",
        blank=True,
        related_name="permitted_memberships",
        help_text="Specific spaces this member (including PSB owners) can open.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "user")
        ordering = ["organization__name", "user__username"]
        verbose_name = "Agent"
        verbose_name_plural = "Agents"

    def __str__(self):
        return f"{self.user.username} - {self.organization.name} ({self.get_role_display()})"


class CustomSourceType(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="custom_sources")
    label = models.CharField(max_length=100)
    
    def __str__(self):
        return self.label


class Referral(SoftDeleteModel):
    CATEGORY_CHOICES = [
        ("dealer", "Car Dealer"),
        ("travel", "Travel Agency"),
        ("broker", "Broker"),
        ("customer", "Customer"),
        ("custom", "Custom"),
    ]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="referrals")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="dealer")
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True, default="")
    phone_no = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    is_partner = models.BooleanField(default=False)
    initial_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class ReferralCategoryOption(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="referral_category_options"
    )
    key = models.CharField(max_length=50)
    label = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "key")
        ordering = ["label"]

    def __str__(self):
        return self.label


class InsuranceTypeOption(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="insurance_type_options"
    )
    key = models.CharField(max_length=30)
    label = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "key")
        ordering = ["label"]

    def __str__(self):
        return self.label


class CustomServiceType(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="custom_services"
    )
    key = models.CharField(max_length=60)
    label = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "key")
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} ({self.organization.name})"


class Client(SoftDeleteModel):
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]
    
    US_STATES = [
        ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"), ("CA", "California"),
        ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"), ("FL", "Florida"), ("GA", "Georgia"),
        ("HI", "Hawaii"), ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
        ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
        ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"), ("MO", "Missouri"),
        ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"),
        ("NM", "New Mexico"), ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
        ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
        ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"),
        ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="clients")
    source = models.CharField(max_length=100, default="walk-in")
    referral = models.ForeignKey(Referral, on_delete=models.SET_NULL, null=True, blank=True, related_name="clients")
    
    first_name = models.CharField(max_length=100, db_index=True)
    last_name = models.CharField(max_length=100, db_index=True)
    middle_name = models.CharField(max_length=100, blank=True, default="")
    
    ssn = models.CharField(max_length=11, blank=True, default="")
    driver_license = models.CharField(max_length=50, blank=True, default="")
    dob = models.DateField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, default="", db_index=True)
    
    building_no = models.CharField(max_length=20, blank=True, default="")
    street_address = models.CharField(max_length=200, blank=True, default="")
    apartment = models.CharField(max_length=50, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=2, choices=US_STATES, default="NY")
    zip_code = models.CharField(max_length=10, blank=True, default="")
    county = models.CharField(max_length=100, blank=True, default="")
    
    # MV-82 Residential Address (if different from mailing)
    residence_building_no = models.CharField(max_length=20, blank=True, default="")
    residence_street_address = models.CharField(max_length=200, blank=True, default="")
    residence_apartment = models.CharField(max_length=50, blank=True, default="")
    residence_city = models.CharField(max_length=100, blank=True, default="")
    residence_zip_code = models.CharField(max_length=10, blank=True, default="")
    residence_county = models.CharField(max_length=100, blank=True, default="")

    email = models.EmailField(blank=True, null=True, db_index=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)
    
    # Commercial / Business plates flag
    is_commercial = models.BooleanField(default=False, help_text="Check if this is a commercial/business account")
    business_name = models.CharField(max_length=200, blank=True, default="", help_text="Business or company name (for commercial accounts)")
    business_ein = models.CharField(max_length=20, blank=True, default="", help_text="Employer Identification Number (EIN) for commercial accounts")
    
    # Uploaded Documents
    mv82_file = models.FileField(upload_to="client_docs/mv82/", blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def name(self):
        if self.is_commercial and self.business_name:
            return self.business_name
        return f"{self.first_name} {self.last_name}"

    @property
    def full_address(self):
        parts = [self.building_no, self.street_address, self.apartment, self.city, self.state, self.zip_code]
        return ", ".join([p for p in parts if p])

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if not is_new:
            try:
                from django.apps import apps
                ServiceRecordModel = apps.get_model('core', 'ServiceRecord')
                ServiceRecordModel.objects.filter(vehicle__client=self).update(
                    client_name=self.name,
                    client_address=self.full_address
                )
            except Exception:
                pass

    def delete(self, using=None, keep_parents=False):
        self.notifications.all().delete()
        super().delete(using=using, keep_parents=keep_parents)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["organization", "last_name", "first_name"]),
        ]


class Vehicle(SoftDeleteModel):
    VEHICLE_TYPES = [
        ("passenger", "Passenger Car"),
        ("truck", "Truck"),
        ("motorcycle", "Motorcycle"),
        ("bus", "Bus"),
        ("trailer", "Trailer"),
        ("moped", "Moped"),
        ("boat", "Boat"),
        ("jetski", "Jetski"),
        ("mobile_home", "Mobile Home"),
        ("snowmobile", "Snowmobile"),
        ("atv", "ATV"),
        ("dump", "Dump"),
        ("other", "Other"),
    ]
    BODY_TYPES = [
        ("2door", "2-Doors"),
        ("4door", "4-Doors"),
        ("truck", "Truck"),
        ("van", "Van"),
        ("coupe", "Coupe"),
        ("convertible", "Convertible"),
        ("suv", "SUV"),
        ("motorcycle", "Motorcycle"),
        ("van_truck", "Van Truck"),
        ("flat_bed_truck", "Flat bed truck"),
        ("tank_truck", "Tank Truck"),
        ("tow", "Tow"),
        ("limo", "Limo"),
        ("light_trailer", "Light Trailer"),
        ("wagon", "Wagon"),
        ("tractor", "Tractor"),
        ("na", "N/A"),
        ("other", "Other"),
    ]
    FUEL_TYPES = [
        ("gas", "Gasoline"),
        ("diesel", "Diesel"),
        ("electric", "Electric"),
        ("hybrid", "Hybrid"),
        ("natural_gas", "Natural Gas"),
        ("other", "Other"),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="vehicles")
    vehicle_type = models.CharField(max_length=50, choices=VEHICLE_TYPES, default="passenger")
    vin = models.CharField(max_length=50, db_index=True)
    is_legacy_vin = models.BooleanField(
        default=False,
        help_text="Pre-1981 or non-standard VIN (fewer than 17 characters). Skips NHTSA decode.",
    )
    plate_number = models.CharField(max_length=50, blank=True, default="", db_index=True)
    
    year = models.IntegerField(blank=True, null=True)
    make = models.CharField(max_length=100, blank=True, default="")
    model = models.CharField(max_length=100, blank=True, default="")
    
    body_type = models.CharField(max_length=50, choices=BODY_TYPES, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, default="")
    weight = models.CharField(max_length=50, blank=True, default="")
    fuel_type = models.CharField(max_length=50, choices=FUEL_TYPES, default="gas")
    
    cylinders = models.CharField(max_length=20, blank=True, default="")
    seats = models.CharField(max_length=20, blank=True, default="")
    
    vehicle_number = models.CharField(max_length=50, blank=True, default="", help_text="Internal vehicle number")
    dl_number = models.CharField(max_length=50, blank=True, default="", help_text="Driver license number for this vehicle/owner")
    
    registration_effective_date = models.DateField(blank=True, null=True)
    registration_expiration_date = models.DateField(blank=True, null=True)
    
    PLATE_TYPES = [
        ("personal", "Personal Plates"),
        ("commercial", "Commercial Plates"),
        ("motorcycle", "Motorcycle plates"),
        ("atv", "ATV plates"),
        ("trailer", "Trailer Plates"),
    ]
    plate_type = models.CharField(max_length=20, choices=PLATE_TYPES, default="personal")
    
    insurance_company = models.CharField(max_length=150, blank=True, default="")
    insurance_policy_number = models.CharField(max_length=100, blank=True, default="")
    insurance_effective_date = models.DateField(blank=True, null=True)
    insurance_expiration_date = models.DateField(blank=True, null=True)
    is_priority = models.BooleanField(default=False)
    
    # MV-82 Technical Fields
    odometer_reading = models.CharField(max_length=50, blank=True, default="")
    odometer_status = models.CharField(max_length=50, blank=True, default="")
    max_gross_weight = models.CharField(max_length=50, blank=True, default="")
    num_axles = models.CharField(max_length=20, blank=True, default="")
    
    # MV-82 Owner/Co-Registrant Fields
    owner_name = models.CharField(max_length=200, blank=True, default="")
    owner_nys_id = models.CharField(max_length=50, blank=True, default="")
    owner_dob = models.DateField(blank=True, null=True)
    
    co_registrant_name = models.CharField(max_length=200, blank=True, default="")
    co_registrant_nys_id = models.CharField(max_length=50, blank=True, default="")
    co_registrant_dob = models.DateField(blank=True, null=True)
    
    # MV-82 Lien/Lease Fields
    has_lien = models.BooleanField(default=False)
    lienholder_name = models.CharField(max_length=200, blank=True, default="")
    lienholder_address = models.CharField(max_length=255, blank=True, default="")
    lien_filing_code = models.CharField(max_length=5, blank=True, default="")
    
    is_leased = models.BooleanField(default=False)
    lessor_name = models.CharField(max_length=200, blank=True, default="")
    lessor_address = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.year} {self.make} {self.model} ({self.vin})"

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "vin"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_active_vin_per_client"
            )
        ]


class ServiceRecord(SoftDeleteModel):
    SERVICE_TYPES = [
        ("vehicle_registration", "Vehicle Registration"),
        ("registration_renewal", "Registration Renewal"),
        ("duplicate_registration", "Duplicate Registration"),
        ("duplicate_title", "Duplicate Title"),
        ("title_only", "Title Only"),
        ("transfer_plate", "Plate Transfer"),
        ("new_plates", "New Plates"),
        ("replace_lost_item", "Replace lost or damage items"),
        ("surrender_plates", "Surrender plates"),
        ("motorcycle_registration", "Motorcycle Registration"),
        ("other", "Other"),
    ]
    TRANSACTION_TYPE_CHOICES = [
        ("OLRS", "OLRS"),
        ("transmittal", "Transmittal"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]
    PAYMENT_METHODS = [
        ("cash", "Cash"),
        ("zelle", "Zelle"),
        ("checks", "Checks"),
        ("visa", "Visa"),
        ("mastercard", "Mastercard"),
        ("discover", "Discover"),
        ("diners_club", "Diners Club"),
        ("american_express", "American Express"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="service_records",
    )
    handled_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="service_records",
    )
    
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="service_records", null=True, blank=True)
    
    # Snapshot fields for receipt/history
    client_name = models.CharField(max_length=200, blank=True, default="")
    client_identifier = models.CharField(max_length=100, blank=True, default="")
    client_address = models.CharField(max_length=255, blank=True, default="")
    
    vehicle_number = models.CharField(max_length=100, blank=True, default="")
    plate_number = models.CharField(max_length=50, blank=True, default="")
    vin = models.CharField(max_length=100, blank=True, default="")
    
    license_number = models.CharField(max_length=100, blank=True, default="")
    driver_license_number = models.CharField(max_length=100, blank=True, default="")
    phone_no = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    
    terminal_number = models.CharField(max_length=80, blank=True, default="")
    transaction_type = models.CharField(max_length=80, choices=TRANSACTION_TYPE_CHOICES, default="OLRS")
    
    service_type = models.CharField(max_length=100, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHODS, default="cash")
    payment_method_2 = models.CharField(max_length=50, choices=PAYMENT_METHODS, blank=True, null=True)
    paid_amount_2 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    source = models.CharField(max_length=100, default="walk-in")
    referral = models.ForeignKey(Referral, on_delete=models.SET_NULL, null=True, blank=True, related_name="service_records")
    
    processing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    dmv_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sales_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    dmv_sales_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Sales tax portion for the DMV.")
    credit_card_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Additional extra fees for PSB.")
    other_dmv_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Additional extra fees for DMV.")
    service_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    referral_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount owed by the referral for this service.")
    is_referral_paid = models.BooleanField(default=False, help_text="Has the referral paid for this service?")
    expected_payment_date = models.DateField(blank=True, null=True, help_text="When is the referral expected to pay?")
    
    notes = models.TextField(blank=True, default="")
    receipt_number = models.CharField(max_length=60, unique=True, blank=True, db_index=True)
    transaction_date = models.DateField(default=timezone.now, help_text="Date printed on the receipt")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    case_id = models.CharField(max_length=60, unique=True, blank=True, null=True, db_index=True)
    reminders_stopped = models.BooleanField(default=False)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount actually paid by the client/referral at the time of service.")


    @property
    def service_type_label(self):
        if self.service_type == "get_title":
            return "Title Only"
        # First check standard choices
        for key, label in self.SERVICE_TYPES:
            if self.service_type == key:
                return label
        # Then check custom services for this organization
        from .models import CustomServiceType
        custom = CustomServiceType.objects.filter(
            organization=self.organization, key=self.service_type
        ).first()
        if custom:
            return custom.label
        return self.service_type

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["organization", "status", "created_at"]),
        ]

    def get_payment_method_display(self):
        p1 = dict(self.PAYMENT_METHODS).get(self.payment_method, self.payment_method)
        if self.payment_method_2:
            p2 = dict(self.PAYMENT_METHODS).get(self.payment_method_2, self.payment_method_2)
            for key, val in self.PAYMENT_METHODS:
                if self.payment_method == key:
                    p1 = val
                if self.payment_method_2 == key:
                    p2 = val
            amt1 = (self.paid_amount or Decimal("0")) - (self.paid_amount_2 or Decimal("0"))
            amt2 = self.paid_amount_2 or Decimal("0")
            return f"{p1} (${amt1:.2f}) / {p2} (${amt2:.2f})"
        for key, val in self.PAYMENT_METHODS:
            if self.payment_method == key:
                return val
        return p1

    def save(self, *args, **kwargs):
        if self.vehicle:
            if not self.vehicle_number:
                self.vehicle_number = self.vehicle.vehicle_number or ""
            if not self.plate_number:
                self.plate_number = self.vehicle.plate_number or ""
            if not self.vin:
                self.vin = self.vehicle.vin or ""
            
            client = self.vehicle.client
            if client:
                if not self.client_name:
                    self.client_name = client.name
                if not self.client_address:
                    self.client_address = client.full_address
                if not self.phone_no:
                    self.phone_no = client.phone_number or ""
                if not self.email:
                    self.email = client.email
                if not self.driver_license_number:
                    self.driver_license_number = client.driver_license or ""

        if not self.receipt_number:
            ts = timezone.now().strftime("%Y%m%d%H%M%S")
            self.receipt_number = f"RCPT-{ts}-{self.organization_id or 'ORG'}"
        if not self.case_id:
            # Generate a unique case ID
            unique_part = get_random_string(6, allowed_chars='ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
            self.case_id = f"CASE-{unique_part}"
        self.service_fee = (
            (self.processing_fee or Decimal("0"))
            + (self.dmv_fee or Decimal("0"))
            + (self.sales_tax or Decimal("0"))
            + (self.dmv_sales_tax or Decimal("0"))
            + (self.credit_card_fee or Decimal("0"))
            + (self.other_fees or Decimal("0"))
            + (self.other_dmv_fee or Decimal("0"))
        )

        # Auto-derive outstanding balance: total due minus what was paid
        paid = self.paid_amount or Decimal("0")
        balance = self.service_fee - paid
        self.referral_balance = balance if balance > Decimal("0") else Decimal("0")

        # Automatically mark as paid if balance is zero
        if self.referral_balance <= 0:
            self.is_referral_paid = True
        else:
            self.is_referral_paid = False

        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.service_type} - {self.vehicle or 'No Vehicle'}"

    @property
    def net_profit(self):
        return self.processing_fee or Decimal("0")


class ServiceAuditLog(models.Model):
    ACTION_CHOICES = [
        ("created", "Created"),
        ("updated", "Updated"),
        ("status_changed", "Status Changed"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="service_audit_logs",
    )
    service_record = models.ForeignKey(
        ServiceRecord,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="service_audit_logs",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    details = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["service_record", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.actor.username} {self.action} {self.service_record.receipt_number}"


class ServiceDocument(models.Model):
    DOCUMENT_TYPES = [
        ("title", "Title"),
        ("bill_of_sale", "Bill of Sale"),
        ("driver_license", "Driver License"),
        ("insurance_id", "Insurance ID Card"),
        ("mv82", "MV82"),
        ("dtf802", "DTF 802"),
        ("reassignments", "Reassignments"),
        ("mv50", "MV50"),
        ("other", "Other docs"),
    ]

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True, blank=True
    )
    service_record = models.ForeignKey(
        ServiceRecord,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True, blank=True
    )
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    custom_name = models.CharField(max_length=150, blank=True, default="", help_text="Custom name for 'other' document types")
    file = models.FileField(upload_to="service_documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_name(self):
        if self.document_type == "other" and self.custom_name:
            return self.custom_name
        return self.get_document_type_display()

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_document_type_display()} for {self.vehicle or self.service_record}"


class ReferralPayment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]
    PAYMENT_TYPES = [
        ("debt", "Initial Debt"),
        ("payment", "Referral Payment"),
        ("adjustment", "Balance Adjustment"),
    ]
    
    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name="payments")
    service_record = models.ForeignKey(ServiceRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="referral_payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES, default="payment")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="completed")
    reference_number = models.CharField(max_length=100, blank=True, help_text="Check #, Transaction ID, etc.")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"Payment {self.id} - {self.referral.name}"


class AutomationLog(models.Model):
    LOG_TYPES = [
        ("confirmation", "Confirmation"),
        ("reminder_45", "45-Day Reminder"),
        ("reminder_30", "30-Day Reminder"),
        ("reminder_15", "15-Day Reminder"),
        ("final_warning", "Final Warning"),
        ("expired_warning", "Expired Warning"),
        ("completed", "Process Completed"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="automation_logs")
    service_record = models.ForeignKey(ServiceRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="automation_logs")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="automation_logs")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="automation_logs")
    
    log_type = models.CharField(max_length=30, choices=LOG_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    sent_to = models.EmailField()
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Automation Log"
        verbose_name_plural = "Automation Logs"

    def __str__(self):
        return f"{self.get_log_type_display()} - {self.client.name} - {self.timestamp}"


class FinanceStrategyNote(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="finance_strategy_note",
    )
    content = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"FinanceStrategyNote({self.user.username})"


class ClientNote(models.Model):
    client = models.ForeignKey("Client", on_delete=models.CASCADE, related_name="notes")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_client_notes")
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_client_notes",
    )
    content = models.TextField()
    follow_up_date = models.DateField(blank=True, null=True, db_index=True)
    is_done = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "-created_at"]),
            models.Index(fields=["follow_up_date", "is_done"]),
        ]

    def __str__(self):
        return f"ClientNote({self.client_id})"


class Notification(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications", db_index=True)
    client = models.ForeignKey("Client", on_delete=models.CASCADE, related_name="notifications", db_index=True)
    note = models.ForeignKey("ClientNote", on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    title = models.CharField(max_length=140)
    message = models.TextField(blank=True, default="")
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.WARNING, db_index=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["is_read", "-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"Notification({self.user_id}, read={self.is_read})"


class SiteNews(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site News"
        verbose_name_plural = "Site News"
        ordering = ["-created_at"]

class ClientIntake(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        PROCESSING = "processing", "In Progress"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="intakes")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    
    # Client Data
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, default="")
    dob = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    driver_license = models.CharField(max_length=50, blank=True, default="")
    ssn_last_4 = models.CharField(max_length=4, blank=True, default="")

    # Commercial / Business Account
    is_commercial = models.BooleanField(default=False)
    business_name = models.CharField(max_length=200, blank=True, default="")
    business_ein = models.CharField(max_length=20, blank=True, default="")
    
    # Address Data
    building_no = models.CharField(max_length=20, blank=True, default="")
    street_address = models.CharField(max_length=200, blank=True, default="")
    apartment = models.CharField(max_length=50, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=2, default="NY", blank=True)
    zip_code = models.CharField(max_length=10, blank=True, default="")
    county = models.CharField(max_length=100, blank=True, default="")
    
    # Vehicle Data
    vin = models.CharField(max_length=50)
    year = models.IntegerField(blank=True, null=True)
    make = models.CharField(max_length=100, blank=True, default="")
    model = models.CharField(max_length=100, blank=True, default="")
    vehicle_type = models.CharField(max_length=50, default="passenger")
    body_type = models.CharField(max_length=50, blank=True, null=True)
    fuel_type = models.CharField(max_length=50, default="gas")
    color = models.CharField(max_length=50, blank=True, default="")
    weight = models.CharField(max_length=50, blank=True, default="")
    cylinders = models.CharField(max_length=20, blank=True, default="")
    
    # Source / How did they find us
    SOURCE_CHOICES = [
        ("google_search", "Google Search"),
        ("walk_in", "Walk-In"),
        ("meta_platform", "Meta Platform"),
        ("google_campaigns", "Google Campaigns"),
        ("existing_client", "Existing Client"),
        ("dealer", "Dealer"),
        ("referral", "Referral"),
        ("cold_calling", "Cold Calling"),
        ("other", "Other"),
    ]
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default="google_search")

    # Transaction Details
    transaction_type = models.CharField(max_length=100, default="Registration and Title")
    insurance_company = models.CharField(max_length=150, blank=True, default="")
    insurance_policy_number = models.CharField(max_length=100, blank=True, default="")
    insurance_effective_date = models.DateField(blank=True, null=True)
    insurance_expiration_date = models.DateField(blank=True, null=True)
    
    # Document Uploads
    mv82_file = models.FileField(upload_to="intake_docs/mv82/", blank=True, null=True)
    dtf802_file = models.FileField(upload_to="intake_docs/dtf802/", blank=True, null=True)
    dtf803_file = models.FileField(upload_to="intake_docs/dtf803/", blank=True, null=True)
    other_docs = models.FileField(upload_to="intake_docs/other/", blank=True, null=True)

    requested_services = models.JSONField(default=list, blank=True)

    # MV-82 Comprehensive Fields
    mv82_transaction_type = models.CharField(max_length=100, blank=True, default="")
    plate_to_transfer = models.CharField(max_length=50, blank=True, default="")
    is_registrant_owner = models.BooleanField(default=True)
    
    # Owner Information (If different from registrant)
    owner_name = models.CharField(max_length=200, blank=True, default="")
    owner_nys_id = models.CharField(max_length=50, blank=True, default="")
    owner_dob = models.DateField(blank=True, null=True)
    
    # Co-Registrant Information
    co_registrant_name = models.CharField(max_length=200, blank=True, default="")
    co_registrant_nys_id = models.CharField(max_length=50, blank=True, default="")
    co_registrant_dob = models.DateField(blank=True, null=True)
    
    # Technical Vehicle Details
    odometer_reading = models.CharField(max_length=50, blank=True, default="")
    odometer_status = models.CharField(max_length=50, blank=True, default="") # Actual, Exceeds, Not Actual
    max_gross_weight = models.CharField(max_length=50, blank=True, default="")
    seating_capacity = models.CharField(max_length=20, blank=True, default="")
    num_axles = models.CharField(max_length=20, blank=True, default="")
    
    # Residential Address (If different from Mailing Address)
    residence_address_same = models.BooleanField(default=True)
    residence_building_no = models.CharField(max_length=20, blank=True, default="")
    residence_street_address = models.CharField(max_length=200, blank=True, default="")
    residence_apartment = models.CharField(max_length=50, blank=True, default="")
    residence_city = models.CharField(max_length=100, blank=True, default="")
    residence_state = models.CharField(max_length=2, default="NY", blank=True)
    residence_zip_code = models.CharField(max_length=10, blank=True, default="")
    residence_county = models.CharField(max_length=100, blank=True, default="")
    
    # Lienholder Information
    has_lien = models.BooleanField(default=False)
    lien_filing_code = models.CharField(max_length=5, blank=True, default="")
    lienholder_name = models.CharField(max_length=200, blank=True, default="")
    lienholder_address = models.CharField(max_length=255, blank=True, default="")
    
    # Lease/Rental/Bus Information
    is_leased = models.BooleanField(default=False)
    lessor_name = models.CharField(max_length=200, blank=True, default="")
    lessor_address = models.CharField(max_length=255, blank=True, default="")
    is_rental = models.BooleanField(default=False)
    is_bus = models.BooleanField(default=False)

    # Internal Tracking
    additional_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="processed_intakes")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Client Intake"
        verbose_name_plural = "Client Intakes"

    @property
    def name(self):
        if self.is_commercial and self.business_name:
            return self.business_name
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return f"Intake: {self.name} ({self.organization.name})"


class Space(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="spaces")
    key = models.CharField(max_length=60)
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    business_address = models.TextField(
        blank=True,
        default="",
        help_text="Address shown on custom inventory invoices and reports",
    )
    business_phone = models.CharField(max_length=40, blank=True, default="")
    business_email = models.EmailField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "key")
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} ({self.organization.name})"


class DocumentFolder(models.Model):
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="document_folders")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="document_folders",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_folders_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["space", "parent", "name"],
                name="unique_document_folder_name_per_parent",
            ),
        ]

    def __str__(self):
        return self.name


class SpaceDocumentType(models.Model):
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="document_types")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="document_types",
    )
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("space", "name")

    def __str__(self):
        return self.name


class SpaceDocumentRecord(models.Model):
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="document_records")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="document_records",
    )
    folder = models.ForeignKey(
        DocumentFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    document_type = models.ForeignKey(
        SpaceDocumentType,
        on_delete=models.PROTECT,
        related_name="records",
    )
    record_number = models.CharField(max_length=40, blank=True, default="", db_index=True)
    order_number = models.CharField(max_length=80, blank=True, default="")
    range_start = models.CharField(max_length=80, blank=True, default="")
    range_end = models.CharField(max_length=80, blank=True, default="")
    quantity = models.PositiveIntegerField(default=0)
    file = models.FileField(upload_to="space_documents/%Y/%m/", blank=True, null=True)
    notes = models.TextField(blank=True, default="")
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="space_documents_added",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.record_number or f"DOC-{self.id}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.record_number:
            number = f"DOC-{self.organization_id}-{self.id:05d}"
            SpaceDocumentRecord.objects.filter(pk=self.pk).update(record_number=number)
            self.record_number = number


class KnowledgeHubMaterial(models.Model):
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="materials")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_materials",
        help_text="Parent roadmap step for nesting sub-steps",
    )
    roadmap_name = models.CharField(
        max_length=100,
        default="General Roadmap",
        help_text="Name of the training roadmap this step belongs to",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    file = models.FileField(upload_to="knowledge_hub/", blank=True, null=True, help_text="Upload training PDF, document, or media file")
    external_url = models.URLField(blank=True, default="", help_text="Optional link to external video, course, or doc")
    step_number = models.PositiveIntegerField(default=1, help_text="Roadmap step order (1, 2, 3...)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["step_number", "created_at"]
        verbose_name = "Knowledge Hub Material"
        verbose_name_plural = "Knowledge Hub Materials"

    def __str__(self):
        return f"{self.step_number}. {self.title}"


class InventoryCategory(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="inventory_categories")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="inventory_categories")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("space", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class InventoryProduct(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="inventory_products")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="inventory_products")
    category = models.ForeignKey(
        InventoryCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=80, blank=True, default="")
    description = models.TextField(blank=True, default="")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Last unit cost from supplier",
    )
    primary_supplier = models.ForeignKey(
        "InventorySupplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    quantity = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    @property
    def total_value(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return self.name


class InventoryBuyer(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="inventory_buyers")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="inventory_buyers")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=40, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InventoryInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Credit/Debit Card"
        ZELLE = "zelle", "Zelle"
        CHECK = "check", "Check"
        OTHER = "other", "Other"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="inventory_invoices")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="inventory_invoices")
    invoice_number = models.CharField(max_length=40, unique=True)
    buyer = models.ForeignKey(
        InventoryBuyer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    buyer_name = models.CharField(max_length=200)
    buyer_phone = models.CharField(max_length=40, blank=True, default="")
    buyer_email = models.EmailField(blank=True, default="")
    buyer_address = models.TextField(blank=True, default="")
    invoice_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    notes = models.TextField(blank=True, default="")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    sales_tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_invoices_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-invoice_date", "-created_at"]

    def __str__(self):
        return f"{self.invoice_number} — {self.buyer_name}"


class InventoryInvoiceLine(models.Model):
    invoice = models.ForeignKey(InventoryInvoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(
        InventoryProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        self.line_total = Decimal(self.quantity) * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} x{self.quantity}"


class InventoryStockMovement(models.Model):
    class MovementType(models.TextChoices):
        SALE = "sale", "Sale"
        RECEIVE = "receive", "Stock Received"
        ADJUSTMENT = "adjustment", "Manual Adjustment"
        RETURN = "return", "Return"

    product = models.ForeignKey(InventoryProduct, on_delete=models.CASCADE, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity_change = models.IntegerField()
    quantity_after = models.IntegerField()
    reference = models.CharField(max_length=80, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name}: {self.quantity_change:+d}"


class InventorySupplier(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="inventory_suppliers")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="inventory_suppliers")
    name = models.CharField(max_length=200)
    company_name = models.CharField(max_length=200, blank=True, default="")
    contact_person = models.CharField(max_length=120, blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InventoryPurchase(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="inventory_purchases")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="inventory_purchases")
    supplier = models.ForeignKey(InventorySupplier, on_delete=models.CASCADE, related_name="purchases")
    purchase_number = models.CharField(max_length=40, unique=True)
    purchase_date = models.DateField()
    notes = models.TextField(blank=True, default="")
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_purchases_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-purchase_date", "-created_at"]

    def __str__(self):
        return f"{self.purchase_number} — {self.supplier.name}"


class InventoryPurchaseLine(models.Model):
    purchase = models.ForeignKey(InventoryPurchase, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(
        InventoryProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_lines",
    )
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        self.line_total = Decimal(self.quantity) * self.unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} x{self.quantity}"


class UserSession(models.Model):
    """
    Tracks the single allowed active session per user.
    Stored in the database (not cache) so it works correctly on
    multi-worker production servers (gunicorn, etc.).
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="active_session")
    session_key = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_user_session"

    def __str__(self):
        return f"{self.user.username} → {self.session_key[:8]}..."


class InsuranceCompany(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="insurance_companies")
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("organization", "name")

    def __str__(self):
        return self.name


class InsurancePolicy(models.Model):
    class StageChoices(models.TextChoices):
        QUOTE = "quote", "Quote"
        BOUND = "bound", "Bound"
        ENDORSEMENT = "endorsement", "Endorsement"

    QUOTE_STAGES = frozenset({StageChoices.QUOTE})
    BOUND_STAGES = frozenset({StageChoices.BOUND})

    class StatusChoices(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        PENDING = "pending", "Pending"
        REJECTED = "rejected", "Rejected"

    class SourceChoices(models.TextChoices):
        WALK_IN = "walk_in", "Walk-In"
        GOOGLE_SEARCH = "google_search", "Google Search"
        META_PLATFORM = "meta_platform", "Meta Platform"
        GOOGLE_CAMPAIGNS = "google_campaigns", "Google Campaigns"
        EXISTING_CLIENT = "existing_client", "Existing Client"
        DEALER = "dealer", "Dealer"
        REFERRAL = "referral", "Referral"
        COLD_CALLING = "cold_calling", "Cold Calling"

    class BusinessTypeChoices(models.TextChoices):
        NEW_BUSINESS = "new_business", "New Business"
        RENEWAL = "renewal", "Renewal"
        REWRITE = "rewrite", "Rewrite"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="insurance_policies")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="insurance_policies")
    policy_number = models.CharField(max_length=100)
    insurance_company = models.ForeignKey(InsuranceCompany, on_delete=models.CASCADE, related_name="policies")
    premium = models.DecimalField(max_digits=12, decimal_places=2)
    broker_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, blank=True, help_text="Broker fee taken by the agent")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Commission rate in percentage (e.g. 15.00 for 15%)")
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    INSURANCE_TYPE_CHOICES = [
        ("auto_personal", "AUTO PERSONAL"),
        ("motor_cycle", "MOTOR CYCLE"),
        ("commercial_auto", "COMMERCIAL AUTO"),
        ("trucking", "TRUCKING"),
        ("contractors", "CONTRACTORS"),
        ("landscaping", "LANDSCAPING"),
        ("dealer_plates", "DEALER PLATES"),
        ("home_owners", "HOME OWNERS"),
        ("ho3", "HO3"),
        ("ho4", "HO4"),
        ("ho6", "HO6"),
        ("dwelling", "DWELLING"),
        ("umbrella", "UMBRELLA"),
        ("business_owners_policy", "BUSINESS OWNERS POLICY"),
        ("general_liability", "GENERAL LIABILITY"),
        ("workers_compensation", "WORKERS COMPENSATION"),
        ("disability", "DISABILITY"),
    ]

    stage = models.CharField(max_length=20, choices=StageChoices.choices, default=StageChoices.QUOTE)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.ACTIVE)
    insurance_type = models.CharField(max_length=30, choices=INSURANCE_TYPE_CHOICES, blank=True, default="", help_text="Type of insurance policy")
    source = models.CharField(max_length=50, choices=SourceChoices.choices, default=SourceChoices.WALK_IN)
    business_type = models.CharField(max_length=50, choices=BusinessTypeChoices.choices, default=BusinessTypeChoices.NEW_BUSINESS)

    class PolicyPaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        ZELLE = "zelle", "Zelle"
        CREDIT_CARD = "credit_card", "Credit Card"
        CHECKS = "checks", "Checks"

    payment_method = models.CharField(
        max_length=20,
        choices=PolicyPaymentMethod.choices,
        blank=True,
        default="",
        help_text="How the broker fee was collected",
    )
    bound_date = models.DateField(blank=True, null=True, help_text="Date the policy was bound")
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="added_insurance_policies", help_text="Agent who added this policy/quote")
    
    start_date = models.DateField()
    end_date = models.DateField()
    insurance_period_months = models.IntegerField(default=6, help_text="Total insurance period in months")
    inactive_date = models.DateField(blank=True, null=True, help_text="Date the policy became inactive")
    unearned_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, blank=True)
    commission_received = models.BooleanField(
        default=False,
        help_text="When checked, this policy's commission counts toward Received Commission.",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.policy_number} - {self.client.name if self.client else 'Unknown'}"

    def save(self, *args, **kwargs):
        # Convert dates to date objects if they are strings
        from datetime import date, datetime
        
        def _parse_date(val):
            if not val:
                return None
            if isinstance(val, (date, datetime)):
                if isinstance(val, datetime):
                    return val.date()
                return val
            try:
                return datetime.strptime(str(val).strip(), "%Y-%m-%d").date()
            except ValueError:
                return None

        self.start_date = _parse_date(self.start_date)
        self.end_date = _parse_date(self.end_date)
        self.inactive_date = _parse_date(self.inactive_date)

        # Calculate commission_amount
        self.commission_amount = Decimal(str(self.premium)) * (Decimal(str(self.commission_rate)) / Decimal("100.00"))
        
        from .insurance_commissions import calculate_unearned_commission

        if self.status == self.StatusChoices.INACTIVE:
            self.unearned_commission = calculate_unearned_commission(
                self.commission_amount,
                self.start_date,
                self.end_date,
                self.inactive_date,
                insurance_period_months=self.insurance_period_months,
            )
        else:
            self.unearned_commission = Decimal("0.00")

        super().save(*args, **kwargs)


class DailyPaymentTransaction(models.Model):
    class PaymentType(models.TextChoices):
        NEW_BUSINESS = "new_business", "New Business"
        RENEWAL = "renewal", "Renewal"
        MONTHLY_PAYMENT = "monthly_payment", "Monthly Payment"
        ENDORSEMENT = "endorsement", "Endorsement"
        MISC = "misc", "Misc"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        ZELLE = "zelle", "Zelle"
        CREDIT_CARD = "credit_card", "Credit Card"
        CHECKS = "checks", "Checks"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="daily_payment_transactions")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="daily_payment_transactions")
    insurance_policy = models.ForeignKey(
        InsurancePolicy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_payment_transactions",
    )
    transaction_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_type = models.CharField(max_length=30, choices=PaymentType.choices)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_daily_payments",
    )
    notes = models.TextField(blank=True, default="")
    is_cleared = models.BooleanField(default=False, help_text="Bank has cleared this payment")
    cleared_date = models.DateField(null=True, blank=True, help_text="Date the bank cleared the amount")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transaction_date", "-created_at"]

    def __str__(self):
        return f"{self.transaction_date} — {self.client} — ${self.amount}"


class BankAccount(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="bank_accounts")
    account_name = models.CharField(max_length=120)
    bank_name = models.CharField(max_length=120, blank=True, default="")
    account_number = models.CharField(max_length=50, blank=True, default="")
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["account_name"]

    def __str__(self):
        return f"{self.account_name} ({self.bank_name}) - ${self.balance}"


class BankTransaction(models.Model):
    class TransactionType(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="transactions")
    insurance_company = models.ForeignKey(InsuranceCompany, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions")
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.transaction_type.upper()}: ${self.amount} ({self.category})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_amount = Decimal("0.00")
        old_type = ""
        if not is_new:
            old_obj = BankTransaction.objects.get(pk=self.pk)
            old_amount = old_obj.amount
            old_type = old_obj.transaction_type

        super().save(*args, **kwargs)

        # Update balance
        account = self.bank_account
        if is_new:
            if self.transaction_type == self.TransactionType.INCOME:
                account.balance += self.amount
            else:
                account.balance -= self.amount
        else:
            # Revert old transaction effect
            if old_type == self.TransactionType.INCOME:
                account.balance -= old_amount
            else:
                account.balance += old_amount
            # Apply new transaction effect
            if self.transaction_type == self.TransactionType.INCOME:
                account.balance += self.amount
            else:
                account.balance -= self.amount
        account.save()

    def delete(self, *args, **kwargs):
        account = self.bank_account
        if self.transaction_type == self.TransactionType.INCOME:
            account.balance -= self.amount
        else:
            account.balance += self.amount
        account.save()
        super().delete(*args, **kwargs)


def insurance_company_document_upload_path(instance, filename):
    return f"insurance_company_docs/{instance.insurance_company.id}/{filename}"


class InsuranceCompanyDocument(models.Model):
    insurance_company = models.ForeignKey(
        InsuranceCompany,
        on_delete=models.CASCADE,
        related_name="documents"
    )
    title = models.CharField(max_length=200, blank=True, default="")
    document = models.FileField(upload_to=insurance_company_document_upload_path)
    document_date = models.DateField(blank=True, null=True, help_text="Date associated with this document")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.insurance_company.name} — {self.title or self.document.name}"


class MotorclubConfig(models.Model):
    """Per-PSB profit split configuration for Motor Club tiers ($35 / $50 / $75 / $100)."""

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="motorclub_config",
    )
    tier_35_provider_take = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("20.00"),
        help_text="Amount the Motor Club provider keeps from the $35 plan.",
    )
    tier_50_provider_take = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("28.00"),
        help_text="Amount the Motor Club provider keeps from the $50 plan.",
    )
    tier_75_provider_take = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("42.00"),
        help_text="Amount the Motor Club provider keeps from the $75 plan.",
    )
    tier_100_provider_take = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("55.00"),
        help_text="Amount the Motor Club provider keeps from the $100 plan.",
    )
    provider_profit_notes = models.TextField(
        blank=True,
        default="",
        help_text="Notes about Motor Club provider / company profit expectations.",
    )
    psb_profit_notes = models.TextField(
        blank=True,
        default="",
        help_text="Notes about PSB profit goals for Motor Club sales.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Motor Club configuration"

    def __str__(self):
        return f"Motor Club config — {self.organization.name}"


class MotorclubB2BPartner(models.Model):
    """Agency or company selling Motor Club through a B2B partnership."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="motorclub_b2b_partners",
    )
    name = models.CharField(max_length=160)
    contact_name = models.CharField(max_length=120, blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("organization", "name")

    def __str__(self):
        return self.name


class MotorclubMembership(models.Model):
    """Roadside assistance membership sold via insurance client, B2B, or direct."""

    class TierChoices(models.IntegerChoices):
        TIER_35 = 35, "$35 / year"
        TIER_50 = 50, "$50 / year"
        TIER_75 = 75, "$75 / year"
        TIER_100 = 100, "$100 / year"

    class ChannelChoices(models.TextChoices):
        INSURANCE_CLIENT = "insurance_client", "Insurance Client"
        B2B = "b2b", "B2B Partner"
        DIRECT = "direct", "Direct / Walk-In"

    class StatusChoices(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="motorclub_memberships",
    )
    space = models.ForeignKey(
        Space,
        on_delete=models.CASCADE,
        related_name="motorclub_memberships",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="motorclub_memberships",
    )
    b2b_partner = models.ForeignKey(
        MotorclubB2BPartner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships",
    )
    insurance_policy = models.ForeignKey(
        InsurancePolicy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="motorclub_memberships",
        help_text="Optional link when sold to an existing insurance client.",
    )
    channel = models.CharField(
        max_length=20,
        choices=ChannelChoices.choices,
        default=ChannelChoices.DIRECT,
    )
    tier = models.PositiveSmallIntegerField(choices=TierChoices.choices)
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE,
    )
    membership_number = models.CharField(max_length=40, blank=True, default="")
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    provider_profit = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Motor Club provider / company profit for this membership.",
    )
    psb_profit = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="PSB profit for this membership.",
    )
    notes = models.TextField(blank=True, default="")
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="added_motorclub_memberships",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        label = self.membership_number or f"MC-{self.id}"
        return f"{label} — {self.client.name} (${self.tier})"

    @property
    def tier_price(self):
        return Decimal(str(self.tier))

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.membership_number:
            number = f"MC-{self.organization_id}-{self.id:05d}"
            MotorclubMembership.objects.filter(pk=self.pk).update(membership_number=number)
            self.membership_number = number

