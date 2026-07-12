"""TLC Policy Profitability Engine — models for the TLC insurance agency space."""

from decimal import Decimal

from django.conf import settings
from django.db import models


class TLCPolicy(models.Model):
    """A TLC insurance policy tracked for full agency profitability."""

    class PolicyType(models.TextChoices):
        NEW_BUSINESS = "new_business", "New Business"
        RENEWAL = "renewal", "Renewal"
        REWRITE = "rewrite", "Rewrite"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"
        CANCELLED = "cancelled", "Cancelled"
        SUSPENDED = "suspended", "Suspended"
        REINSTATED = "reinstated", "Reinstated"
        EXPIRED = "expired", "Expired"

    organization = models.ForeignKey(
        "Organization", on_delete=models.CASCADE, related_name="tlc_policies"
    )
    space = models.ForeignKey("Space", on_delete=models.CASCADE, related_name="tlc_policies")
    client = models.ForeignKey(
        "Client", on_delete=models.SET_NULL, null=True, blank=True, related_name="tlc_policies"
    )
    vehicle = models.ForeignKey(
        "Vehicle", on_delete=models.SET_NULL, null=True, blank=True, related_name="tlc_policies"
    )
    insurance_policy = models.ForeignKey(
        "InsurancePolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tlc_policies",
        help_text="Optional link to the general insurance CRM policy.",
    )

    policy_number = models.CharField(max_length=100, db_index=True)
    carrier = models.CharField(max_length=120, blank=True, default="")
    policy_type = models.CharField(
        max_length=20, choices=PolicyType.choices, default=PolicyType.NEW_BUSINESS
    )
    named_insured = models.CharField(max_length=200, blank=True, default="")
    business_name = models.CharField(max_length=200, blank=True, default="")
    tlc_base_number = models.CharField(max_length=40, blank=True, default="")
    tlc_license_number = models.CharField(max_length=40, blank=True, default="")
    vin = models.CharField(max_length=17, blank=True, default="")
    plate_number = models.CharField(max_length=20, blank=True, default="")
    driver_name = models.CharField(max_length=200, blank=True, default="")
    broker_name = models.CharField(max_length=120, blank=True, default="")
    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tlc_produced_policies",
    )
    csr = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tlc_csr_policies",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    effective_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    renewal_date = models.DateField(null=True, blank=True)

    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text="Carrier commission rate as a percentage.",
    )
    carrier_commission_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    renewal_commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    producer_commission_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    csr_commission_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    broker_fee_collected = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    finance_fee_collected = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    amount_collected_from_client = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Total premium/fees collected from the customer (excluding DMV).",
    )
    amount_remitted_to_carrier = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    carrier_credits = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    carrier_refunds = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    commission_received = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    commission_chargeback = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    endorsement_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    notes = models.TextField(blank=True, default="")
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="added_tlc_policies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("organization", "policy_number")
        verbose_name = "TLC policy"
        verbose_name_plural = "TLC policies"

    def __str__(self):
        return f"{self.policy_number} — {self.named_insured or self.business_name or 'TLC Policy'}"

    def save(self, *args, **kwargs):
        premium = Decimal("0")
        try:
            breakdown = self.premium_breakdown
            if breakdown:
                premium = breakdown.total_written_premium or Decimal("0")
        except TLCPremiumBreakdown.DoesNotExist:
            if self.pk:
                breakdown = TLCPremiumBreakdown.objects.filter(policy_id=self.pk).first()
                if breakdown:
                    premium = breakdown.total_written_premium or Decimal("0")
        if premium and self.commission_rate:
            self.carrier_commission_amount = (
                premium * (Decimal(str(self.commission_rate)) / Decimal("100"))
            ).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)


class TLCPremiumBreakdown(models.Model):
    """Carrier premium and fee structure for a TLC policy."""

    policy = models.OneToOneField(
        TLCPolicy, on_delete=models.CASCADE, related_name="premium_breakdown"
    )
    total_written_premium = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    down_payment = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    amount_financed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    number_of_installments = models.PositiveSmallIntegerField(default=0)
    monthly_installment = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    policy_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    installment_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    finance_charge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    taxes = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    mvr_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    inspection_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    sr22_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    additional_driver_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    additional_vehicle_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    endorsement_charges = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    cancellation_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    reinstatement_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    returned_check_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    late_payment_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    other_carrier_fees = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        verbose_name = "TLC premium breakdown"
        verbose_name_plural = "TLC premium breakdowns"

    def __str__(self):
        return f"Premium — {self.policy.policy_number}"


class TLCInstallment(models.Model):
    """Single installment on a TLC policy payment schedule."""

    policy = models.ForeignKey(
        TLCPolicy, on_delete=models.CASCADE, related_name="installments"
    )
    installment_number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    is_paid = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)
    late_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    nsf_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    was_reinstated = models.BooleanField(default=False)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["installment_number"]
        unique_together = ("policy", "installment_number")

    def __str__(self):
        return f"#{self.installment_number} — {self.policy.policy_number}"


class TLCReinstatement(models.Model):
    """Cancellation and reinstatement history for a TLC policy."""

    policy = models.ForeignKey(
        TLCPolicy, on_delete=models.CASCADE, related_name="reinstatements"
    )
    cancellation_date = models.DateField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    reinstatement_date = models.DateField(null=True, blank=True)
    reinstatement_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tlc_reinstatements_processed",
    )
    carrier_confirmation = models.CharField(max_length=120, blank=True, default="")
    is_paid = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reinstatement_date", "-created_at"]

    def __str__(self):
        return f"Reinstatement — {self.policy.policy_number}"


class TLCEndorsement(models.Model):
    """Endorsement affecting premium and commission on a TLC policy."""

    class EndorsementType(models.TextChoices):
        ADDED_DRIVER = "added_driver", "Added Driver"
        REMOVED_DRIVER = "removed_driver", "Removed Driver"
        ADDRESS_CHANGE = "address_change", "Address Change"
        VEHICLE_CHANGE = "vehicle_change", "Vehicle Change"
        COVERAGE_CHANGE = "coverage_change", "Coverage Change"
        PLATE_CHANGE = "plate_change", "Plate Change"
        TLC_NUMBER_CHANGE = "tlc_number_change", "TLC Number Change"
        OTHER = "other", "Other"

    policy = models.ForeignKey(
        TLCPolicy, on_delete=models.CASCADE, related_name="endorsements"
    )
    endorsement_type = models.CharField(
        max_length=30, choices=EndorsementType.choices, default=EndorsementType.OTHER
    )
    premium_difference = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    commission_difference = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    effective_date = models.DateField(null=True, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tlc_endorsements_processed",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-created_at"]

    def __str__(self):
        return f"{self.get_endorsement_type_display()} — {self.policy.policy_number}"


class TLCDMVService(models.Model):
    """DMV / TLC service revenue tied to a policy."""

    class ServiceType(models.TextChoices):
        REGISTRATION = "registration", "Registration"
        PLATE_TRANSFER = "plate_transfer", "Plate Transfer"
        TITLE = "title", "Title"
        DUPLICATE_REGISTRATION = "duplicate_registration", "Duplicate Registration"
        INSPECTION = "inspection", "Inspection"
        TLC_FILING = "tlc_filing", "TLC Filing"
        OTHER = "other", "Other"

    policy = models.ForeignKey(
        TLCPolicy, on_delete=models.CASCADE, related_name="dmv_services"
    )
    service_type = models.CharField(
        max_length=30, choices=ServiceType.choices, default=ServiceType.REGISTRATION
    )
    fee_charged = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    dmv_tlc_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    agency_profit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    service_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-service_date", "-created_at"]

    def save(self, *args, **kwargs):
        self.agency_profit = (self.fee_charged - self.dmv_tlc_cost).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_service_type_display()} — {self.policy.policy_number}"


class TLCAgencyExpense(models.Model):
    """Agency expense allocated to a TLC policy."""

    class ExpenseType(models.TextChoices):
        PRODUCER_COMMISSION = "producer_commission", "Producer Commission"
        CSR_BONUS = "csr_bonus", "CSR Bonus"
        MERCHANT_FEES = "merchant_fees", "Merchant Fees"
        PROCESSING_FEES = "processing_fees", "Processing Fees"
        CHARGEBACKS = "chargebacks", "Chargebacks"
        ADVERTISING = "advertising", "Advertising Cost"
        OFFICE_ALLOCATION = "office_allocation", "Office Allocation"
        SOFTWARE = "software", "Software Cost"
        PAYROLL = "payroll", "Payroll Allocation"
        MISC = "misc", "Misc Expenses"

    policy = models.ForeignKey(
        TLCPolicy, on_delete=models.CASCADE, related_name="agency_expenses"
    )
    expense_type = models.CharField(
        max_length=30, choices=ExpenseType.choices, default=ExpenseType.MISC
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    expense_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.get_expense_type_display()} — {self.policy.policy_number}"


class TLCCarrierRemittance(models.Model):
    """Payment remitted from the agency to the carrier."""

    policy = models.ForeignKey(
        TLCPolicy, on_delete=models.CASCADE, related_name="carrier_remittances"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    remittance_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-remittance_date", "-created_at"]

    def __str__(self):
        return f"Remittance ${self.amount} — {self.policy.policy_number}"


class TLCPolicyDocument(models.Model):
    """Document attached to a TLC policy."""

    class DocumentType(models.TextChoices):
        DRIVER_LICENSE = "driver_license", "Driver License"
        TLC_LICENSE = "tlc_license", "TLC License"
        REGISTRATION = "registration", "Registration"
        CERTIFICATE_OF_INSURANCE = "coi", "Certificate of Insurance"
        ID_CARDS = "id_cards", "ID Cards"
        PAYMENT_RECEIPT = "payment_receipt", "Payment Receipt"
        FINANCE_AGREEMENT = "finance_agreement", "Finance Agreement"
        CARRIER_NOTICE = "carrier_notice", "Carrier Notice"
        CANCELLATION_NOTICE = "cancellation_notice", "Cancellation Notice"
        REINSTATEMENT_NOTICE = "reinstatement_notice", "Reinstatement Notice"
        DMV_DOCUMENT = "dmv_document", "DMV Document"
        PHOTO = "photo", "Photo"
        SIGNED_APPLICATION = "signed_application", "Signed Application"
        OTHER = "other", "Other"

    policy = models.ForeignKey(
        TLCPolicy, on_delete=models.CASCADE, related_name="documents"
    )
    document_type = models.CharField(
        max_length=30, choices=DocumentType.choices, default=DocumentType.OTHER
    )
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="tlc_policy_documents/", blank=True, null=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tlc_documents_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


class TLCPolicyTimelineEvent(models.Model):
    """Lifecycle event on a TLC policy timeline."""

    class EventType(models.TextChoices):
        QUOTE = "quote", "Quote"
        BOUND = "bound", "Bound"
        DOWN_PAYMENT = "down_payment", "Down Payment"
        ISSUED = "issued", "Issued"
        INSTALLMENT = "installment", "Installment"
        CANCELLATION = "cancellation", "Cancellation"
        REINSTATEMENT = "reinstatement", "Reinstatement"
        ENDORSEMENT = "endorsement", "Endorsement"
        RENEWAL = "renewal", "Renewal"
        EXPIRED = "expired", "Expired"

    policy = models.ForeignKey(
        TLCPolicy, on_delete=models.CASCADE, related_name="timeline_events"
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    event_date = models.DateField(null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tlc_timeline_events_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["event_date", "created_at"]

    def __str__(self):
        return f"{self.title} — {self.policy.policy_number}"
