"""Renewal autopilot: one card per expiring policy term, its activity log, and office settings."""

from __future__ import annotations

from django.conf import settings
from django.db import models

DEFAULT_EMAIL_SUBJECT = "Your {company} policy renews on {expiration_date}"
DEFAULT_EMAIL_BODY = (
    "Hi {first_name},\n\n"
    "Your {company} policy {policy_number} expires on {expiration_date}. "
    "We'd like to review your renewal with you and make sure you still have the best price "
    "and coverage.\n\n"
    "Reply to this email or call us at {agency_phone} and we'll take care of it.\n\n"
    "Thank you,\n{agent_name}\n{agency_name}"
)
DEFAULT_TEXT_BODY = (
    "Hi {first_name}, this is {agent_name} from {agency_name}. Your {company} policy "
    "{policy_number} expires on {expiration_date}. Call or text us at {agency_phone} to renew."
)


class InsuranceRenewalSettings(models.Model):
    organization = models.OneToOneField(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_renewal_settings",
    )
    window_days = models.PositiveSmallIntegerField(
        default=60,
        help_text="A renewal card appears this many days before a policy expires.",
    )
    reminder_days = models.CharField(
        max_length=80,
        default="45,30,15,7",
        help_text="Comma-separated days before expiration when a client reminder is due.",
    )
    daily_collection_target = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Goal for payments collected per day (0 = compare with the last 7 days).",
    )
    email_subject = models.CharField(max_length=180, default=DEFAULT_EMAIL_SUBJECT)
    email_body = models.TextField(default=DEFAULT_EMAIL_BODY)
    text_body = models.TextField(default=DEFAULT_TEXT_BODY)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Insurance renewal settings"
        verbose_name_plural = "Insurance renewal settings"

    def __str__(self):
        return f"Renewal settings · {self.organization}"

    def reminder_offsets(self) -> list[int]:
        offsets = set()
        for part in (self.reminder_days or "").split(","):
            part = part.strip()
            if part.isdigit() and 0 < int(part) <= 365:
                offsets.add(int(part))
        return sorted(offsets, reverse=True)


class InsuranceRenewal(models.Model):
    class Stage(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        CONTACTED = "contacted", "Contacted"
        REQUOTING = "requoting", "Re-quoting"
        RENEWED = "renewed", "Renewed"
        REWRITTEN = "rewritten", "Rewritten"
        LOST = "lost", "Lost"

    OPEN_STAGES = (Stage.UPCOMING, Stage.CONTACTED, Stage.REQUOTING)
    WON_STAGES = (Stage.RENEWED, Stage.REWRITTEN)

    class LostReason(models.TextChoices):
        PRICE = "price", "Price too high"
        OTHER_AGENCY = "other_agency", "Went to another agency"
        SOLD_VEHICLE = "sold_vehicle", "Sold the vehicle"
        MOVED = "moved", "Moved away"
        NO_RESPONSE = "no_response", "No response"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_renewals",
    )
    policy = models.OneToOneField(
        "InsurancePolicy",
        on_delete=models.CASCADE,
        related_name="renewal",
    )
    expiration_date = models.DateField(db_index=True)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.UPCOMING)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_renewals",
    )
    new_policy = models.ForeignKey(
        "InsurancePolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="renewed_from",
    )
    lost_reason = models.CharField(max_length=20, choices=LostReason.choices, blank=True, default="")
    lost_note = models.CharField(max_length=500, blank=True, default="")
    snoozed_until = models.DateField(null=True, blank=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    contact_count = models.PositiveIntegerField(default=0)
    reminders_sent = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Reminder offsets (days before expiration) already emailed, comma-separated.",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["expiration_date", "id"]
        indexes = [
            models.Index(fields=["organization", "stage", "expiration_date"], name="core_renew_org_stage_exp_idx"),
        ]

    def __str__(self):
        return f"Renewal · {self.policy}"

    @property
    def is_open(self) -> bool:
        return self.stage in self.OPEN_STAGES

    def sent_offsets(self) -> set[int]:
        return {int(p) for p in (self.reminders_sent or "").split(",") if p.strip().isdigit()}


class InsuranceRenewalEvent(models.Model):
    class Kind(models.TextChoices):
        CREATED = "created", "Card created"
        CALL = "call", "Call"
        TEXT = "text", "Text message"
        EMAIL = "email", "Email"
        NOTE = "note", "Note"
        STAGE = "stage", "Stage change"
        ASSIGN = "assign", "Reassigned"
        SNOOZE = "snooze", "Snoozed"

    renewal = models.ForeignKey(InsuranceRenewal, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    note = models.TextField(blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_renewal_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.renewal_id}"
