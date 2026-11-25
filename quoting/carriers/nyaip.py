"""New York Automobile Insurance Plan (Assigned Risk), via PASS.

Certified producers submit private-passenger applications at https://www.nypass.com/.
The plan is the residual market. This adapter does not log in, does not order an
MVR, and does not rate a plan premium unless the agent has recorded a voluntary-
market declination.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from quoting.carriers.base import CarrierAdapter
from quoting.carriers.common import quoted_offer, stopped
from quoting.carriers.fixtures import fixture_offer, illustrative_premium
from quoting.engine.types import Application, CarrierResult


class NyaipAdapter(CarrierAdapter):
    key = "nyaip"
    display_name = "New York Automobile Insurance Plan"
    portal_url = "https://www.nypass.com/"
    secret_names = (
        "NYAIP_AGENT_PORTAL_USERNAME",
        "NYAIP_AGENT_PORTAL_PASSWORD",
    )

    def extra_hard_stops(self, application: Application) -> CarrierResult | None:
        if not application.voluntary_market_declined:
            return stopped(
                self,
                code="special_case",
                title="Assigned Risk needs a voluntary declination",
                detail=(
                    "NYAIP is the residual market. No plan premium was rated because "
                    "a voluntary-market declination was not recorded."
                ),
                missing=("producer certification that a voluntary carrier declined this applicant",),
                origin="intake",
            )
        if not application.declination_carrier.strip():
            return stopped(
                self,
                code="special_case",
                title="Declination carrier is blank",
                detail="A voluntary-market declination was marked, but the carrier that declined was left blank.",
                missing=("name of the voluntary carrier that declined",),
                origin="intake",
            )
        return None

    def fixture(self, application: Application) -> CarrierResult:
        premium = illustrative_premium(
            application,
            base=Decimal("1180.00"),
            per_extra_driver=Decimal("120.00"),
            per_extra_vehicle=Decimal("260.00"),
            per_point=Decimal("90.00"),
        )
        offer = fixture_offer(application, prefix="NYAIP", premium=premium)
        note = (
            "Illustrative plan fixture for the demo, not an NYAIP premium. "
            f"The agent recorded a declination from {application.declination_carrier.strip()}. "
            "Inputs are the base, limits, deductibles, driver count, vehicle count, "
            "prior insurance, and chargeable points."
        )
        return quoted_offer(self, replace(offer, note=note))
