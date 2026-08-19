"""Async connector jobs, retry, DLQ, outbox."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .connectors import get_connector
from .exceptions import RetryableConnectorError, TerminalConnectorError
from .models import (
    ConnectAuditEvent,
    ConnectorJob,
    DeadLetterItem,
    IdempotencyRecord,
    OutboxEvent,
)

logger = logging.getLogger(__name__)

RETRYABLE_HINTS = ("timeout", "429", "500", "502", "503", "504", "temporarily")


def enqueue_outbox(*, organization, event_type, payload, aggregate_type="", aggregate_id="", correlation_id=""):
    return OutboxEvent.objects.create(
        organization=organization,
        event_type=event_type,
        payload=payload,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id or ""),
        correlation_id=correlation_id or payload.get("correlation_id") or "",
    )


def audit(*, organization, action, actor=None, resource_type="", resource_id="", correlation_id="", before=None, after=None):
    return ConnectAuditEvent.objects.create(
        organization=organization,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id or ""),
        correlation_id=correlation_id or "",
        before=before,
        after=after,
    )


def remember_idempotency(organization, key: str, resource_type: str, resource_id="") -> bool:
    """Return True if this key is new; False if duplicate."""
    if not key:
        return True
    _, created = IdempotencyRecord.objects.get_or_create(
        organization=organization,
        key=key,
        defaults={"resource_type": resource_type, "resource_id": str(resource_id or "")},
    )
    return created


def enqueue_job(*, organization, connection, operation, payload, idempotency_key="", correlation_id=""):
    job = ConnectorJob.objects.create(
        organization=organization,
        connection=connection,
        operation=operation,
        payload=payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id or payload.get("correlation_id") or "",
        status=ConnectorJob.Status.QUEUED,
    )
    enqueue_outbox(
        organization=organization,
        event_type="ConnectorJobQueued",
        payload={"job_id": job.id, "operation": operation},
        aggregate_type="ConnectorJob",
        aggregate_id=job.id,
        correlation_id=job.correlation_id,
    )
    return job


def dispatch_job(job: ConnectorJob):
    from .tasks import run_connector_job

    try:
        run_connector_job.delay(job.id)
    except Exception:
        logger.exception("Celery dispatch failed; running job %s inline", job.id)
        run_connector_job(job.id)


def execute_job(job_id: int) -> dict:
    from .engines import apply_connector_result

    job = ConnectorJob.objects.select_related("connection__connector", "organization").get(pk=job_id)
    job.attempt += 1
    job.status = ConnectorJob.Status.RUNNING
    job.save(update_fields=["attempt", "status", "updated_at"])

    connector = get_connector(job.connection.connector.slug)
    try:
        result = _invoke(connector, job)
        apply_connector_result(job, result)
        job.status = ConnectorJob.Status.SUCCEEDED
        job.last_error = ""
        job.save(update_fields=["status", "last_error", "updated_at"])
        job.connection.last_success_at = timezone.now()
        job.connection.save(update_fields=["last_success_at"])
        OutboxEvent.objects.filter(
            aggregate_type="ConnectorJob",
            aggregate_id=str(job.id),
            status=OutboxEvent.Status.PENDING,
        ).update(status=OutboxEvent.Status.PUBLISHED, published_at=timezone.now())
        return {"ok": True, "job_id": job.id}
    except RetryableConnectorError as exc:
        return _retry_or_dead(job, str(exc))
    except TerminalConnectorError as exc:
        return _fail_terminal(job, str(exc))
    except Exception as exc:
        logger.exception("Connector job %s crashed", job.id)
        if any(h in str(exc).lower() for h in RETRYABLE_HINTS):
            return _retry_or_dead(job, str(exc))
        return _fail_terminal(job, str(exc))


def _invoke(connector, job: ConnectorJob):
    from .models import BindTransaction, Submission

    op = job.operation
    connection = job.connection
    payload = job.payload or {}
    if op == "health_check":
        return connector.health_check(connection)
    if op == "submit":
        submission = Submission.objects.get(pk=payload["submission_id"], organization=job.organization)
        return connector.submit_submission(connection, submission)
    if op == "quote":
        submission = Submission.objects.get(pk=payload["submission_id"], organization=job.organization)
        return connector.request_quote(connection, submission)
    if op == "bind":
        bind = BindTransaction.objects.select_related("submission").get(
            pk=payload["bind_id"], organization=job.organization
        )
        return connector.request_bind(connection, bind)
    if op == "documents":
        submission = Submission.objects.get(pk=payload["submission_id"], organization=job.organization)
        return {"documents": connector.download_documents(connection, submission)}
    if op == "webhook":
        return connector.handle_webhook(connection, payload.get("event") or {})
    raise TerminalConnectorError(f"Unknown operation {op}")


def _retry_or_dead(job: ConnectorJob, error: str) -> dict:
    job.last_error = error[:4000]
    if job.attempt >= job.max_attempts:
        job.status = ConnectorJob.Status.DEAD
        job.save(update_fields=["status", "last_error", "updated_at"])
        DeadLetterItem.objects.create(organization=job.organization, job=job, error=error)
        audit(
            organization=job.organization,
            action="job_dead_letter",
            resource_type="ConnectorJob",
            resource_id=job.id,
            correlation_id=job.correlation_id,
            after={"error": error},
        )
        return {"ok": False, "dead": True, "error": error}
    delay = min(60 * (2 ** (job.attempt - 1)), 3600)
    job.status = ConnectorJob.Status.RETRYING
    job.next_run_at = timezone.now() + timedelta(seconds=delay)
    job.save(update_fields=["status", "last_error", "next_run_at", "updated_at"])
    return {"ok": False, "retry": True, "error": error, "delay": delay}


def _fail_terminal(job: ConnectorJob, error: str) -> dict:
    job.status = ConnectorJob.Status.FAILED
    job.last_error = error[:4000]
    job.save(update_fields=["status", "last_error", "updated_at"])
    job.connection.last_failure_at = timezone.now()
    job.connection.last_failure_message = error[:255]
    job.connection.save(update_fields=["last_failure_at", "last_failure_message"])
    return {"ok": False, "terminal": True, "error": error}


def retry_dead_letter(item: DeadLetterItem, actor=None) -> ConnectorJob:
    job = item.job
    job.status = ConnectorJob.Status.QUEUED
    job.attempt = 0
    job.last_error = ""
    job.save(update_fields=["status", "attempt", "last_error", "updated_at"])
    item.status = DeadLetterItem.Status.RETRIED
    item.resolved_by = actor
    item.resolved_at = timezone.now()
    item.save(update_fields=["status", "resolved_by", "resolved_at"])
    audit(
        organization=item.organization,
        action="dlq_retry",
        actor=actor,
        resource_type="DeadLetterItem",
        resource_id=item.id,
    )
    dispatch_job(job)
    return job
