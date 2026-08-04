"""Agent portal: attendance, tasks, activity timeline, and related helpers."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class AgentAttendanceSession(models.Model):
    """
    One attendance shift per agent membership per America/New_York work-date.

    A shift for work_date D opens when the agent logs into the system
    (website or companion app) and auto-closes at 18:00 America/New_York on D.
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
        help_text="America/New_York calendar date this shift belongs to.",
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
    """Staged work item assigned to an insurance agent until completed."""

    class Status(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        WAITING = "waiting", "Waiting"
        DONE = "done", "Done"

    STATUS_PIPELINE = (
        Status.TODO,
        Status.IN_PROGRESS,
        Status.WAITING,
        Status.DONE,
    )

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
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
        db_index=True,
    )
    is_done = models.BooleanField(default=False, db_index=True)
    completion_note = models.TextField(blank=True, default="")
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

    @property
    def status_label(self) -> str:
        return self.get_status_display()

    def set_status(self, status: str, *, note: str | None = None, save: bool = True):
        """
        Move the task through the stage pipeline and keep is_done/completed_at in sync.
        Passing note=None leaves completion_note unchanged; note="" clears it.
        """
        status = (status or "").strip().lower()
        valid = {choice.value for choice in self.Status}
        if status not in valid:
            raise ValueError(f"Invalid task status: {status}")

        self.status = status
        if status == self.Status.DONE:
            self.is_done = True
            if self.completed_at is None:
                self.completed_at = timezone.now()
            if note is not None:
                self.completion_note = (note or "").strip()
        else:
            self.is_done = False
            self.completed_at = None
            if note is not None and note.strip():
                self.completion_note = note.strip()

        if save:
            self.save(
                update_fields=[
                    "status",
                    "is_done",
                    "completed_at",
                    "completion_note",
                    "updated_at",
                ]
            )
        return self

    def mark_done(self, *, done: bool = True, note: str | None = None):
        """Backward-compatible open/done toggle."""
        if done:
            return self.set_status(self.Status.DONE, note=note)
        return self.set_status(self.Status.TODO, note=None)


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
