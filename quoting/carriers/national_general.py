"""National General, via the agent's NatGenAgency portal.

The public producer site is https://natgenagency.com/. This adapter does not
log in and does not complete MFA or a bot check on that site.
"""

from __future__ import annotations

from decimal import Decimal

from quoting.carriers.base import CarrierAdapter
from quoting.carriers.common import quoted_offer, stopped
from quoting.carriers.fixtures import fixture_offer, illustrative_premium
from quoting.engine.types import Application, CarrierResult


class NationalGeneralAdapter(CarrierAdapter):
    key = "national_general"
    display_name = "National General"
    portal_url = "https://natgenagency.com/"
    secret_names = (
        "NATIONAL_GENERAL_AGENT_PORTAL_USERNAME",
        "NATIONAL_GENERAL_AGENT_PORTAL_PASSWORD",
    )

    def demo_stops(self, application: Application) -> CarrierResult | None:
        flagged = [
            driver
            for driver in application.drivers
            if (driver.violations or 0) >= 3 or (driver.accidents or 0) >= 2
        ]
        if not flagged:
            return None
        missing = tuple(
            f"underwriting referral outcome for {driver.display_name}" for driver in flagged
        )
        return stopped(
            self,
            code="underwriting_referral",
            title="Underwriting referral",
            detail=(
                "Demo stop: a driver has 3 or more violations, or 2 or more accidents, in three years. "
                "A live National General quote would wait for the referral. This desk does not invent that decision."
            ),
            missing=missing,
            origin="demo",
        )

    def fixture(self, application: Application) -> CarrierResult:
        premium = illustrative_premium(
            application,
            base=Decimal("805.00"),
            per_extra_driver=Decimal("88.00"),
            per_extra_vehicle=Decimal("195.00"),
            per_point=Decimal("64.00"),
        )
        return quoted_offer(self, fixture_offer(application, prefix="NGIC", premium=premium))
