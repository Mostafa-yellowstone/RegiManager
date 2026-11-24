"""Carrier adapter contract.

A new carrier subclasses `CarrierAdapter`, names the portal and the environment
variables it needs, and registers itself. The quote job does not change.

`quote` must stop, with the missing item named, when the next step is an MVR,
a referral, a special case, MFA, or a bot check. It must not invent a premium
for that carrier and must not bypass the portal's own controls.
"""

from __future__ import annotations

from quoting.carriers.common import demo_foreign_license, hard_stops, live_quote
from quoting.engine.types import Application, CarrierResult


class CarrierAdapter:
    key = ""
    display_name = ""
    portal_url = ""
    secret_names: tuple[str, ...] = ()
    supported: frozenset[tuple[str, str]] = frozenset({("personal_auto", "NY")})

    def extra_hard_stops(self, application: Application) -> CarrierResult | None:
        return None

    def demo_stops(self, application: Application) -> CarrierResult | None:
        """Demo-only stops. Live mode asks the portal instead of using these."""

        return None

    def fixture(self, application: Application) -> CarrierResult:
        raise NotImplementedError

    def quote(self, application: Application, *, mode: str, session=None) -> CarrierResult:
        stopped = hard_stops(self, application)
        if stopped is not None:
            return stopped
        extra = self.extra_hard_stops(application)
        if extra is not None:
            return extra
        if mode == "demo":
            demo_stop = self.demo_stops(application)
            if demo_stop is not None:
                return demo_stop
            foreign = demo_foreign_license(self, application)
            if foreign is not None:
                return foreign
            return self.fixture(application)
        if mode == "live":
            return live_quote(self, application, session)
        raise ValueError(f"Unknown quote mode: {mode}")
