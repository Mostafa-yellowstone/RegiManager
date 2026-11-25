"""Progressive, via the agent's ForAgentsOnly portal.

The public site is https://www.foragentsonly.com/. Login there uses the agent's
own id and, when Progressive asks, a one-time passcode. This adapter does not
log in and does not complete that step.
"""

from __future__ import annotations

from decimal import Decimal

from quoting.carriers.base import CarrierAdapter
from quoting.carriers.common import quoted_offer, stopped
from quoting.carriers.fixtures import fixture_offer, illustrative_premium
from quoting.engine.types import Application, CarrierResult


class ProgressiveAdapter(CarrierAdapter):
    key = "progressive"
    display_name = "Progressive"
    portal_url = "https://www.foragentsonly.com/"
    secret_names = (
        "PROGRESSIVE_AGENT_PORTAL_USERNAME",
        "PROGRESSIVE_AGENT_PORTAL_PASSWORD",
    )

    def demo_stops(self, application: Application) -> CarrierResult | None:
        flagged = [
            driver
            for driver in application.drivers
            if (driver.accidents or 0) + (driver.violations or 0) >= 2
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
                "Demo stop: a driver has 2 or more accidents and violations in three years. "
                "A live Progressive quote would wait for the referral. This desk does not invent that decision."
            ),
            missing=missing,
            origin="demo",
        )

    def fixture(self, application: Application) -> CarrierResult:
        premium = illustrative_premium(
            application,
            base=Decimal("742.00"),
            per_extra_driver=Decimal("95.00"),
            per_extra_vehicle=Decimal("210.00"),
            per_point=Decimal("70.00"),
        )
        return quoted_offer(self, fixture_offer(application, prefix="PGR", premium=premium))
