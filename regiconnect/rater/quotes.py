"""Append CanonicalQuote versions. Never overwrite an existing version."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db.models import Max
from django.utils import timezone

from regiconnect.models import CanonicalQuote
from regiconnect.runtime import audit, enqueue_outbox


def _as_date(value):
    if value in (None, ""):
        return None
    if hasattr(value, "year") and not isinstance(value, str):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def next_quote_version(*, submission=None, rating_job=None) -> int:
    qs = CanonicalQuote.objects.all()
    if rating_job is not None:
        qs = qs.filter(rating_job=rating_job)
    elif submission is not None:
        qs = qs.filter(submission=submission)
    else:
        raise ValueError("submission or rating_job is required")
    current = qs.aggregate(Max("version"))["version__max"] or 0
    return current + 1


def append_quote_version(
    *,
    organization,
    market,
    premium,
    submission=None,
    rating_request=None,
    rating_job=None,
    connection=None,
    taxes=0,
    fees=0,
    total=None,
    coverage=None,
    effective_date=None,
    expiration_date=None,
    status=CanonicalQuote.Status.QUOTED,
    quote_source=CanonicalQuote.QuoteSource.OTHER,
    premium_class=CanonicalQuote.PremiumClass.ESTIMATED,
    environment="",
    mapping_version="",
    provider_slug="",
    external_reference="",
    actor=None,
) -> CanonicalQuote:
    if submission is None and rating_job is None:
        raise ValueError("A quote must attach to a Submission or a RatingJob.")
    version = next_quote_version(submission=submission, rating_job=rating_job)
    premium_d = Decimal(str(premium))
    taxes_d = Decimal(str(taxes or 0))
    fees_d = Decimal(str(fees or 0))
    total_d = Decimal(str(total)) if total is not None else (premium_d + taxes_d + fees_d)
    conn = connection
    if conn is None and submission is not None:
        conn = submission.connection
    if conn is None and rating_job is not None:
        conn = rating_job.connection
    env = environment or (conn.environment if conn is not None else "")
    quote = CanonicalQuote.objects.create(
        organization=organization,
        submission=submission,
        rating_request=rating_request or (rating_job.rating_request if rating_job is not None else None),
        rating_job=rating_job,
        connection=conn,
        market=market,
        version=version,
        premium=premium_d,
        taxes=taxes_d,
        fees=fees_d,
        total=total_d,
        coverage=coverage or {},
        effective_date=_as_date(effective_date),
        expiration_date=_as_date(expiration_date),
        quoted_at=timezone.now(),
        status=status,
        quote_source=quote_source,
        premium_class=premium_class,
        environment=env,
        mapping_version=mapping_version,
        provider_slug=provider_slug,
        external_reference=str(external_reference or ""),
    )
    audit(
        organization=organization,
        action="quote_received",
        actor=actor,
        resource_type="CanonicalQuote",
        resource_id=quote.id,
        correlation_id=(
            (rating_request.correlation_id if rating_request else "")
            or (submission.correlation_id if submission else "")
        ),
        after={
            "version": version,
            "quote_source": quote.quote_source,
            "premium_class": quote.premium_class,
            "premium": str(quote.premium),
        },
    )
    enqueue_outbox(
        organization=organization,
        event_type="QuoteReceived",
        payload={
            "quote_id": quote.id,
            "version": version,
            "quote_source": quote.quote_source,
        },
        aggregate_type="CanonicalQuote",
        aggregate_id=quote.id,
        correlation_id=quote.rating_request.correlation_id if quote.rating_request_id else "",
    )
    return quote
