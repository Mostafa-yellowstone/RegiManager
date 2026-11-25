"""Per-carrier portal logins for the quote engine, encrypted at rest.

Passwords are write-only: stored with Fernet, never shown in admin or logs.
Key comes from CARRIER_CRED_KEY (a Fernet key); until it is set, a key derived from SECRET_KEY is used.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models
from django.utils import timezone


class CredentialKeyError(RuntimeError):
    pass


def _derived_key() -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(("carrier-cred:" + settings.SECRET_KEY).encode()).digest()).decode()


def _fernet(key: str | None = None):
    """MultiFernet: encrypts with CARRIER_CRED_KEY when set, else a key derived from SECRET_KEY.

    Decrypts with either, so logins saved before CARRIER_CRED_KEY was set stay readable after it is set.
    Set CARRIER_CRED_KEY in production: the derived key is only as safe as SECRET_KEY, and changing
    SECRET_KEY would make logins saved with the derived key unreadable.
    """
    from cryptography.fernet import MultiFernet

    keys = []
    env = key or os.getenv("CARRIER_CRED_KEY", "")
    if env:
        keys.append(env)
    keys.append(_derived_key())
    try:
        return MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in keys])
    except Exception as exc:
        raise CredentialKeyError("CARRIER_CRED_KEY is not a valid Fernet key.") from exc


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise CredentialKeyError("Stored credential cannot be decrypted with the current key.") from exc


class CarrierCredential(models.Model):
    class Status(models.TextChoices):
        UNTESTED = "untested", "Untested"
        OK = "ok", "Login OK"
        FAILED = "failed", "Login failed"
        NEEDS_VERIFICATION = "needs_verification", "Needs verification code"
        LOCKED = "locked", "Locked or blocked"

    organization = models.ForeignKey("Organization", on_delete=models.CASCADE, related_name="carrier_credentials")
    carrier_key = models.CharField(max_length=40, db_index=True)
    line = models.CharField(max_length=20, choices=[("auto", "Auto"), ("commercial_auto", "Commercial auto")], default="auto")
    label = models.CharField(max_length=120, blank=True, default="", help_text="Which agency login this is, e.g. 'Brooklyn office'.")
    portal_url = models.URLField(blank=True, default="")
    otp_email = models.EmailField(
        blank=True, default="",
        help_text="Display only. Where the carrier sends the login code. A person types the code on the run page; nothing reads this mailbox.",
    )
    username = models.CharField(max_length=200)
    password_enc = models.TextField(blank=True, default="")
    enabled = models.BooleanField(default=False, help_text="Off by default. Only enabled logins are used by quote runs.")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.UNTESTED)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True, default="")
    consecutive_failures = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    AUTO_DISABLE_AFTER = 3  # stop hammering a portal that keeps rejecting us (account lockout risk)

    class Meta:
        ordering = ["carrier_key", "line", "label"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "carrier_key", "line", "label"], name="uniq_carrier_cred_per_org_line_label"),
        ]

    def __str__(self) -> str:
        return f"{self.carrier_key} ({self.line}) {self.label}".strip()

    def set_password(self, plain: str) -> None:
        self.password_enc = encrypt_secret(plain) if plain else ""

    def has_password(self) -> bool:
        return bool(self.password_enc)

    def get_password(self, actor: str = "", purpose: str = "") -> str:
        """Decrypt for a portal login. Every read is logged. Only adapters should call this."""
        pw = decrypt_secret(self.password_enc) if self.password_enc else ""
        CarrierCredentialLog.objects.create(credential=self, action="used", actor=actor[:100], detail=purpose[:200])
        return pw

    def record_result(self, ok: bool, status: str | None = None, error: str = "") -> None:
        self.last_checked_at = timezone.now()
        if ok:
            self.status = status or self.Status.OK
            self.consecutive_failures = 0
            self.last_error = ""
        else:
            self.status = status or self.Status.FAILED
            self.consecutive_failures += 1
            self.last_error = error[:300]
            if self.status == self.Status.LOCKED or self.consecutive_failures >= self.AUTO_DISABLE_AFTER:
                self.enabled = False
        self.save()
        CarrierCredentialLog.objects.create(credential=self, action="ok" if ok else "failed", detail=error[:200])


class CarrierCredentialLog(models.Model):
    credential = models.ForeignKey(CarrierCredential, on_delete=models.CASCADE, related_name="logs")
    action = models.CharField(max_length=20)  # created, updated, enabled, disabled, used, ok, failed
    actor = models.CharField(max_length=100, blank=True, default="")
    detail = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


def usable_carrier_keys(organization, line: str) -> set[str]:
    """Carrier keys with an enabled login and a stored password for this org and line."""
    qs = CarrierCredential.objects.filter(organization=organization, line=line, enabled=True).exclude(password_enc="")
    return set(qs.values_list("carrier_key", flat=True))


def carrier_otp_emails(organization, line: str) -> dict[str, str]:
    """carrier_key -> inbox where the carrier sends the login OTP (enabled logins with a saved email only)."""
    qs = CarrierCredential.objects.filter(organization=organization, line=line, enabled=True).exclude(otp_email="")
    return {c.carrier_key: c.otp_email for c in qs}
