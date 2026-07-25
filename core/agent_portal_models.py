"""Agent portal: attendance, tasks, activity timeline, and related helpers."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class AgentAttendanceSession(models.Model):
    """
    One attendance shift per agent membership per Cairo work-date.

    A shift for work_date D opens when the agent hits the portal and
    auto-closes at 01:00 Africa/Cairo on D+1.
    """

    membership = models.ForeignKey(
        "OrganizationMembership",
        on_delete=models.CASCADE,
        related_name="attendance_sessions",
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="agent_attendance_sessions",
    )
    work_date = models.DateField(
        db_index=True,
        help_text="Cairo calendar date this shift belongs to.",
    )
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_date", "-opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "work_date"],
                name="uniq_agent_attendance_membership_work_date",
            )
        ]
        verbose_name = "Agent attendance session"
        verbose_name_plural = "Agent attendance sessions"

    def __str__(self):
        status = "open" if self.closed_at is None else "closed"
        return f"{self.membership_id} {self.work_date} ({status})"

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


class AgentTask(models.Model):
    """Persistent checklist item assigned to an agent until marked done."""

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="agent_tasks",
    )
    assigned_to = models.ForeignKey(
        "OrganizationMembership",
        on_delete=models.CASCADE,
        related_name="assigned_tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_tasks_created",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_done = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["is_done", "-created_at"]
        verbose_name = "Agent task"
        verbose_name_plural = "Agent tasks"

    def __str__(self):
        return self.title

    def mark_done(self, *, done: bool = True):
        self.is_done = done
        self.completed_at = timezone.now() if done else None
        self.save(update_fields=["is_done", "completed_at", "updated_at"])


class AgentActivityEvent(models.Model):
    """Timeline entry for insurance / motorclub / TLC actions by an agent."""

    class Domain(models.TextChoices):
        INSURANCE = "insurance", "Insurance"
        MOTORCLUB = "motorclub", "Motor Club"
        TLC = "tlc", "TLC"

    class EventType(models.TextChoices):
        QUOTE_CREATED = "quote_created", "Quote created"
        POLICY_BOUND = "policy_bound", "Policy bound"
        ENDORSEMENT = "endorsement", "Endorsement"
        MEMBERSHIP_CREATED = "membership_created", "Membership created"
        MEMBERSHIP_UPDATED = "membership_updated", "Membership updated"
        TLC_POLICY_CREATED = "tlc_policy_created", "TLC policy created"
        TLC_POLICY_UPDATED = "tlc_policy_updated", "TLC policy updated"
        TLC_ENDORSEMENT = "tlc_endorsement", "TLC endorsement"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="agent_activity_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_activity_events",
    )
    membership = models.ForeignKey(
        "OrganizationMembership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_events",
    )
    domain = models.CharField(max_length=20, choices=Domain.choices, db_index=True)
    event_type = models.CharField(max_length=40, choices=EventType.choices, db_index=True)
    title = models.CharField(max_length=200)
    detail = models.CharField(max_length=400, blank=True, default="")
    object_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Agent activity event"
        verbose_name_plural = "Agent activity events"
        indexes = [
            models.Index(fields=["organization", "actor", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.domain}:{self.event_type} — {self.title}"
