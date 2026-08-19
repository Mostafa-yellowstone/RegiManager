"""Auditable RatingRequest status transitions."""

from __future__ import annotations

from typing import FrozenSet

from regiconnect.models import RatingRequest


class IllegalRatingTransition(ValueError):
    pass


RatingRequestStatus = RatingRequest.Status

ALLOWED: dict[str, FrozenSet[str]] = {
    RatingRequest.Status.DRAFT: frozenset(
        {
            RatingRequest.Status.VALIDATING,
            RatingRequest.Status.CANCELLED,
            RatingRequest.Status.EXPIRED,
        }
    ),
    RatingRequest.Status.VALIDATING: frozenset(
        {
            RatingRequest.Status.ELIGIBILITY_CHECK,
            RatingRequest.Status.FAILED,
            RatingRequest.Status.CANCELLED,
        }
    ),
    RatingRequest.Status.ELIGIBILITY_CHECK: frozenset(
        {
            RatingRequest.Status.READY,
            RatingRequest.Status.NO_MARKET,
            RatingRequest.Status.FAILED,
            RatingRequest.Status.CANCELLED,
        }
    ),
    RatingRequest.Status.READY: frozenset(
        {
            RatingRequest.Status.RATING,
            RatingRequest.Status.CANCELLED,
            RatingRequest.Status.EXPIRED,
        }
    ),
    RatingRequest.Status.RATING: frozenset(
        {
            RatingRequest.Status.PARTIAL_RESULTS,
            RatingRequest.Status.COMPLETED,
            RatingRequest.Status.REFERRED,
            RatingRequest.Status.NO_MARKET,
            RatingRequest.Status.FAILED,
            RatingRequest.Status.CANCELLED,
        }
    ),
    RatingRequest.Status.PARTIAL_RESULTS: frozenset(
        {
            RatingRequest.Status.COMPLETED,
            RatingRequest.Status.REFERRED,
            RatingRequest.Status.FAILED,
            RatingRequest.Status.CANCELLED,
            RatingRequest.Status.EXPIRED,
            RatingRequest.Status.RATING,
        }
    ),
    RatingRequest.Status.COMPLETED: frozenset({RatingRequest.Status.EXPIRED}),
    RatingRequest.Status.REFERRED: frozenset(
        {RatingRequest.Status.EXPIRED, RatingRequest.Status.CANCELLED}
    ),
    RatingRequest.Status.NO_MARKET: frozenset({RatingRequest.Status.CANCELLED}),
    RatingRequest.Status.FAILED: frozenset({RatingRequest.Status.CANCELLED}),
    RatingRequest.Status.CANCELLED: frozenset(),
    RatingRequest.Status.EXPIRED: frozenset(),
}


def assert_transition(current: str, nxt: str) -> None:
    if current == nxt:
        return
    allowed = ALLOWED.get(current, frozenset())
    if nxt not in allowed:
        raise IllegalRatingTransition(f"Cannot move rating request from {current} to {nxt}.")
