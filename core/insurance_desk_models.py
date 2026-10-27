"""Agency desk records: coverages, transactions, carrier quotes, commissions, certificates, claims."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class InsuranceCoverage(models.Model):
    class Code(models.TextChoices):
        BI = "bi", "Bodily injury"
        PD = "pd", "Property damage"
        PIP = "pip", "PIP"
        OBEL = "obel", "OBEL"
        UM = "um", "Uninsured motorist"
        SUM = "sum", "SUM"
        MED = "med", "Medical payments"
        COMP = "comp", "Comprehensive"
        COLL = "coll", "Collision"
        RENTAL = "rental", "Rental"
        TOWING = "towing", "Towing"

    policy = models.ForeignKey("InsurancePolicy", on_delete=models.CASCADE, related_name="coverages")
    vehicle = models.ForeignKey(
        "InsurancePolicyVehicle",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coverages",
    )
    code = models.CharField(max_length=20, choices=Code.choices)
    limit_text = models.CharField(max_length=80, blank=True, default="")
    deductible = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["code", "id"]
        verbose_name = "Insurance coverage"
        verbose_name_plural = "Insurance coverages"

    def __str__(self):
        return f"{self.get_code_display()} · {self.policy_id}"


class InsurancePolicyTransaction(models.Model):
    class Kind(models.TextChoices):
        NEW_BUSINESS = "new_business", "New business"
        ENDORSEMENT = "endorsement", "Endorsement"
        CANCELLATION = "cancellation", "Cancellation"
        REINSTATEMENT = "reinstatement", "Reinstatement"
        RENEWAL = "renewal", "Renewal"

    class CancelReason(models.TextChoices):
        INSURED = "insured_request", "Insured request"
        NON_PAY = "non_pay", "Non-pay"
        SOLD = "sold_vehicle", "Sold the vehicle"
        MOVED = "moved", "Moved away"
        UNDERWRITING = "underwriting", "Underwriting"
        OTHER = "other", "Other"

    class RequestedBy(models.TextChoices):
        INSURED = "insured", "Insured"
        CARRIER = "carrier", "Carrier"
        FINANCE = "finance", "Finance company"
        AGENCY = "agency", "Agency"

    policy = models.ForeignKey("InsurancePolicy", on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    effective_date = models.DateField()
    old_premium = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    new_premium = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    reason = models.CharField(max_length=20, choices=CancelReason.choices, blank=True, default="")
    requested_by = models.CharField(max_length=20, choices=RequestedBy.choices, blank=True, default="")
    notice_date = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.policy_id}"


class InsuranceQuoteOption(models.Model):
    """One carrier quote on a lead. The agency shops carriers and records the result here."""

    class Decision(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    lead = models.ForeignKey("InsuranceQuoteLead", on_delete=models.CASCADE, related_name="options")
    company = models.ForeignKey(
        "InsuranceCompany",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_options",
    )
    carrier_name = models.CharField(max_length=120, blank=True, default="")
    term_premium = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    down_payment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    term_months = models.PositiveSmallIntegerField(default=6)
    bi_limit = models.CharField(max_length=40, blank=True, default="")
    pd_limit = models.CharField(max_length=40, blank=True, default="")
    pip_limit = models.CharField(max_length=40, blank=True, default="")
    um_limit = models.CharField(max_length=40, blank=True, default="")
    comp_deductible = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    coll_deductible = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    decision = models.CharField(max_length=20, choices=Decision.choices, default=Decision.PENDING)
    note = models.CharField(max_length=500, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["term_premium", "id"]

    def __str__(self):
        return f"{self.carrier_label} · {self.term_premium}"

    @property
    def carrier_label(self) -> str:
        if self.company_id:
            return self.company.name
        return self.carrier_name or "Carrier"


def _statement_upload(instance, filename):
    return f"insurance_statements/{instance.organization_id}/{filename}"


class InsuranceCommissionStatement(models.Model):
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="commission_statements",
    )
    company = models.ForeignKey(
        "InsuranceCompany",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commission_statements",
    )
    statement_date = models.DateField(null=True, blank=True)
    source_name = models.CharField(max_length=200, blank=True, default="")
    file = models.FileField(upload_to=_statement_upload, blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.source_name or f"Statement {self.pk}"


class InsuranceCommissionStatementLine(models.Model):
    class Status(models.TextChoices):
        MATCHED = "matched", "Matched"
        SHORT = "short", "Short pay"
        UNMATCHED = "unmatched", "Unmatched"

    statement = models.ForeignKey(
        InsuranceCommissionStatement,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    policy_number = models.CharField(max_length=100)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    expected_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNMATCHED)
    policy = models.ForeignKey(
        "InsurancePolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commission_statement_lines",
    )

    class Meta:
        ordering = ["policy_number", "id"]


class InsuranceCertificateHolder(models.Model):
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="certificate_holders",
    )
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=400, blank=True, default="")

    class Meta:
        ordering = ["name"]
        unique_together = ("organization", "name")

    def __str__(self):
        return self.name


def _certificate_upload(instance, filename):
    return f"insurance_certificates/{instance.policy_id}/{filename}"


class InsuranceCertificate(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        ISSUED = "issued", "Issued"

    policy = models.ForeignKey("InsurancePolicy", on_delete=models.CASCADE, related_name="certificates")
    holder = models.ForeignKey(
        InsuranceCertificateHolder,
        on_delete=models.PROTECT,
        related_name="certificates",
    )
    additional_insured = models.BooleanField(default=False)
    waiver_of_subrogation = models.BooleanField(default=False)
    description = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    file = models.FileField(upload_to=_certificate_upload, blank=True, null=True)
    requested_by_client = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.holder} · {self.policy_id}"


class InsuranceClaim(models.Model):
    class Status(models.TextChoices):
        REPORTED = "reported", "Reported"
        WITH_CARRIER = "with_carrier", "With carrier"
        CLOSED = "closed", "Closed"

    policy = models.ForeignKey("InsurancePolicy", on_delete=models.CASCADE, related_name="claims")
    vehicle = models.ForeignKey(
        "InsurancePolicyVehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claims",
    )
    loss_date = models.DateField()
    description = models.TextField(blank=True, default="")
    other_party = models.CharField(max_length=200, blank=True, default="")
    police_report = models.CharField(max_length=80, blank=True, default="")
    carrier_claim_number = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REPORTED)
    opened_by_client = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-loss_date", "-id"]

    def __str__(self):
        return f"Claim {self.carrier_claim_number or self.pk} · {self.policy_id}"


def _claim_photo_upload(instance, filename):
    return f"insurance_claims/{instance.claim_id}/{filename}"


class InsuranceClaimPhoto(models.Model):
    claim = models.ForeignKey(InsuranceClaim, on_delete=models.CASCADE, related_name="photos")
    file = models.FileField(upload_to=_claim_photo_upload)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class InsuranceIssuedForm(models.Model):
    """A certificate, application, or loss notice filled from the policy."""

    policy = models.ForeignKey("InsurancePolicy", on_delete=models.CASCADE, related_name="issued_forms")
    form_key = models.CharField(max_length=40)
    title = models.CharField(max_length=160)
    holder_name = models.CharField(max_length=200, blank=True, default="")
    file = models.FileField(upload_to="insurance_forms/%Y/%m/")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class InsuranceDriverIncident(models.Model):
    class Kind(models.TextChoices):
        ACCIDENT = "accident", "Accident"
        VIOLATION = "violation", "Violation"

    driver = models.ForeignKey("InsurancePolicyDriver", on_delete=models.CASCADE, related_name="incidents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    occurred_on = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["-occurred_on", "-id"]
