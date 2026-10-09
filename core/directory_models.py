"""Directory hub: companies, shared accounts, phone lines, and logins."""

import re

from django.conf import settings
from django.db import models


def format_us_phone(value):
    """Show a phone as (718) 555-0100. A leading 1 is the country code."""
    raw = (value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    digits = digits[:10]
    if not digits:
        return raw
    if len(digits) < 4:
        return f"({digits}"
    if len(digits) < 7:
        return f"({digits[:3]}) {digits[3:]}"
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


class DirectoryEntry(models.Model):
    class Kind(models.TextChoices):
        COMPANY = "company", "Company"
        LOGIN = "login", "Login credentials"
        SHARED_ACCOUNT = "shared_account", "Shared account"
        PERSON = "person", "Person"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="directory_entries",
    )
    space = models.ForeignKey(
        "Space",
        on_delete=models.CASCADE,
        related_name="directory_entries",
    )
    kind = models.CharField(max_length=30, choices=Kind.choices, default=Kind.COMPANY)
    name = models.CharField(max_length=200)
    category = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Short label such as carrier, Gmail, or vendor.",
    )
    website = models.URLField(blank=True, default="")
    portal_url = models.URLField(blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address = models.CharField(max_length=300, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_directory_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["space", "name"], name="dir_ent_space_name"),
        ]

    def __str__(self):
        return self.name


class DirectoryNote(models.Model):
    entry = models.ForeignKey(DirectoryEntry, on_delete=models.CASCADE, related_name="note_items")
    title = models.CharField(max_length=120)
    body = models.TextField(blank=True, default="")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.title


class DirectoryPhone(models.Model):
    entry = models.ForeignKey(DirectoryEntry, on_delete=models.CASCADE, related_name="phones")
    label = models.CharField(max_length=120, help_text="Who or what this line is, such as Claims or Maria.")
    number = models.CharField(max_length=40)
    extension = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["entry", "number"], name="dir_phone_entry_num"),
        ]

    def formatted_number(self):
        return format_us_phone(self.number)

    def __str__(self):
        return f"{self.label}: {self.number}"


class DirectoryCredential(models.Model):
    entry = models.ForeignKey(DirectoryEntry, on_delete=models.CASCADE, related_name="credentials")
    label = models.CharField(max_length=120, help_text="Gmail, carrier portal, shared inbox, and so on.")
    username = models.CharField(max_length=200, blank=True, default="")
    secret = models.CharField(max_length=400, blank=True, default="")
    login_url = models.URLField(blank=True, default="")
    notes = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.label
