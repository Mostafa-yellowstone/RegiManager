"""Secret references — never store or return plaintext through APIs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid

from django.conf import settings

from .exceptions import SecretAccessError
from .models import SecretReference


def _key() -> bytes:
    return hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()


def encrypt_mapping(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(16)
    key = _key()
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    tag = hmac.new(key, nonce + xored, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + tag + xored).decode("ascii")


def decrypt_mapping(blob: str) -> dict:
    try:
        packed = base64.urlsafe_b64decode(blob.encode("ascii"))
        nonce, tag, xored = packed[:16], packed[16:48], packed[48:]
        key = _key()
        expected = hmac.new(key, nonce + xored, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise SecretAccessError("Secret payload failed integrity check.")
        raw = bytes(b ^ key[i % len(key)] for i, b in enumerate(xored))
        return json.loads(raw.decode("utf-8"))
    except SecretAccessError:
        raise
    except Exception as exc:
        raise SecretAccessError("Unable to read secret.") from exc


def store_secret(organization, mapping: dict) -> SecretReference:
    reference = f"rcsec_{uuid.uuid4().hex}"
    return SecretReference.objects.create(
        organization=organization,
        reference=reference,
        backend="local_encrypted",
        payload_encrypted=encrypt_mapping(mapping),
    )


def load_secret(reference: str, organization_id: int) -> dict:
    row = SecretReference.objects.filter(reference=reference, organization_id=organization_id).first()
    if row is None:
        raise SecretAccessError("Unknown credential reference.")
    if not row.payload_encrypted:
        return {}
    return decrypt_mapping(row.payload_encrypted)
