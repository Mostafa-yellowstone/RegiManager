"""Normalize connector/validation failures for agents. Never dump raw carrier internals."""

from __future__ import annotations

from regiconnect.exceptions import (
    CapabilityNotSupported,
    MissingCarrierSpec,
    RetryableConnectorError,
    TerminalConnectorError,
)
from regiconnect.models import RatingError


def classify_error(exc: BaseException | str) -> tuple[str, bool, str, str]:
    """Return category, retryable, internal message, agent message."""
    text = str(exc)
    lower = text.lower()
    if isinstance(exc, MissingCarrierSpec) or "official" in lower and "spec" in lower:
        return (
            RatingError.Category.UNSUPPORTED,
            False,
            text,
            "This market is not available for electronic rating yet.",
        )
    if isinstance(exc, CapabilityNotSupported) or "does not support" in lower:
        return (
            RatingError.Category.UNSUPPORTED,
            False,
            text,
            "This market does not support rating for this request.",
        )
    if isinstance(exc, RetryableConnectorError) or any(
        h in lower for h in ("timeout", "429", "500", "502", "503", "504", "temporarily")
    ):
        category = RatingError.Category.TIMEOUT if "timeout" in lower else RatingError.Category.RATE_LIMIT if "429" in lower else RatingError.Category.NETWORK_ERROR
        if "500" in lower or "502" in lower or "503" in lower or "504" in lower:
            category = RatingError.Category.CARRIER_ERROR
        return (
            category,
            True,
            text,
            "The market did not finish rating. The system will retry if allowed.",
        )
    if isinstance(exc, TerminalConnectorError):
        if "auth" in lower:
            return (
                RatingError.Category.AUTHENTICATION_ERROR,
                False,
                text,
                "This market connection is not authorized. An administrator must repair it.",
            )
        if "invalid" in lower or "validat" in lower:
            return (
                RatingError.Category.VALIDATION_ERROR,
                False,
                text,
                "Required rating information is missing or invalid.",
            )
        return (
            RatingError.Category.CARRIER_ERROR,
            False,
            text,
            "The market could not complete this rating request.",
        )
    return (
        RatingError.Category.SYSTEM_ERROR,
        False,
        text,
        "Rating could not be completed. Try again or contact support.",
    )


def record_rating_error(*, organization, rating_request, rating_job=None, exc=None, message="", retryable=None, category=""):
    raw = message or str(exc or "")
    cat, retry, internal, agent = classify_error(exc if exc is not None else raw)
    if category:
        cat = category
    if retryable is not None:
        retry = retryable
    return RatingError.objects.create(
        organization=organization,
        rating_request=rating_request,
        rating_job=rating_job,
        category=cat,
        message=internal[:4000],
        agent_message=agent,
        retryable=retry,
    )
