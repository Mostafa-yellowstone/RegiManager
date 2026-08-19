"""Market access: appointment + producer code + connection. Never auto-activates appointments."""

from __future__ import annotations

from datetime import date

from .models import Appointment, Connection, MarketProfile, ProducerCode


class AccessDecision:
    def __init__(self, allowed: bool, reasons: list[str]):
        self.allowed = allowed
        self.reasons = reasons


def evaluate_market_access(
    *,
    organization,
    market: MarketProfile,
    state: str,
    line_of_business: str,
    on: date | None = None,
) -> AccessDecision:
    reasons: list[str] = []
    on = on or date.today()
    if market.organization_id != organization.id:
        return AccessDecision(False, ["Market belongs to another tenant."])
    if market.status != MarketProfile.Status.ACTIVE:
        reasons.append(f"Market status is {market.status}, not active.")
    if market.states and state and state.upper() not in {s.upper() for s in market.states}:
        reasons.append(f"State {state} is not on the market profile.")
    if market.lines_of_business and line_of_business and line_of_business not in market.lines_of_business:
        reasons.append(f"Line {line_of_business} is not on the market profile.")

    if market.requires_appointment:
        appt = _matching_appointment(market, state, line_of_business, on)
        if appt is None:
            reasons.append("No ACTIVE appointment covers this state and line of business.")
        else:
            reasons.append(f"Appointment {appt.id} is active.")

    if market.requires_producer_code:
        code = _matching_producer(market, state, line_of_business, on)
        if code is None:
            reasons.append("No producer code covers this state and line of business.")
        else:
            reasons.append(f"Producer code {code.code} matched.")

    conn = Connection.objects.filter(
        organization=organization,
        market=market,
        status=Connection.Status.ACTIVE,
    ).first()
    if conn is None:
        reasons.append("No ACTIVE connection for this market.")
    elif conn.environment == Connection.Environment.PRODUCTION and not conn.production_approved_at:
        reasons.append("Production connection is not certified/approved.")
    else:
        reasons.append(f"Connection {conn.id} ({conn.environment}) is active.")

    blocking = [
        r
        for r in reasons
        if r.startswith("No ")
        or "not active" in r
        or "not on the market" in r
        or "not certified" in r
        or "another tenant" in r
    ]
    return AccessDecision(not blocking, reasons)


def _matching_appointment(market, state, lob, on: date):
    qs = Appointment.objects.filter(market=market, status=Appointment.Status.ACTIVE)
    for appt in qs:
        if appt.state and state and appt.state.upper() != state.upper():
            continue
        if appt.line_of_business and lob and appt.line_of_business != lob:
            continue
        if appt.effective_date and on < appt.effective_date:
            continue
        if appt.expiration_date and on > appt.expiration_date:
            continue
        return appt
    return None


def _matching_producer(market, state, lob, on: date):
    for code in ProducerCode.objects.filter(market=market):
        if code.state and state and code.state.upper() != state.upper():
            continue
        if code.line_of_business and lob and code.line_of_business != lob:
            continue
        if code.effective_date and on < code.effective_date:
            continue
        if code.expiration_date and on > code.expiration_date:
            continue
        return code
    return None
