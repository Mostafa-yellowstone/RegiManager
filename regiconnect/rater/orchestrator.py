"""Carrier-agnostic rating orchestrator. Does not calculate premiums."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.models import Vehicle

from regiconnect.engines import create_submission
from regiconnect.models import CanonicalQuote, RatingJob, RatingRequest
from regiconnect.runtime import audit, dispatch_job, enqueue_job, enqueue_outbox

from .eligibility import evaluate_markets
from .errors import classify_error, record_rating_error
from .quotes import append_quote_version
from .requests import add_rating_job, transition_rating_request
from .state import IllegalRatingTransition


TERMINAL_JOB = {
    RatingJob.Status.EXCLUDED,
    RatingJob.Status.QUOTED,
    RatingJob.Status.REFERRED,
    RatingJob.Status.DECLINED,
    RatingJob.Status.FAILED,
    RatingJob.Status.CANCELLED,
    RatingJob.Status.EXPIRED,
}

IN_FLIGHT = {
    RatingJob.Status.PENDING,
    RatingJob.Status.QUEUED,
    RatingJob.Status.RATING,
}


def start_rating(request: RatingRequest, *, actor=None, market_ids=None) -> RatingRequest:
    """Evaluate markets and dispatch rating jobs. HTTP callers must not wait on carriers."""
    if request.status in {
        RatingRequest.Status.RATING,
        RatingRequest.Status.PARTIAL_RESULTS,
        RatingRequest.Status.COMPLETED,
        RatingRequest.Status.CANCELLED,
        RatingRequest.Status.EXPIRED,
        RatingRequest.Status.FAILED,
        RatingRequest.Status.NO_MARKET,
        RatingRequest.Status.REFERRED,
    }:
        return request

    if market_ids:
        snap = dict(request.canonical_snapshot or {})
        snap["selected_market_ids"] = list(market_ids)
        request.canonical_snapshot = snap
        request.save(update_fields=["canonical_snapshot", "updated_at"])

    if request.status == RatingRequest.Status.DRAFT:
        transition_rating_request(request, RatingRequest.Status.VALIDATING, actor=actor)
    if request.status == RatingRequest.Status.VALIDATING:
        _validate(request, actor=actor)
        request.refresh_from_db()
        if request.status == RatingRequest.Status.FAILED:
            return request
        transition_rating_request(request, RatingRequest.Status.ELIGIBILITY_CHECK, actor=actor)
    if request.status == RatingRequest.Status.ELIGIBILITY_CHECK:
        _apply_eligibility(request, actor=actor, market_ids=market_ids)
    request.refresh_from_db()
    if request.status == RatingRequest.Status.NO_MARKET:
        return request
    if request.status == RatingRequest.Status.READY:
        transition_rating_request(request, RatingRequest.Status.RATING, actor=actor)
        enqueue_outbox(
            organization=request.organization,
            event_type="RatingStarted",
            payload={"rating_request_id": request.id},
            aggregate_type="RatingRequest",
            aggregate_id=request.id,
            correlation_id=request.correlation_id,
        )
    _dispatch_eligible_jobs(request, actor=actor)
    return refresh_rating_request(request)


def rating_results(request: RatingRequest) -> dict:
    jobs = list(request.jobs.select_related("market__company", "connection").order_by("id"))
    quotes = list(
        CanonicalQuote.objects.filter(rating_request=request).select_related("market__company").order_by("id", "version")
    )
    return {
        "id": request.id,
        "status": request.status,
        "correlation_id": request.correlation_id,
        "jobs": [
            {
                "id": job.id,
                "market_id": job.market_id,
                "market_name": job.market.company.name,
                "market_channel": job.market.market_channel,
                "status": job.status,
                "eligibility": job.eligibility,
                "reason": job.eligibility_reason,
                "error_category": job.error_category,
            }
            for job in jobs
        ],
        "quotes": [
            {
                "id": quote.id,
                "market_id": quote.market_id,
                "market_name": quote.market.company.name,
                "version": quote.version,
                "premium": str(quote.premium),
                "taxes": str(quote.taxes),
                "fees": str(quote.fees),
                "total": str(quote.total),
                "coverage_type": (quote.coverage or {}).get("type") or "",
                "coverage": quote.coverage or {},
                "effective_date": str(quote.effective_date or ""),
                "expiration_date": str(quote.expiration_date or ""),
                "quote_source": quote.quote_source,
                "premium_class": quote.premium_class,
                "status": quote.status,
                "bind_supported": bool(
                    quote.premium_class == CanonicalQuote.PremiumClass.FINAL
                    and quote.quote_source != CanonicalQuote.QuoteSource.MOCK
                ),
            }
            for quote in quotes
        ],
        "coverage_mismatch": len({(q.coverage or {}).get("type") or "" for q in quotes if q.status != CanonicalQuote.Status.DECLINED}) > 1,
    }


def refresh_rating_request(request: RatingRequest) -> RatingRequest:
    request.refresh_from_db()
    jobs = list(request.jobs.all())
    if not jobs:
        return request
    in_flight = [j for j in jobs if j.status in IN_FLIGHT]
    quoted = [j for j in jobs if j.status == RatingJob.Status.QUOTED]
    referred = [j for j in jobs if j.status == RatingJob.Status.REFERRED]
    declined = [j for j in jobs if j.status == RatingJob.Status.DECLINED]
    failed = [j for j in jobs if j.status == RatingJob.Status.FAILED]
    eligible_or_sent = [j for j in jobs if j.status != RatingJob.Status.EXCLUDED]

    nxt = None
    if in_flight and (quoted or referred or declined or failed):
        nxt = RatingRequest.Status.PARTIAL_RESULTS
    elif in_flight:
        nxt = RatingRequest.Status.RATING
    elif quoted:
        nxt = RatingRequest.Status.COMPLETED
    elif referred and not quoted:
        nxt = RatingRequest.Status.REFERRED
    elif not eligible_or_sent:
        nxt = RatingRequest.Status.NO_MARKET
    elif declined and not failed:
        nxt = RatingRequest.Status.COMPLETED
    elif failed and not quoted:
        nxt = RatingRequest.Status.FAILED
    else:
        nxt = RatingRequest.Status.COMPLETED

    if nxt and nxt != request.status:
        try:
            transition_rating_request(request, nxt)
        except IllegalRatingTransition:
            pass
        if nxt in {RatingRequest.Status.COMPLETED, RatingRequest.Status.NO_MARKET, RatingRequest.Status.FAILED, RatingRequest.Status.REFERRED}:
            enqueue_outbox(
                organization=request.organization,
                event_type="RatingCompleted",
                payload={"rating_request_id": request.id, "status": nxt},
                aggregate_type="RatingRequest",
                aggregate_id=request.id,
                correlation_id=request.correlation_id,
            )
    return request


def on_connector_job_update(connector_job, *, result=None, error="", retry=False, terminal=False):
    payload = connector_job.payload or {}
    job_id = payload.get("rating_job_id")
    if not job_id:
        return
    rating_job = RatingJob.objects.select_related("rating_request", "market", "connection").filter(pk=job_id).first()
    if rating_job is None:
        return
    request = rating_job.rating_request
    if retry:
        rating_job.status = RatingJob.Status.RATING
        rating_job.last_error = (error or "")[:4000]
        cat, _, _, _ = classify_error(error)
        rating_job.error_category = cat
        rating_job.save(update_fields=["status", "last_error", "error_category", "updated_at"])
        record_rating_error(
            organization=request.organization,
            rating_request=request,
            rating_job=rating_job,
            message=error,
            retryable=True,
            category=cat,
        )
        refresh_rating_request(request)
        return
    if terminal:
        rating_job.status = RatingJob.Status.FAILED
        rating_job.last_error = (error or "")[:4000]
        rec = record_rating_error(
            organization=request.organization,
            rating_request=request,
            rating_job=rating_job,
            message=error,
            retryable=False,
        )
        rating_job.error_category = rec.category
        rating_job.save(update_fields=["status", "last_error", "error_category", "updated_at"])
        refresh_rating_request(request)
        return
    if result is None:
        return
    _apply_rating_result(rating_job, result)


def _validate(request: RatingRequest, *, actor=None) -> None:
    snap = request.canonical_snapshot or {}
    state = (request.state or snap.get("state") or "").strip()
    lob = (request.line_of_business or snap.get("line_of_business") or "").strip()
    problems = []
    if request.client.organization_id != request.organization_id:
        problems.append("Client is not in this organization.")
    if not state:
        problems.append("State is required for rating.")
    if not lob:
        problems.append("Line of business is required for rating.")
    if problems:
        request.last_error = " ".join(problems)
        request.save(update_fields=["last_error", "updated_at"])
        record_rating_error(
            organization=request.organization,
            rating_request=request,
            message=request.last_error,
            retryable=False,
            category="validation_error",
        )
        transition_rating_request(request, RatingRequest.Status.FAILED, actor=actor)


def _apply_eligibility(request: RatingRequest, *, actor=None, market_ids=None) -> None:
    decisions = evaluate_markets(request, market_ids=market_ids)
    if not decisions:
        request.last_error = "No markets exist for this organization."
        request.save(update_fields=["last_error", "updated_at"])
        transition_rating_request(request, RatingRequest.Status.NO_MARKET, actor=actor)
        return
    for decision in decisions:
        add_rating_job(
            request,
            market=decision.market,
            connection=decision.connection,
            eligibility=decision.eligibility,
            eligibility_reason=decision.reason_text,
            status=RatingJob.Status.QUEUED if decision.send_rating else RatingJob.Status.EXCLUDED,
            actor=actor,
        )
    if not any(d.send_rating for d in decisions):
        transition_rating_request(request, RatingRequest.Status.NO_MARKET, actor=actor)
        return
    transition_rating_request(request, RatingRequest.Status.READY, actor=actor)


def resume_pending_jobs(request: RatingRequest, *, actor=None) -> RatingRequest:
    """Poll delayed/async markets again. Does not invent a second quote pipeline."""
    jobs = list(
        RatingJob.objects.filter(rating_request=request, status=RatingJob.Status.RATING)
        .select_related("connection", "submission", "market", "rating_request")
    )
    for job in jobs:
        if job.connection_id is None or job.submission_id is None:
            continue
        connector_job = enqueue_job(
            organization=request.organization,
            connection=job.connection,
            operation="quote",
            payload={
                "submission_id": job.submission_id,
                "rating_job_id": job.id,
                "rating_request_id": request.id,
            },
            idempotency_key=f"job-rate-resume-{job.id}-{timezone.now().timestamp()}",
            correlation_id=request.correlation_id,
        )
        job.connector_job = connector_job
        job.save(update_fields=["connector_job", "updated_at"])
        dispatch_job(connector_job)
    return refresh_rating_request(request)


def _dispatch_eligible_jobs(request: RatingRequest, *, actor=None) -> None:
    jobs = list(
        RatingJob.objects.filter(
            rating_request=request,
            status=RatingJob.Status.QUEUED,
            eligibility=RatingJob.Eligibility.ELIGIBLE,
        ).select_related("market", "connection", "rating_request")
    )
    extra = list(
        RatingJob.objects.filter(
            rating_request=request,
            status=RatingJob.Status.QUEUED,
            eligibility=RatingJob.Eligibility.UNKNOWN,
        ).select_related("market", "connection", "rating_request")
    )
    seen = {j.id for j in jobs}
    for job in extra:
        if job.id not in seen:
            jobs.append(job)
    for job in jobs:
        _dispatch_one(job, actor=actor)


def _dispatch_one(job: RatingJob, *, actor=None) -> None:
    request = job.rating_request
    if job.connection_id is None:
        job.status = RatingJob.Status.EXCLUDED
        job.eligibility = RatingJob.Eligibility.UNAVAILABLE
        job.eligibility_reason = job.eligibility_reason or "No connection to dispatch."
        job.save(update_fields=["status", "eligibility", "eligibility_reason", "updated_at"])
        return
    vehicle = None
    vehicle_id = ((request.canonical_snapshot or {}).get("vehicle") or {}).get("vehicle_id")
    if vehicle_id:
        vehicle = Vehicle.objects.filter(pk=vehicle_id, client_id=request.client_id).first()
    extra = dict((request.canonical_snapshot or {}).get("extra") or {})
    extra["idempotency_key"] = f"rate-sub-{job.id}"
    extra["scenario"] = (request.canonical_snapshot or {}).get("scenario") or extra.get("scenario") or ""
    from regiconnect.models import RatingExtension

    extension = RatingExtension.objects.filter(rating_request=request, market_id=job.market_id).first()
    if extension and (extension.extra or {}).get("scenario"):
        extra["scenario"] = extension.extra["scenario"]
    with transaction.atomic():
        submission = create_submission(
            organization=request.organization,
            market=job.market,
            connection=job.connection,
            actor=actor,
            client=request.client,
            vehicle=vehicle,
            quote_lead=request.quote_lead,
            state=request.state,
            line_of_business=request.line_of_business,
            extra=extra,
            scenario=extra.get("scenario") or "",
            canonical=request.canonical_snapshot,
        )
        job.submission = submission
        job.status = RatingJob.Status.RATING
        job.idempotency_key = job.idempotency_key or f"rate-job-{request.id}-{job.market_id}"
        connector_job = enqueue_job(
            organization=request.organization,
            connection=job.connection,
            operation="quote",
            payload={
                "submission_id": submission.id,
                "rating_job_id": job.id,
                "rating_request_id": request.id,
            },
            idempotency_key=f"job-rate-{job.id}",
            correlation_id=request.correlation_id,
        )
        job.connector_job = connector_job
        job.save(update_fields=["submission", "status", "connector_job", "idempotency_key", "updated_at"])
    audit(
        organization=request.organization,
        action="rating_submitted",
        actor=actor,
        resource_type="RatingJob",
        resource_id=job.id,
        correlation_id=request.correlation_id,
        after={"market_id": job.market_id, "connector_job_id": job.connector_job_id},
    )
    dispatch_job(job.connector_job)


def _apply_rating_result(rating_job: RatingJob, result: dict) -> None:
    status = (result.get("status") or "quoted").lower()
    request = rating_job.rating_request
    if status == "declined":
        rating_job.status = RatingJob.Status.DECLINED
        rating_job.last_error = str(result.get("reason") or "Declined")
        rating_job.error_category = "decline"
        rating_job.save(update_fields=["status", "last_error", "error_category", "updated_at"])
        record_rating_error(
            organization=request.organization,
            rating_request=request,
            rating_job=rating_job,
            message=rating_job.last_error,
            retryable=False,
            category="decline",
        )
        refresh_rating_request(request)
        return
    if status == "referred":
        rating_job.status = RatingJob.Status.REFERRED
        rating_job.last_error = str(result.get("reason") or "Referred")
        rating_job.error_category = "referral"
        rating_job.save(update_fields=["status", "last_error", "error_category", "updated_at"])
        refresh_rating_request(request)
        return
    if status in {"pending", "queued", "rating"}:
        rating_job.status = RatingJob.Status.RATING
        rating_job.last_error = str(result.get("reason") or "Waiting for market")
        rating_job.save(update_fields=["status", "last_error", "updated_at"])
        refresh_rating_request(request)
        return
    slug = ""
    if rating_job.connection_id:
        slug = getattr(rating_job.connection.connector, "slug", "") or ""
    is_mock = slug == "mock"
    append_quote_version(
        organization=request.organization,
        market=rating_job.market,
        premium=result.get("premium") or "0",
        taxes=result.get("taxes") or 0,
        fees=result.get("fees") or 0,
        total=result.get("total"),
        coverage=result.get("coverage") or {},
        effective_date=result.get("effective_date"),
        expiration_date=result.get("expiration_date"),
        submission=rating_job.submission,
        rating_request=request,
        rating_job=rating_job,
        connection=rating_job.connection,
        quote_source=CanonicalQuote.QuoteSource.MOCK if is_mock else CanonicalQuote.QuoteSource.OTHER,
        premium_class=CanonicalQuote.PremiumClass.ESTIMATED,
        provider_slug=slug,
        environment=rating_job.connection.environment if rating_job.connection_id else "",
        external_reference=result.get("external_reference") or "",
    )
    rating_job.status = RatingJob.Status.QUOTED
    rating_job.last_error = ""
    rating_job.save(update_fields=["status", "last_error", "updated_at"])
    refresh_rating_request(request)
