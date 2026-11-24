"""Illustrative premiums for the demo path.

These numbers are a stable function of the application so the demo can be
checked. They are not Progressive, National General, or NYAIP rates.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_HALF_UP

from quoting.engine.types import Application, QuoteOffer
from quoting.carriers.common import coverage_rows

BI_FACTOR = {
    "25/50": Decimal("1.00"),
    "50/100": Decimal("1.18"),
    "100/300": Decimal("1.42"),
    "250/500": Decimal("1.70"),
}
PD_FACTOR = {
    "10": Decimal("1.00"),
    "25": Decimal("1.06"),
    "50": Decimal("1.11"),
    "100": Decimal("1.18"),
}
PHYSICAL_DAMAGE = {
    1000: Decimal("280"),
    500: Decimal("410"),
    250: Decimal("560"),
    100: Decimal("720"),
}
CENT = Decimal("0.01")
FIXTURE_NOTE = (
    "Illustrative fixture for the demo. Inputs are the base, limits, deductibles, "
    "driver count, vehicle count, prior insurance, and chargeable points. Not a carrier rate."
)


def illustrative_premium(
    application: Application,
    *,
    base: Decimal,
    per_extra_driver: Decimal,
    per_extra_vehicle: Decimal,
    per_point: Decimal,
) -> Decimal:
    drivers = len(application.drivers)
    vehicles = len(application.vehicles)
    points = sum((driver.accidents or 0) + (driver.violations or 0) for driver in application.drivers)
    premium = base
    premium += per_extra_driver * max(drivers - 1, 0)
    premium += per_extra_vehicle * max(vehicles - 1, 0)
    premium += per_point * points
    premium *= BI_FACTOR[application.coverage.bodily_injury]
    premium *= PD_FACTOR[application.coverage.property_damage]
    comp = application.coverage.comprehensive_deductible
    coll = application.coverage.collision_deductible
    if comp is not None and coll is not None:
        premium += PHYSICAL_DAMAGE[min(comp, coll)] * vehicles
    if not application.prior.currently_insured:
        premium *= Decimal("1.15")
    if application.coverage.term_months == 12:
        premium *= Decimal("1.92")
    return premium.quantize(CENT, rounding=ROUND_HALF_UP)


def demo_quote_number(prefix: str, application: Application) -> str:
    payload = "|".join(
        (
            prefix,
            application.named_insured.last_name.upper(),
            application.effective_date.isoformat() if application.effective_date else "",
            ",".join(vehicle.vin for vehicle in application.vehicles),
            application.coverage.bodily_injury,
            str(application.coverage.term_months),
        )
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:8].upper()
    return f"DEMO-{prefix}-{digest}"


def fixture_offer(application: Application, *, prefix: str, premium: Decimal) -> QuoteOffer:
    return QuoteOffer(
        quote_number=demo_quote_number(prefix, application),
        term_premium=premium,
        term_months=application.coverage.term_months or 6,
        coverages=coverage_rows(application),
        source="fixture",
        illustrative=True,
        note=FIXTURE_NOTE,
    )
