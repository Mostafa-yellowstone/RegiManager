"""Placeholder for a real market that has not provided official specs."""

from __future__ import annotations

from typing import Any

from ..exceptions import MissingCarrierSpec
from ..sdk import InsuranceConnector


class UnspecifiedCarrierConnector(InsuranceConnector):
    slug = "unspecified"
    display_name = "Unspecified carrier (spec required)"
    version = "0.0"
    missing_carrier_spec = True

    def capabilities(self) -> dict[str, bool]:
        return {key: False for key in super().capabilities()}

    def health_check(self, connection) -> dict[str, Any]:
        raise MissingCarrierSpec(
            "No official carrier integration specification is on file. "
            "Do not invent endpoints or credentials."
        )
