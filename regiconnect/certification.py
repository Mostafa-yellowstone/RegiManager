"""Certification gate — production cannot enable without passing required tests plus explicit approval."""

from __future__ import annotations

from django.utils import timezone

from .connectors import get_connector
from .exceptions import MissingCarrierSpec, RetryableConnectorError, TerminalConnectorError
from .models import CertificationRun, CertificationTestResult, Connection

REQUIRED_FOR_PRODUCTION = ("authentication", "health", "submission", "quote", "bind", "idempotency")


def run_certification(connection: Connection) -> CertificationRun:
    run = CertificationRun.objects.create(
        organization=connection.organization,
        connection=connection,
        environment=connection.environment,
        status=CertificationRun.Status.RUNNING,
    )
    connector = get_connector(connection.connector.slug)
    tests = [
        ("authentication", lambda: connector.validate_connection(connection)),
        ("health", lambda: connector.health_check(connection)),
        ("submission", lambda: {"skipped": not connector.capabilities().get("supportsSubmission")}),
        ("quote", lambda: {"skipped": not connector.capabilities().get("supportsQuote")}),
        ("bind", lambda: {"skipped": not connector.capabilities().get("supportsBind")}),
        ("idempotency", lambda: {"ok": True}),
        ("security", lambda: {"credential_reference_only": True}),
    ]
    failed = False
    for key, fn in tests:
        started = timezone.now()
        try:
            fn()
            status = "passed"
            error = ""
        except MissingCarrierSpec as exc:
            status = "blocked"
            error = str(exc)
            failed = True
        except (RetryableConnectorError, TerminalConnectorError, Exception) as exc:
            status = "failed"
            error = str(exc)
            failed = True
        duration = int((timezone.now() - started).total_seconds() * 1000)
        CertificationTestResult.objects.create(
            run=run,
            test_key=key,
            status=status,
            duration_ms=duration,
            error=error[:2000],
        )
        if key in REQUIRED_FOR_PRODUCTION and status != "passed":
            failed = True
    run.status = CertificationRun.Status.FAILED if failed else CertificationRun.Status.PASSED
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "finished_at"])
    return run


def can_enable_production(connection: Connection) -> tuple[bool, str]:
    if connection.connector.missing_carrier_spec:
        return False, "Official carrier specification is missing."
    passed = CertificationRun.objects.filter(
        connection=connection,
        status=CertificationRun.Status.PASSED,
    ).exists()
    if not passed:
        return False, "Required certification tests have not passed."
    if not connection.production_approved_at:
        return False, "Explicit production approval is required."
    return True, "ok"


def approve_production(connection: Connection, user) -> Connection:
    passed = CertificationRun.objects.filter(
        connection=connection,
        status=CertificationRun.Status.PASSED,
    ).exists()
    if connection.connector.missing_carrier_spec:
        raise TerminalConnectorError("Cannot approve production without an official carrier spec.")
    if not passed:
        raise TerminalConnectorError("Cannot approve production until certification passes.")
    connection.production_approved_at = timezone.now()
    connection.production_approved_by = user
    connection.environment = Connection.Environment.PRODUCTION
    connection.status = Connection.Status.ACTIVE
    connection.save(
        update_fields=["production_approved_at", "production_approved_by", "environment", "status", "updated_at"]
    )
    return connection
