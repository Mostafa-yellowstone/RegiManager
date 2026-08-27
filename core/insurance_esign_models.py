"""Insurance Space Acrobat-style e-signature envelopes."""

from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models


def _original_upload_to(instance, filename):
    return f"insurance_esign/original/{instance.organization_id}/{filename}"


def _signed_upload_to(instance, filename):
    return f"insurance_esign/signed/{instance.organization_id}/{filename}"


def new_signer_token() -> str:
    return secrets.token_urlsafe(32)


class InsuranceESignEnvelope(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        AWAITING = "awaiting", "Awaiting signature"
        SIGNED = "signed", "Completed"
        VOID = "void", "Void"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="insurance_esign_envelopes",
    )
    title = models.CharField(max_length=200)
    original_file = models.FileField(upload_to=_original_upload_to)
    signed_file = models.FileField(upload_to=_signed_upload_to, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    fields_json = models.JSONField(default=list, blank=True)
    audit_json = models.JSONField(default=list, blank=True)
    signer_name = models.CharField(max_length=160, blank=True, default="")
    signer_email = models.EmailField(blank=True, default="")
    signer_token = models.CharField(max_length=64, unique=True, db_index=True)
    signed_ip = models.CharField(max_length=45, blank=True, default="")
    signed_user_agent = models.CharField(max_length=300, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_esign_created",
    )
    signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_esign_signed",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Insurance e-signature envelope"
        verbose_name_plural = "Insurance e-signature envelopes"

    def __str__(self):
        return f"{self.title} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.signer_token:
            self.signer_token = new_signer_token()
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        files = [field for field in (self.original_file, self.signed_file) if field]
        result = super().delete(using=using, keep_parents=keep_parents)
        for stored in files:
            try:
                stored.delete(save=False)
            except Exception:
                pass
        return result
