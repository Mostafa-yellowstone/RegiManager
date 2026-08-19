"""Market selection for a rating request. Carrier schemas stay in connectors."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from regiconnect.access import evaluate_market_access
from regiconnect.appetite import evaluate_appetite
from regiconnect.connectors import get_connector
from regiconnect.models import Connection, MarketProfile, RatingJob


@dataclass
class MarketEligibility:
    market: MarketProfile
    connection: Connection | None
    eligibility: str
    status: str
    reasons: list[str] = field(default_factory=list)
    send_rating: bool = False

    @property
    def reason_text(self) -> str:
        return " ".join(self.reasons).strip()


def merged_capabilities(connection: Connection | None) -> dict:
    if connection is None:
        return {}
    live = {}
    try:
        live = dict(get_connector(connection.connector.slug).capabilities() or {})
    except Exception:
        live = {}
    stored = dict(connection.capabilities or connection.connector.capabilities or {})
    return {**live, **stored}


def evaluate_markets(request, *, market_ids=None) -> list[MarketEligibility]:
    qs = MarketProfile.objects.filter(organization=request.organization).select_related("company")
    if market_ids:
        qs = qs.filter(id__in=list(market_ids))
    rows = []
    on = request.effective_date or timezone.localdate()
    canonical = request.canonical_snapshot or {}
    state = (request.state or canonical.get("state") or "").upper()
    lob = request.line_of_business or canonical.get("line_of_business") or ""
    for market in qs.order_by("id"):
        rows.append(_evaluate_one(request, market, state=state, lob=lob, on=on, canonical=canonical))
    return rows


def _evaluate_one(request, market, *, state, lob, on, canonical) -> MarketEligibility:
    if market.market_channel == MarketProfile.MarketChannel.ASSIGNED_RISK:
        return MarketEligibility(
            market=market,
            connection=None,
            eligibility=RatingJob.Eligibility.UNAVAILABLE,
            status=RatingJob.Status.EXCLUDED,
            reasons=[
                "Assigned Risk is not a voluntary market. "
                "Agents cannot select a servicing carrier; NYAIP assignment is not electronically filed in RegiManager."
            ],
            send_rating=False,
        )

    access = evaluate_market_access(
        organization=request.organization,
        market=market,
        state=state,
        line_of_business=lob,
        on=on,
    )
    connection = Connection.objects.filter(
        organization=request.organization,
        market=market,
        status=Connection.Status.ACTIVE,
    ).select_related("connector").first()

    if not access.allowed:
        return MarketEligibility(
            market=market,
            connection=connection,
            eligibility=RatingJob.Eligibility.INELIGIBLE,
            status=RatingJob.Status.EXCLUDED,
            reasons=access.reasons,
            send_rating=False,
        )

    if connection is None:
        return MarketEligibility(
            market=market,
            connection=None,
            eligibility=RatingJob.Eligibility.UNAVAILABLE,
            status=RatingJob.Status.EXCLUDED,
            reasons=["No ACTIVE connection for this market."],
            send_rating=False,
        )

    if connection.connector.missing_carrier_spec:
        return MarketEligibility(
            market=market,
            connection=connection,
            eligibility=RatingJob.Eligibility.UNAVAILABLE,
            status=RatingJob.Status.EXCLUDED,
            reasons=["No official carrier specification is on file. Rating is not enabled."],
            send_rating=False,
        )

    caps = merged_capabilities(connection)
    if not caps.get("supportsRating") and not caps.get("supportsQuote"):
        return MarketEligibility(
            market=market,
            connection=connection,
            eligibility=RatingJob.Eligibility.UNAVAILABLE,
            status=RatingJob.Status.EXCLUDED,
            reasons=["This connection does not declare rating or quote capability."],
            send_rating=False,
        )

    appetite = evaluate_appetite(market, canonical)
    reasons = list(access.reasons) + list(appetite.reasons)
    if appetite.result == "ineligible":
        return MarketEligibility(
            market=market,
            connection=connection,
            eligibility=RatingJob.Eligibility.INELIGIBLE,
            status=RatingJob.Status.EXCLUDED,
            reasons=reasons,
            send_rating=False,
        )
    if appetite.result == "refer":
        return MarketEligibility(
            market=market,
            connection=connection,
            eligibility=RatingJob.Eligibility.REFER,
            status=RatingJob.Status.EXCLUDED,
            reasons=reasons + ["Internal appetite requires referral before electronic rating."],
            send_rating=False,
        )

    return MarketEligibility(
        market=market,
        connection=connection,
        eligibility=RatingJob.Eligibility.ELIGIBLE if appetite.result in {"eligible", "unknown"} else RatingJob.Eligibility.UNKNOWN,
        status=RatingJob.Status.PENDING,
        reasons=reasons,
        send_rating=True,
    )
