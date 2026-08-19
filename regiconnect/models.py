"""RegiConnect persistence. Existing CRM/policy/company/pipeline rows are referenced, not cloned."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


def _uuid():
    return str(uuid.uuid4())


def _check_constraint(*, name: str, q):
    """Django 5.0 uses check=; Django 5.1+ (including 6.0) uses condition=."""
    try:
        return models.CheckConstraint(condition=q, name=name)
    except TypeError:
        return models.CheckConstraint(check=q, name=name)


class MarketProfile(models.Model):
    class MarketType(models.TextChoices):
        CARRIER = "carrier", "Carrier"
        MGA = "mga", "MGA"
        WHOLESALER = "wholesaler", "Wholesaler"
        AGGREGATOR = "aggregator", "Aggregator"
        DISTRIBUTION_PARTNER = "distribution_partner", "Distribution Partner"
        OTHER = "other", "Other"

    class MarketChannel(models.TextChoices):
        VOLUNTARY = "voluntary", "Voluntary"
        ASSIGNED_RISK = "assigned_risk", "Assigned Risk"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        EXPIRED = "expired", "Expired"
        TERMINATED = "terminated", "Terminated"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_market_profiles",
    )
    company = models.OneToOneField(
        "core.InsuranceCompany",
        on_delete=models.CASCADE,
        related_name="market_profile",
    )
    market_type = models.CharField(max_length=32, choices=MarketType.choices, default=MarketType.CARRIER)
    market_channel = models.CharField(
        max_length=20,
        choices=MarketChannel.choices,
        default=MarketChannel.VOLUNTARY,
        help_text="Assigned Risk (e.g. NYAIP) is not a voluntary carrier the agent can shop like Progressive.",
    )
    naic = models.CharField(max_length=20, blank=True, default="")
    states = models.JSONField(default=list, blank=True)
    lines_of_business = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requires_appointment = models.BooleanField(default=True)
    requires_producer_code = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self):
        return f"{self.company_id} {self.market_type}"


class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_appointments",
    )
    market = models.ForeignKey(MarketProfile, on_delete=models.CASCADE, related_name="appointments")
    producer_code = models.CharField(max_length=80, blank=True, default="")
    state = models.CharField(max_length=2, blank=True, default="")
    line_of_business = models.CharField(max_length=40, blank=True, default="")
    effective_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    external_reference = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "market", "status"])]


class ProducerCode(models.Model):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_producer_codes",
    )
    market = models.ForeignKey(MarketProfile, on_delete=models.CASCADE, related_name="producer_codes")
    code = models.CharField(max_length=80)
    state = models.CharField(max_length=2, blank=True, default="")
    line_of_business = models.CharField(max_length=40, blank=True, default="")
    effective_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "market", "code", "state", "line_of_business"],
                name="regiconnect_producer_unique",
            )
        ]


class AppetiteRule(models.Model):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_appetite_rules",
    )
    market = models.ForeignKey(MarketProfile, on_delete=models.CASCADE, related_name="appetite_rules")
    name = models.CharField(max_length=120)
    criteria = models.JSONField(default=list, blank=True)
    result_on_match = models.CharField(max_length=20, default="eligible")
    priority = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "id"]


class Connector(models.Model):
    """Code-registered connector. Slug maps to Python implementation."""

    slug = models.SlugField(unique=True)
    display_name = models.CharField(max_length=120)
    version = models.CharField(max_length=20, default="1.0")
    mapping_version = models.CharField(max_length=20, default="1.0")
    connector_type = models.CharField(max_length=40, default="rest")
    missing_carrier_spec = models.BooleanField(default=False)
    capabilities = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.slug} v{self.version}"


class Connection(models.Model):
    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox"
        CERTIFICATION = "certification", "Certification"
        PRODUCTION = "production", "Production"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        TESTING = "testing", "Testing"
        CERTIFICATION = "certification", "Certification"
        APPROVED = "approved", "Approved"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        FAILED = "failed", "Failed"
        DISABLED = "disabled", "Disabled"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_connections",
    )
    market = models.ForeignKey(MarketProfile, on_delete=models.CASCADE, related_name="connections")
    connector = models.ForeignKey(Connector, on_delete=models.PROTECT, related_name="connections")
    environment = models.CharField(max_length=20, choices=Environment.choices, default=Environment.SANDBOX)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    credential_reference = models.CharField(max_length=120, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    capabilities = models.JSONField(default=dict, blank=True)
    last_health_check = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_failure_message = models.CharField(max_length=255, blank=True, default="")
    production_approved_at = models.DateTimeField(null=True, blank=True)
    production_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regiconnect_production_approvals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "status"])]


class SecretReference(models.Model):
    """Pointer + encrypted blob. Never expose `payload_encrypted` via APIs."""

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_secrets",
    )
    reference = models.CharField(max_length=120, unique=True)
    backend = models.CharField(max_length=40, default="local_encrypted")
    payload_encrypted = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "reference"])]


class ConnectAuditEvent(models.Model):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_audit",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=80)
    resource_type = models.CharField(max_length=80, blank=True, default="")
    resource_id = models.CharField(max_length=80, blank=True, default="")
    correlation_id = models.CharField(max_length=64, db_index=True, default=_uuid)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"])]


class IdempotencyRecord(models.Model):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_idempotency",
    )
    key = models.CharField(max_length=120)
    resource_type = models.CharField(max_length=80)
    resource_id = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "key"], name="regiconnect_idempotency_org_key")
        ]


class OutboxEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_outbox",
    )
    event_type = models.CharField(max_length=80)
    aggregate_type = models.CharField(max_length=80, blank=True, default="")
    aggregate_id = models.CharField(max_length=80, blank=True, default="")
    correlation_id = models.CharField(max_length=64, default=_uuid)
    causation_id = models.CharField(max_length=64, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]


class ConnectorJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        RETRYING = "retrying", "Retrying"
        FAILED = "failed", "Failed"
        DEAD = "dead", "Dead letter"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_jobs",
    )
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="jobs")
    operation = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    attempt = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    correlation_id = models.CharField(max_length=64, default=_uuid, db_index=True)
    idempotency_key = models.CharField(max_length=120, blank=True, default="")
    payload = models.JSONField(default=dict)
    last_error = models.TextField(blank=True, default="")
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "status"])]


class DeadLetterItem(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RETRIED = "retried", "Retried"
        RESOLVED = "resolved", "Resolved"
        DISCARDED = "discarded", "Discarded"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_dlq",
    )
    job = models.ForeignKey(ConnectorJob, on_delete=models.CASCADE, related_name="dlq_items")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    error = models.TextField(blank=True, default="")
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Submission(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        VALIDATING = "validating", "Validating"
        READY = "ready", "Ready"
        SUBMITTING = "submitting", "Submitting"
        SUBMITTED = "submitted", "Submitted"
        RECEIVED = "received", "Received"
        UNDER_REVIEW = "under_review", "Under review"
        QUOTED = "quoted", "Quoted"
        REFERRED = "referred", "Referred"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_submissions",
    )
    client = models.ForeignKey(
        "core.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regiconnect_submissions",
    )
    quote_lead = models.ForeignKey(
        "core.InsuranceQuoteLead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regiconnect_submissions",
    )
    market = models.ForeignKey(MarketProfile, on_delete=models.CASCADE, related_name="submissions")
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="submissions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    state = models.CharField(max_length=2, blank=True, default="")
    line_of_business = models.CharField(max_length=40, blank=True, default="")
    external_reference = models.CharField(max_length=120, blank=True, default="")
    correlation_id = models.CharField(max_length=64, default=_uuid, db_index=True)
    idempotency_key = models.CharField(max_length=120, db_index=True)
    canonical_payload = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                name="regiconnect_submission_idempotent",
            )
        ]
        indexes = [models.Index(fields=["organization", "status", "-created_at"])]


class SubmissionExtension(models.Model):
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name="extension")
    extra = models.JSONField(default=dict, blank=True)
    scenario = models.CharField(max_length=40, blank=True, default="")


class CanonicalQuote(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        QUOTED = "quoted", "Quoted"
        UPDATED = "updated", "Updated"
        REFERRED = "referred", "Referred"
        DECLINED = "declined", "Declined"
        ERROR = "error", "Error"
        EXPIRED = "expired", "Expired"
        SELECTED = "selected", "Selected"
        BOUND = "bound", "Bound"
        CANCELLED = "cancelled", "Cancelled"

    class QuoteSource(models.TextChoices):
        MOCK = "mock", "Mock / Test"
        DIRECT_CARRIER = "direct_carrier", "Direct carrier"
        MGA = "mga", "MGA"
        AUTHORIZED_PROVIDER = "authorized_provider", "Authorized provider"
        EZLYNX = "ezlynx", "EZLynx (optional)"
        MANUAL = "manual", "Manual"
        OTHER = "other", "Other"

    class PremiumClass(models.TextChoices):
        ESTIMATED = "estimated", "Estimated"
        INDICATIVE = "indicative", "Indicative"
        FINAL = "final", "Final"
        BOUND = "bound", "Bound"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_quotes",
    )
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="quotes",
        null=True,
        blank=True,
    )
    rating_request = models.ForeignKey(
        "RatingRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
    )
    rating_job = models.ForeignKey(
        "RatingJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
    )
    connection = models.ForeignKey(
        "Connection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
    )
    market = models.ForeignKey(MarketProfile, on_delete=models.CASCADE, related_name="quotes")
    version = models.PositiveIntegerField(default=1)
    premium = models.DecimalField(max_digits=12, decimal_places=2)
    taxes = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    coverage = models.JSONField(default=dict, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    quoted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    quote_source = models.CharField(
        max_length=32,
        choices=QuoteSource.choices,
        default=QuoteSource.OTHER,
        help_text="Mock quotes must use MOCK and must never be shown as a carrier rate.",
    )
    premium_class = models.CharField(
        max_length=20,
        choices=PremiumClass.choices,
        default=PremiumClass.ESTIMATED,
    )
    environment = models.CharField(max_length=20, blank=True, default="")
    mapping_version = models.CharField(max_length=40, blank=True, default="")
    provider_slug = models.CharField(max_length=80, blank=True, default="")
    external_reference = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            _check_constraint(
                name="regiconnect_quote_has_parent",
                q=models.Q(submission__isnull=False) | models.Q(rating_job__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["submission", "version"],
                condition=models.Q(submission__isnull=False),
                name="regiconnect_quote_submission_version",
            ),
            models.UniqueConstraint(
                fields=["rating_job", "version"],
                condition=models.Q(rating_job__isnull=False),
                name="regiconnect_quote_rating_job_version",
            ),
        ]


class RatingRequest(models.Model):
    """Comparative rating session. Does not replace InsuranceQuoteLead or Client."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        VALIDATING = "validating", "Validating"
        ELIGIBILITY_CHECK = "eligibility_check", "Eligibility check"
        READY = "ready", "Ready"
        RATING = "rating", "Rating"
        PARTIAL_RESULTS = "partial_results", "Partial results"
        COMPLETED = "completed", "Completed"
        REFERRED = "referred", "Referred"
        NO_MARKET = "no_market", "No market"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    class RatingMode(models.TextChoices):
        REAL_TIME = "real_time", "Real time"
        ASYNC = "async", "Asynchronous"
        MIXED = "mixed", "Mixed"

    class TransactionType(models.TextChoices):
        NEW_BUSINESS = "new_business", "New business"
        ENDORSEMENT = "endorsement", "Endorsement"
        RENEWAL = "renewal", "Renewal"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regi_rater_requests",
    )
    client = models.ForeignKey(
        "core.Client",
        on_delete=models.PROTECT,
        related_name="regi_rater_requests",
    )
    quote_lead = models.ForeignKey(
        "core.InsuranceQuoteLead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regi_rater_requests",
        help_text="Optional link to the existing Quote Pipeline lead after select, or a seed lead.",
    )
    state = models.CharField(max_length=2, blank=True, default="")
    line_of_business = models.CharField(max_length=40, blank=True, default="auto_personal")
    effective_date = models.DateField(null=True, blank=True)
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        default=TransactionType.NEW_BUSINESS,
    )
    rating_mode = models.CharField(
        max_length=20,
        choices=RatingMode.choices,
        default=RatingMode.MIXED,
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    canonical_snapshot = models.JSONField(default=dict, blank=True)
    coverage = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=64, default=_uuid, db_index=True)
    idempotency_key = models.CharField(max_length=120, db_index=True)
    last_error = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regi_rater_requests_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                name="regiconnect_rating_request_idempotent",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status", "-created_at"]),
            models.Index(fields=["organization", "client"]),
        ]


class RatingJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        EXCLUDED = "excluded", "Excluded"
        QUEUED = "queued", "Queued"
        RATING = "rating", "Rating"
        QUOTED = "quoted", "Quoted"
        REFERRED = "referred", "Referred"
        DECLINED = "declined", "Declined"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    class Eligibility(models.TextChoices):
        ELIGIBLE = "eligible", "Eligible"
        INELIGIBLE = "ineligible", "Ineligible"
        REFER = "refer", "Refer"
        UNKNOWN = "unknown", "Unknown"
        UNAVAILABLE = "unavailable", "Unavailable"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regi_rater_jobs",
    )
    rating_request = models.ForeignKey(RatingRequest, on_delete=models.CASCADE, related_name="jobs")
    market = models.ForeignKey(MarketProfile, on_delete=models.CASCADE, related_name="rating_jobs")
    connection = models.ForeignKey(
        Connection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rating_jobs",
    )
    submission = models.ForeignKey(
        Submission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rating_jobs",
    )
    connector_job = models.ForeignKey(
        ConnectorJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rating_jobs",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    eligibility = models.CharField(
        max_length=20,
        choices=Eligibility.choices,
        default=Eligibility.UNKNOWN,
    )
    eligibility_reason = models.TextField(blank=True, default="")
    error_category = models.CharField(max_length=40, blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    correlation_id = models.CharField(max_length=64, default=_uuid, db_index=True)
    idempotency_key = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rating_request", "market"],
                name="regiconnect_rating_job_request_market",
            )
        ]
        indexes = [models.Index(fields=["organization", "status"])]


class RatingExtension(models.Model):
    """Carrier-specific answers. Do not add these fields to Client."""

    rating_request = models.ForeignKey(RatingRequest, on_delete=models.CASCADE, related_name="extensions")
    market = models.ForeignKey(MarketProfile, on_delete=models.CASCADE, related_name="rating_extensions")
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rating_request", "market"],
                name="regiconnect_rating_extension_unique",
            )
        ]


class RatingError(models.Model):
    class Category(models.TextChoices):
        VALIDATION_ERROR = "validation_error", "Validation"
        AUTHENTICATION_ERROR = "authentication_error", "Authentication"
        AUTHORIZATION_ERROR = "authorization_error", "Authorization"
        RATE_LIMIT = "rate_limit", "Rate limit"
        TIMEOUT = "timeout", "Timeout"
        CARRIER_ERROR = "carrier_error", "Carrier"
        UNSUPPORTED = "unsupported", "Unsupported"
        DECLINE = "decline", "Decline"
        REFERRAL = "referral", "Referral"
        SYSTEM_ERROR = "system_error", "System"
        NETWORK_ERROR = "network_error", "Network"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regi_rater_errors",
    )
    rating_request = models.ForeignKey(RatingRequest, on_delete=models.CASCADE, related_name="errors")
    rating_job = models.ForeignKey(
        RatingJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="errors",
    )
    category = models.CharField(max_length=40, choices=Category.choices, default=Category.SYSTEM_ERROR)
    message = models.TextField()
    agent_message = models.TextField(blank=True, default="")
    retryable = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "rating_request"])]


class BindTransaction(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        SUBMITTED = "submitted", "Submitted"
        PENDING = "pending", "Pending"
        BOUND = "bound", "Bound"
        DECLINED = "declined", "Declined"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_binds",
    )
    quote = models.ForeignKey(CanonicalQuote, on_delete=models.CASCADE, related_name="binds")
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="binds")
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="binds")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    correlation_id = models.CharField(max_length=64, default=_uuid)
    idempotency_key = models.CharField(max_length=120)
    external_reference = models.CharField(max_length=120, blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                name="regiconnect_bind_idempotent",
            )
        ]


class QuoteLeadConnectivity(models.Model):
    class QuoteSource(models.TextChoices):
        MANUAL = "manual", "Manual"
        REGI_CONNECT = "regi_connect", "RegiConnect"
        REGI_RATER = "regi_rater", "Regi Rater"
        CARRIER_API = "carrier_api", "Carrier API"
        MGA = "mga", "MGA"
        SFTP = "sftp", "SFTP"
        ACORD = "acord", "ACORD"
        OTHER = "other", "Other"

    lead = models.OneToOneField(
        "core.InsuranceQuoteLead",
        on_delete=models.CASCADE,
        related_name="regi_connectivity",
    )
    submission = models.ForeignKey(
        Submission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pipeline_links",
    )
    market = models.ForeignKey(
        MarketProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    quote = models.ForeignKey(
        CanonicalQuote,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    quote_source = models.CharField(max_length=20, choices=QuoteSource.choices, default=QuoteSource.REGI_CONNECT)
    premium = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    external_reference = models.CharField(max_length=120, blank=True, default="")
    connectivity_status = models.CharField(max_length=40, blank=True, default="")


class PolicyConnectivity(models.Model):
    policy = models.OneToOneField(
        "core.InsurancePolicy",
        on_delete=models.CASCADE,
        related_name="regi_connectivity",
    )
    submission = models.ForeignKey(
        Submission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    bind = models.ForeignKey(
        BindTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    external_policy_number = models.CharField(max_length=120, blank=True, default="")
    carrier_reference = models.CharField(max_length=120, blank=True, default="")
    last_sync_at = models.DateTimeField(null=True, blank=True)
    connectivity_status = models.CharField(max_length=40, blank=True, default="")


class WebhookEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        DUPLICATE = "duplicate", "Duplicate"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_webhooks",
    )
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="webhook_events")
    event_id = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    headers_digest = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "event_id"],
                name="regiconnect_webhook_idempotent",
            )
        ]


class InboundTransaction(models.Model):
    class TxnType(models.TextChoices):
        NEW_BUSINESS = "new_business", "New Business"
        RENEWAL = "renewal", "Renewal"
        ENDORSEMENT = "endorsement", "Endorsement"
        CANCELLATION = "cancellation", "Cancellation"
        REINSTATEMENT = "reinstatement", "Reinstatement"
        NON_RENEWAL = "non_renewal", "Non-renewal"
        COMMISSION = "commission", "Commission"
        BILLING = "billing", "Billing"
        DOCUMENT = "document", "Document"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_inbound",
    )
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="inbound_transactions")
    txn_type = models.CharField(max_length=30, choices=TxnType.choices)
    external_reference = models.CharField(max_length=120, blank=True, default="")
    checksum = models.CharField(max_length=64, blank=True, default="")
    raw_payload = models.JSONField(default=dict, blank=True)
    parsed = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "external_reference", "checksum"],
                name="regiconnect_inbound_dedupe",
            )
        ]


class DocumentExchange(models.Model):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_documents",
    )
    submission = models.ForeignKey(
        Submission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    policy = models.ForeignKey(
        "core.InsurancePolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regiconnect_documents",
    )
    doc_type = models.CharField(max_length=40, default="other")
    file = models.FileField(upload_to="regiconnect/docs/%Y/%m/", blank=True)
    external_reference = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class SftpEndpoint(models.Model):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_sftp",
    )
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="sftp_endpoints")
    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=22)
    username = models.CharField(max_length=120, blank=True, default="")
    credential_reference = models.CharField(max_length=120, blank=True, default="")
    host_key_fingerprint = models.CharField(max_length=128, blank=True, default="")
    inbound_path = models.CharField(max_length=255, blank=True, default="")
    outbound_path = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class SftpFileJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DOWNLOADED = "downloaded", "Downloaded"
        UPLOADED = "uploaded", "Uploaded"
        QUARANTINED = "quarantined", "Quarantined"
        DUPLICATE = "duplicate", "Duplicate"
        FAILED = "failed", "Failed"

    endpoint = models.ForeignKey(SftpEndpoint, on_delete=models.CASCADE, related_name="files")
    filename = models.CharField(max_length=255)
    checksum = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)


class AcordMapping(models.Model):
    connector = models.ForeignKey(Connector, on_delete=models.CASCADE, related_name="acord_mappings")
    transaction_type = models.CharField(max_length=40)
    acord_version = models.CharField(max_length=20)
    mapping = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ReconciliationException(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_reconciliation",
    )
    kind = models.CharField(max_length=40)
    detail = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)


class CertificationRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="regiconnect_cert_runs",
    )
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="certification_runs")
    environment = models.CharField(max_length=20, default=Connection.Environment.CERTIFICATION)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class CertificationTestResult(models.Model):
    run = models.ForeignKey(CertificationRun, on_delete=models.CASCADE, related_name="results")
    test_key = models.CharField(max_length=40)
    status = models.CharField(max_length=20)
    duration_ms = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    request_reference = models.CharField(max_length=80, blank=True, default="")
    response_reference = models.CharField(max_length=80, blank=True, default="")
