"""Create and mutate RatingRequest rows using existing CRM entities."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from regiconnect.canonical import build_canonical_payload
from regiconnect.models import RatingJob, RatingRequest
from regiconnect.runtime import audit, enqueue_outbox, remember_idempotency

from .state import assert_transition


def create_rating_request(
    *,
    organization,
    client,
    actor=None,
    vehicles=None,
    extra_drivers=None,
    coverage=None,
    state="",
    line_of_business="auto_personal",
    effective_date=None,
    quote_lead=None,
    idempotency_key="",
    extra=None,
) -> RatingRequest:
    if client.organization_id != organization.id:
        raise ValueError("Client is not in this organization.")
    idem = (idempotency_key or "").strip() or f"rate-{organization.id}-{client.id}-{timezone.now().isoformat()}"
    existing = RatingRequest.objects.filter(organization=organization, idempotency_key=idem).first()
    if existing:
        return existing
    if not remember_idempotency(organization, f"rating-request:{idem}", "RatingRequest"):
        return RatingRequest.objects.get(organization=organization, idempotency_key=idem)

    extra = dict(extra or {})
    if extra_drivers:
        extra["additional_drivers"] = list(extra.get("additional_drivers") or []) + list(extra_drivers)
    if coverage:
        extra["coverage_type"] = coverage.get("type") if isinstance(coverage, dict) else coverage
    vehicle_rows = list(vehicles or [])
    vehicle = vehicle_rows[0] if vehicle_rows else None
    if len(vehicle_rows) > 1:
        from regiconnect.canonical import vehicle_from_row

        extra["additional_vehicles"] = list(extra.get("additional_vehicles") or []) + [
            vehicle_from_row(row) for row in vehicle_rows[1:]
        ]
    snapshot = build_canonical_payload(
        client=client,
        vehicle=vehicle,
        quote_lead=quote_lead,
        extra=extra,
        state=state or getattr(client, "state", "") or "",
        line_of_business=line_of_business,
    )
    with transaction.atomic():
        request = RatingRequest.objects.create(
            organization=organization,
            client=client,
            quote_lead=quote_lead,
            state=snapshot.get("state") or "",
            line_of_business=snapshot.get("line_of_business") or line_of_business,
            effective_date=effective_date,
            coverage=coverage or {},
            canonical_snapshot=snapshot,
            idempotency_key=idem,
            created_by=actor if getattr(actor, "pk", None) else None,
            status=RatingRequest.Status.DRAFT,
        )
        audit(
            organization=organization,
            action="rating_request_created",
            actor=actor if getattr(actor, "pk", None) else None,
            resource_type="RatingRequest",
            resource_id=request.id,
            correlation_id=request.correlation_id,
            after={"client_id": client.id, "status": request.status},
        )
        enqueue_outbox(
            organization=organization,
            event_type="RatingRequestCreated",
            payload={"rating_request_id": request.id, "client_id": client.id},
            aggregate_type="RatingRequest",
            aggregate_id=request.id,
            correlation_id=request.correlation_id,
        )
    return request


def transition_rating_request(request: RatingRequest, nxt: str, *, actor=None, after=None) -> RatingRequest:
    before = request.status
    assert_transition(before, nxt)
    if before == nxt:
        return request
    request.status = nxt
    request.save(update_fields=["status", "updated_at"])
    audit(
        organization=request.organization,
        action="rating_request_status",
        actor=actor,
        resource_type="RatingRequest",
        resource_id=request.id,
        correlation_id=request.correlation_id,
        before={"status": before},
        after=after or {"status": nxt},
    )
    return request


def add_rating_job(
    request: RatingRequest,
    *,
    market,
    connection=None,
    eligibility=RatingJob.Eligibility.UNKNOWN,
    eligibility_reason="",
    status=RatingJob.Status.PENDING,
    actor=None,
) -> RatingJob:
    if market.organization_id != request.organization_id:
        raise ValueError("Market is not in this organization.")
    job, created = RatingJob.objects.get_or_create(
        rating_request=request,
        market=market,
        defaults={
            "organization": request.organization,
            "connection": connection,
            "eligibility": eligibility,
            "eligibility_reason": eligibility_reason,
            "status": status,
            "correlation_id": request.correlation_id,
            "idempotency_key": f"rate-job-{request.id}-{market.id}",
        },
    )
    if created:
        audit(
            organization=request.organization,
            action="rating_job_created" if status != RatingJob.Status.EXCLUDED else "market_excluded",
            actor=actor,
            resource_type="RatingJob",
            resource_id=job.id,
            correlation_id=request.correlation_id,
            after={
                "market_id": market.id,
                "status": job.status,
                "eligibility": job.eligibility,
                "reason": eligibility_reason,
            },
        )
    return job
