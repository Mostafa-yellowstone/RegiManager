"""Carrier registry and adapter interface (auto and commercial auto only).

Each carrier is a CarrierAdapter. Real portal automation lives in adapters
that implement `quote()`; until one is written the adapter returns
status "not_implemented" so nothing is ever reported as a fake price.
Eligibility rules here are used to skip carriers that cannot write the risk
BEFORE spending a portal login on them. They are starting values to be
confirmed against each carrier's guidelines, not carrier facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class QuoteResult:
    carrier: str
    status: str  # quoted | declined | skipped | needs_input | error | not_implemented
    premium_monthly: float | None = None
    premium_term: float | None = None
    term_months: int | None = None
    detail: str = ""
    quote_ref: str = ""
    duration_s: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CarrierAdapter:
    key: str
    name: str
    lines: tuple[str, ...]  # subset of ("auto", "commercial_auto")
    states: frozenset[str] | None = None  # None = all states we operate in
    max_vehicles: int = 99
    max_drivers: int = 99
    min_driver_age: int = 16
    portal_login_required: bool = True
    spend_gate: bool = False  # the run reaches a step that costs money (MVR/POS); a person must approve that step
    quote_fn: Callable[[dict], QuoteResult] | None = None

    def eligibility(self, req: dict) -> str | None:
        """Return a reason string if this carrier should be skipped, else None."""
        lob = req.get("line_of_business")
        if lob not in self.lines:
            return f"{self.name} does not write {lob}."
        st = ((req.get("garaging_address") or {}).get("state") or "").upper()
        if self.states is not None and st not in self.states:
            return f"{self.name} not available in {st}."
        if len(req.get("vehicles") or []) > self.max_vehicles:
            return f"More than {self.max_vehicles} vehicles."
        if len(req.get("drivers") or []) > self.max_drivers:
            return f"More than {self.max_drivers} drivers."
        return None

    def quote(self, req: dict) -> QuoteResult:
        if self.quote_fn is None:
            return QuoteResult(self.name, "not_implemented", detail="Portal automation for this carrier is not built yet.")
        return self.quote_fn(req)


_REGISTRY: dict[str, CarrierAdapter] = {}


def register(adapter: CarrierAdapter) -> CarrierAdapter:
    _REGISTRY[adapter.key] = adapter
    return adapter


def get_carriers(line: str | None = None) -> list[CarrierAdapter]:
    return [c for c in _REGISTRY.values() if line is None or line in c.lines]


# Progressive is the only carrier in the run for now. It is not mixed with the
# office's company list. Other portals stay out until each one has its own section.
register(CarrierAdapter("progressive", "Progressive", ("auto", "commercial_auto"), spend_gate=True))
