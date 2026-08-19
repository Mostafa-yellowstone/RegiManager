"""Inbound webhooks: HMAC, timestamp window, persist-then-process."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from django.db import IntegrityError, transaction

from .exceptions import TerminalConnectorError
from .models import WebhookEvent
from .runtime import dispatch_job, enqueue_job
from .secrets import SecretAccessError, load_secret

MAX_SKEW_SECONDS = 300


def verify_and_store(*, connection, body: bytes, headers: dict) -> WebhookEvent:
    secret = _webhook_secret(connection)
    signature = (
        headers.get("X-RegiConnect-Signature")
        or headers.get("HTTP_X_REGICONNECT_SIGNATURE")
        or ""
    )
    timestamp = headers.get("X-RegiConnect-Timestamp") or headers.get("HTTP_X_REGICONNECT_TIMESTAMP") or ""
    event_id = headers.get("X-RegiConnect-Event-Id") or headers.get("HTTP_X_REGICONNECT_EVENT_ID") or ""
    if secret:
        if not signature or not timestamp or not event_id:
            raise TerminalConnectorError("Missing webhook authentication headers.")
        try:
            ts = int(timestamp)
        except ValueError as exc:
            raise TerminalConnectorError("Invalid webhook timestamp.") from exc
        if abs(time.time() - ts) > MAX_SKEW_SECONDS:
            raise TerminalConnectorError("Webhook timestamp outside replay window.")
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise TerminalConnectorError("Webhook signature mismatch.")
    if not event_id:
        event_id = hashlib.sha256(body).hexdigest()
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise TerminalConnectorError("Webhook body is not JSON.") from exc
    try:
        with transaction.atomic():
            event = WebhookEvent.objects.create(
                organization=connection.organization,
                connection=connection,
                event_id=event_id,
                payload=payload if isinstance(payload, dict) else {"value": payload},
                headers_digest=hashlib.sha256(signature.encode()).hexdigest()[:64],
                status=WebhookEvent.Status.RECEIVED,
            )
    except IntegrityError:
        event = WebhookEvent.objects.get(connection=connection, event_id=event_id)
        event.status = WebhookEvent.Status.DUPLICATE
        event.save(update_fields=["status"])
        return event
    job = enqueue_job(
        organization=connection.organization,
        connection=connection,
        operation="webhook",
        payload={"event": event.payload, "webhook_event_id": event.id},
        idempotency_key=f"wh-{connection.id}-{event_id}",
        correlation_id=str(payload.get("correlation_id") or "") if isinstance(payload, dict) else "",
    )
    dispatch_job(job)
    event.status = WebhookEvent.Status.PROCESSED
    event.save(update_fields=["status"])
    return event


def _webhook_secret(connection) -> str:
    ref = connection.credential_reference
    if not ref:
        return ""
    try:
        mapping = load_secret(ref, connection.organization_id)
    except SecretAccessError:
        return ""
    return str(mapping.get("webhook_secret") or "")
