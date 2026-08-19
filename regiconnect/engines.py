"""Submission, quote, and bind engines with audited transitions."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .access import evaluate_market_access
from .appetite import evaluate_appetite
from .exceptions import TerminalConnectorError
from .models import (
    BindTransaction,
    CanonicalQuote,
    Connection,
    Submission,
    SubmissionExtension,
)
from .canonical import build_canonical_payload
from .runtime import audit, dispatch_job, enqueue_job, enqueue_outbox, remember_idempotency


class ValidationError(TerminalConnectorError):
    pass


def canonical_from_client(client, *, state="", line_of_business="", extra=None) -> dict:
    extra = extra or {}
    return build_canonical_payload(
        client=client,
        extra=extra,
        state=state,
        line_of_business=line_of_business,
    )


def create_submission(
    *,
    organization,
    market,
    connection: Connection,
    actor,
    client=None,
    vehicle=None,
    quote_lead=None,
    state="",
    line_of_business="",
    extra=None,
    scenario="",
) -> Submission:
    extra = extra or {}
    canonical = build_canonical_payload(
        client=client,
        vehicle=vehicle,
        quote_lead=quote_lead,
        extra=extra,
        state=state or (quote_lead.state if quote_lead else ""),
        line_of_business=line_of_business or (getattr(quote_lead, "insurance_type", "") if quote_lead else ""),
    )
    if scenario:
        canonical["scenario"] = scenario
    idem = extra.get("idempotency_key") or f"sub-{organization.id}-{uuid.uuid4().hex}"
    existing = Submission.objects.filter(organization=organization, idempotency_key=idem).first()
    if existing:
        return existing
    remember_idempotency(organization, idem, "Submission")

    with transaction.atomic():
        submission = Submission.objects.create(
            organization=organization,
            client=client,
            quote_lead=quote_lead,
            market=market,
            connection=connection,
            status=Submission.Status.DRAFT,
            state=canonical.get("state") or "",
            line_of_business=canonical.get("line_of_business") or "",
            idempotency_key=idem,
            canonical_payload=canonical,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        SubmissionExtension.objects.create(
            submission=submission,
            extra=extra,
            scenario=canonical.get("scenario") or "",
        )
        audit(
            organization=organization,
            action="submission_created",
            actor=actor if getattr(actor, "pk", None) else None,
            resource_type="Submission",
            resource_id=submission.id,
            correlation_id=submission.correlation_id,
        )
        enqueue_outbox(
            organization=organization,
            event_type="SubmissionCreated",
            payload={"submission_id": submission.id},
            aggregate_type="Submission",
            aggregate_id=submission.id,
            correlation_id=submission.correlation_id,
        )
    return submission


def validate_submission(submission: Submission) -> Submission:
    submission.status = Submission.Status.VALIDATING
    submission.save(update_fields=["status", "updated_at"])
    access = evaluate_market_access(
        organization=submission.organization,
        market=submission.market,
        state=submission.state,
        line_of_business=submission.line_of_business,
    )
    appetite = evaluate_appetite(submission.market, submission.canonical_payload)
    reasons = access.reasons + appetite.reasons
    if not access.allowed:
        submission.status = Submission.Status.FAILED
        submission.last_error = "; ".join(access.reasons)
        submission.save(update_fields=["status", "last_error", "updated_at"])
        raise ValidationError(submission.last_error)
    if appetite.result == "ineligible":
        submission.status = Submission.Status.DECLINED
        submission.last_error = "; ".join(reasons)
        submission.save(update_fields=["status", "last_error", "updated_at"])
        raise ValidationError(submission.last_error)
    if appetite.result == "refer":
        submission.status = Submission.Status.REFERRED
        submission.save(update_fields=["status", "updated_at"])
        return submission
    submission.status = Submission.Status.READY
    submission.save(update_fields=["status", "updated_at"])
    audit(
        organization=submission.organization,
        action="submission_validated",
        resource_type="Submission",
        resource_id=submission.id,
        correlation_id=submission.correlation_id,
        after={"appetite": appetite.result, "access": access.reasons},
    )
    return submission


def submit_and_quote(submission: Submission) -> Submission:
    validate_submission(submission)
    if submission.status == Submission.Status.REFERRED:
        return submission
    if submission.connection.environment == Connection.Environment.PRODUCTION:
        if not submission.connection.production_approved_at:
            raise ValidationError("Production is not certified for this connection.")
    submission.status = Submission.Status.SUBMITTING
    submission.save(update_fields=["status", "updated_at"])
    job = enqueue_job(
        organization=submission.organization,
        connection=submission.connection,
        operation="submit",
        payload={"submission_id": submission.id},
        idempotency_key=f"job-submit-{submission.idempotency_key}",
        correlation_id=submission.correlation_id,
    )
    dispatch_job(job)
    quote_job = enqueue_job(
        organization=submission.organization,
        connection=submission.connection,
        operation="quote",
        payload={"submission_id": submission.id},
        idempotency_key=f"job-quote-{submission.idempotency_key}",
        correlation_id=submission.correlation_id,
    )
    dispatch_job(quote_job)
    return submission


def request_bind(quote: CanonicalQuote, actor=None) -> BindTransaction:
    key = f"bind-{quote.id}"
    existing = BindTransaction.objects.filter(organization=quote.organization, idempotency_key=key).first()
    if existing:
        return existing
    bind = BindTransaction.objects.create(
        organization=quote.organization,
        quote=quote,
        submission=quote.submission,
        connection=quote.submission.connection,
        idempotency_key=key,
        correlation_id=quote.submission.correlation_id,
        status=BindTransaction.Status.REQUESTED,
    )
    audit(
        organization=quote.organization,
        action="bind_requested",
        actor=actor,
        resource_type="BindTransaction",
        resource_id=bind.id,
        correlation_id=bind.correlation_id,
    )
    job = enqueue_job(
        organization=quote.organization,
        connection=bind.connection,
        operation="bind",
        payload={"bind_id": bind.id},
        idempotency_key=f"job-{key}",
        correlation_id=bind.correlation_id,
    )
    dispatch_job(job)
    return bind


def apply_connector_result(job, result: dict) -> None:
    from .integrations import ingest_bind, ingest_quote, store_documents

    op = job.operation
    payload = job.payload or {}
    if op == "submit":
        submission = Submission.objects.get(pk=payload["submission_id"])
        submission.status = Submission.Status.SUBMITTED
        submission.external_reference = str(result.get("external_reference") or submission.external_reference)
        submission.save(update_fields=["status", "external_reference", "updated_at"])
        enqueue_outbox(
            organization=submission.organization,
            event_type="SubmissionSubmitted",
            payload={"submission_id": submission.id},
            aggregate_type="Submission",
            aggregate_id=submission.id,
            correlation_id=submission.correlation_id,
        )
        return
    if op == "quote":
        submission = Submission.objects.select_related("market", "connection").get(pk=payload["submission_id"])
        status = (result.get("status") or "quoted").lower()
        if status == "declined":
            submission.status = Submission.Status.DECLINED
            submission.last_error = str(result.get("reason") or "Declined")
            submission.save(update_fields=["status", "last_error", "updated_at"])
            return
        if status == "referred":
            submission.status = Submission.Status.REFERRED
            submission.save(update_fields=["status", "updated_at"])
            return
        version = (submission.quotes.count() or 0) + 1
        premium = Decimal(str(result.get("premium") or "0"))
        taxes = Decimal(str(result.get("taxes") or "0"))
        fees = Decimal(str(result.get("fees") or "0"))
        total = Decimal(str(result.get("total") or (premium + taxes + fees)))
        quote = CanonicalQuote.objects.create(
            organization=submission.organization,
            submission=submission,
            market=submission.market,
            version=version,
            premium=premium,
            taxes=taxes,
            fees=fees,
            total=total,
            coverage=result.get("coverage") or {},
            effective_date=result.get("effective_date") or None,
            expiration_date=result.get("expiration_date") or None,
            external_reference=str(result.get("external_reference") or ""),
        )
        submission.status = Submission.Status.QUOTED
        submission.external_reference = quote.external_reference or submission.external_reference
        submission.save(update_fields=["status", "external_reference", "updated_at"])
        ingest_quote(quote)
        enqueue_outbox(
            organization=submission.organization,
            event_type="QuoteReceived",
            payload={"quote_id": quote.id, "submission_id": submission.id},
            aggregate_type="CanonicalQuote",
            aggregate_id=quote.id,
            correlation_id=submission.correlation_id,
        )
        return
    if op == "bind":
        from .models import BindTransaction

        bind = BindTransaction.objects.select_related("quote", "submission", "connection").get(pk=payload["bind_id"])
        status = (result.get("status") or "bound").lower()
        bind.external_reference = str(result.get("external_reference") or "")
        if status != "bound":
            bind.status = BindTransaction.Status.DECLINED
            bind.last_error = str(result.get("reason") or "Not bound")
            bind.save(update_fields=["status", "last_error", "external_reference", "updated_at"])
            return
        bind.status = BindTransaction.Status.BOUND
        bind.save(update_fields=["status", "external_reference", "updated_at"])
        ingest_bind(bind, policy_number=str(result.get("policy_number") or bind.external_reference))
        enqueue_outbox(
            organization=bind.organization,
            event_type="PolicyBound",
            payload={"bind_id": bind.id},
            aggregate_type="BindTransaction",
            aggregate_id=bind.id,
            correlation_id=bind.correlation_id,
        )
        return
    if op == "documents":
        submission = Submission.objects.get(pk=payload["submission_id"])
        store_documents(submission, result.get("documents") or [])
        return
    if op == "health_check":
        job.connection.last_health_check = timezone.now()
        job.connection.save(update_fields=["last_health_check"])
