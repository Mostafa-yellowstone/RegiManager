"""Shared stop reasons and the live-portal gate.

Demo referral thresholds live on each carrier. They are not carrier manuals.
Live mode does not apply those thresholds and does not log in.
"""

from __future__ import annotations

from decimal import Decimal

from quoting.engine.secrets import missing_names
from quoting.engine.types import Application, Blocker, CarrierResult, QuoteOffer


class PortalChallenge(Exception):
    """The portal is showing a step the agent has to finish.

    `kind` is `mfa` or `bot_check`. Callers must stop. They must not solve it.
    """

    def __init__(self, kind: str, detail: str):
        if kind not in ("mfa", "bot_check"):
            raise ValueError("Portal challenges are MFA or a bot check.")
        self.kind = kind
        self.detail = detail
        super().__init__(detail)


class PortalHold:
    """A portal page that is not a finished quote. The agent has to supply something."""

    def __init__(self, code: str, title: str, detail: str, missing: tuple[str, ...]):
        self.code = code
        self.title = title
        self.detail = detail
        self.missing = missing


class PortalQuote:
    """A quote the portal itself returned through an agent session."""

    def __init__(self, quote_number: str, term_premium: Decimal, term_months: int, note: str = ""):
        self.quote_number = quote_number
        self.term_premium = term_premium
        self.term_months = term_months
        self.note = note


def stopped(adapter, *, code: str, title: str, detail: str, missing: tuple[str, ...], origin: str) -> CarrierResult:
    return CarrierResult(
        carrier_key=adapter.key,
        carrier_name=adapter.display_name,
        portal_url=adapter.portal_url,
        status="blocked",
        blocker=Blocker(code=code, title=title, detail=detail, missing=missing, origin=origin),
    )


def quoted_offer(adapter, offer: QuoteOffer) -> CarrierResult:
    return CarrierResult(
        carrier_key=adapter.key,
        carrier_name=adapter.display_name,
        portal_url=adapter.portal_url,
        status="quoted",
        offer=offer,
    )


def _drivers_needing_mvr(application: Application) -> tuple[str, ...]:
    names = []
    if application.mvr_pending:
        names.extend(driver.display_name for driver in application.drivers)
    else:
        names.extend(driver.display_name for driver in application.drivers if driver.mvr_required)
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def hard_stops(adapter, application: Application) -> CarrierResult | None:
    """Facts that block a quote in demo and live mode. No premium is estimated."""

    mvr_names = _drivers_needing_mvr(application)
    if mvr_names:
        listed = ", ".join(mvr_names)
        return stopped(
            adapter,
            code="mvr_required",
            title="Motor vehicle report needed",
            detail=(
                f"An MVR is still needed for {listed}. "
                "The quote was not submitted and an MVR was not ordered."
            ),
            missing=tuple(f"motor vehicle report for {name}" for name in mvr_names),
            origin="intake",
        )

    business = [vehicle.display_name for vehicle in application.vehicles if vehicle.usage == "business"]
    if business:
        listed = ", ".join(business)
        return stopped(
            adapter,
            code="special_case",
            title="Business use is outside personal auto",
            detail=(
                f"{listed} is rated as business use. "
                "v1 quotes New York personal auto (pleasure or commute) only."
            ),
            missing=tuple(f"a commercial auto quote for {name}" for name in business),
            origin="intake",
        )

    unexplained = [
        driver
        for driver in application.drivers
        if driver.license_state != "NY" and not driver.license_state_reason.strip()
    ]
    if unexplained:
        missing = tuple(
            f"why {driver.display_name}'s license is from {driver.license_state}"
            for driver in unexplained
        )
        return stopped(
            adapter,
            code="special_case",
            title="Out-of-state license needs an explanation",
            detail="A license from outside New York needs the agent's explanation before a quote is started.",
            missing=missing,
            origin="intake",
        )

    if not application.prior.currently_insured and not application.prior.lapse_reason.strip():
        return stopped(
            adapter,
            code="special_case",
            title="No current policy",
            detail="The applicant is not currently insured. The reason was left blank, so it was not filled in.",
            missing=("reason the applicant has no current policy",),
            origin="intake",
        )
    return None


def demo_foreign_license(adapter, application: Application) -> CarrierResult | None:
    foreign = [driver for driver in application.drivers if driver.license_state != "NY"]
    if not foreign:
        return None
    missing = tuple(
        f"a portal decision on the {driver.license_state} license for {driver.display_name}"
        for driver in foreign
    )
    return stopped(
        adapter,
        code="special_case",
        title="Out-of-state license",
        detail=(
            "Demo stop: this fixture does not rate an out-of-state license. "
            "A live quote would be the portal's decision, not an estimated premium."
        ),
        missing=missing,
        origin="demo",
    )


def live_quote(adapter, application: Application, session) -> CarrierResult:
    """Finish a live quote only from an agent session that is already past portal checks.

    Missing environment variables stop the carrier with the variable names.
    A configured login still needs the agent to complete the portal, including
    MFA or a bot check. Those checks are not bypassed, and no password is read
    into the result.
    """

    missing = missing_names(adapter.secret_names)
    if missing:
        return CarrierResult(
            carrier_key=adapter.key,
            carrier_name=adapter.display_name,
            portal_url=adapter.portal_url,
            status="needs_credentials",
            blocker=Blocker(
                code="needs_credentials",
                title="Portal login is not configured",
                detail=(
                    f"{adapter.display_name} was not quoted. "
                    "Set the agent portal variables in the server environment. "
                    "Do not paste them into the app or the repo."
                ),
                missing=missing,
                origin="portal",
            ),
        )
    if session is None:
        return stopped(
            adapter,
            code="interactive_login_required",
            title="Agent portal session required",
            detail=(
                f"The {adapter.display_name} environment variables are set. "
                "This desk does not log in to the portal. "
                "A quote is not submitted until the agent finishes the portal's own login, "
                "including MFA or a bot check. Those checks are not bypassed."
            ),
            missing=("an agent-completed portal session",),
            origin="portal",
        )

    try:
        session.ensure_ready()
    except PortalChallenge as challenge:
        return _challenge_result(adapter, challenge)

    try:
        payload = session.submit_quote(application)
    except PortalChallenge as challenge:
        return _challenge_result(adapter, challenge)

    if isinstance(payload, PortalHold):
        return stopped(
            adapter,
            code=payload.code,
            title=payload.title,
            detail=payload.detail,
            missing=payload.missing,
            origin="portal",
        )
    if not isinstance(payload, PortalQuote):
        return stopped(
            adapter,
            code="missing_information",
            title="Portal response was not a quote",
            detail="The portal session did not return a quote. No premium was estimated.",
            missing=("a portal quote number and term premium",),
            origin="portal",
        )
    number = (payload.quote_number or "").strip()
    premium = payload.term_premium
    if not number or premium is None or premium <= 0 or payload.term_months not in (6, 12):
        return stopped(
            adapter,
            code="missing_information",
            title="Portal quote was incomplete",
            detail="The portal did not return a quote number, a term, and a premium. Nothing was filled in.",
            missing=("quote number", "term months", "term premium"),
            origin="portal",
        )
    note = payload.note.strip() or "Premium returned by the agent portal session."
    return quoted_offer(
        adapter,
        QuoteOffer(
            quote_number=number,
            term_premium=premium,
            term_months=payload.term_months,
            coverages=_coverage_rows(application),
            source="portal",
            illustrative=False,
            note=note,
        ),
    )


def _challenge_result(adapter, challenge: PortalChallenge) -> CarrierResult:
    if challenge.kind == "mfa":
        title = "Multi-factor check"
        missing = ("agent completion of the portal's MFA step",)
    else:
        title = "Portal bot check"
        missing = ("agent completion of the portal's bot check",)
    return stopped(
        adapter,
        code="portal_challenge",
        title=title,
        detail=challenge.detail,
        missing=missing,
        origin="portal",
    )


def _coverage_rows(application: Application) -> tuple[tuple[str, str], ...]:
    coverage = application.coverage
    comp = "none" if coverage.comprehensive_deductible is None else f"{coverage.comprehensive_deductible:,}"
    coll = "none" if coverage.collision_deductible is None else f"{coverage.collision_deductible:,}"
    pip = f"{int(coverage.pip):,}" if coverage.pip.isdigit() else coverage.pip
    damage = f"{int(coverage.property_damage):,}" if coverage.property_damage.isdigit() else coverage.property_damage
    return (
        ("Bodily injury", coverage.bodily_injury),
        ("Property damage", damage),
        ("PIP", pip),
        ("Uninsured motorist", coverage.uninsured_motorist),
        ("Comprehensive deductible", comp),
        ("Collision deductible", coll),
    )


def coverage_rows(application: Application) -> tuple[tuple[str, str], ...]:
    return _coverage_rows(application)
