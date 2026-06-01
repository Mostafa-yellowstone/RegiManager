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
    invite_code = models.CharField(max_length=20, unique=True, default=generate_invite_code)
    portal_token = models.CharField(max_length=64, unique=True, blank=True, null=True)
    max_agents = models.IntegerField(default=5, help_text="Maximum number of agents allowed for this PSB.")
    is_automation_enabled = models.BooleanField(default=False, help_text="Enable Automation Hub features for this PSB.")
    is_active = models.BooleanField(default=True, help_text="Enable or disable this PSB account.")
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
    
    # Uploaded Documents
    mv82_file = models.FileField(upload_to="client_docs/mv82/", blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_address(self):
        parts = [self.building_no, self.street_address, self.apartment, self.city, self.state, self.zip_code]
        return ", ".join([p for p in parts if p])

    def __str__(self):
        return self.name

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
    vin = models.CharField(max_length=50, unique=True, db_index=True)
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


class ServiceRecord(SoftDeleteModel):
    SERVICE_TYPES = [
        ("vehicle_registration", "Vehicle Registration"),
        ("registration_renewal", "Registration Renewal"),
        ("get_title", "Get A Title"),
        ("transfer_plate", "Plate Transfer"),
        ("replace_lost_item", "Replace lost or damage items"),
        ("surrender_plates", "Surrender plates"),
        ("motorcycle_registration", "Motorcycle Registration"),
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
    source = models.CharField(max_length=100, default="walk-in")
    referral = models.ForeignKey(Referral, on_delete=models.SET_NULL, null=True, blank=True, related_name="service_records")
    
    processing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    dmv_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sales_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    credit_card_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Additional extra fees.")
    service_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    referral_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount owed by the referral for this service.")
    is_referral_paid = models.BooleanField(default=False, help_text="Has the referral paid for this service?")
    expected_payment_date = models.DateField(blank=True, null=True, help_text="When is the referral expected to pay?")
    
    notes = models.TextField(blank=True, default="")
    receipt_number = models.CharField(max_length=60, unique=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    case_id = models.CharField(max_length=60, unique=True, blank=True, null=True, db_index=True)
    reminders_stopped = models.BooleanField(default=False)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount actually paid by the client/referral at the time of service.")


    @property
    def service_type_label(self):
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

    def save(self, *args, **kwargs):
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
            + (self.credit_card_fee or Decimal("0"))
            + (self.other_fees or Decimal("0"))
        )
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
    file = models.FileField(upload_to="service_documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

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

    def __str__(self):
        return f"Intake: {self.first_name} {self.last_name} ({self.organization.name})"


class InventoryService(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="inventory_services")
    key = models.CharField(max_length=60)
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    stock = models.IntegerField(default=0, help_text="Available stock / items")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "key")
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} ({self.organization.name})"


class MarketingCampaignLog(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="marketing_campaigns")
    inventory_service = models.ForeignKey(InventoryService, on_delete=models.CASCADE, related_name="campaigns")
    subject = models.CharField(max_length=255)
    body = models.TextField()
    image = models.ImageField(upload_to="marketing_campaigns/", blank=True, null=True)
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="sent_campaigns")
    recipients_count = models.IntegerField(default=0)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"Campaign: {self.subject} ({self.sent_at.strftime('%Y-%m-%d %H:%M')})"


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
