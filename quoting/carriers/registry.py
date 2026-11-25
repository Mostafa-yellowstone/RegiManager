"""Carrier registry.

Add a carrier by subclassing `CarrierAdapter` and registering it in
`default_registry`. The quote job iterates this registry for the line.
"""

from __future__ import annotations

from quoting.carriers.national_general import NationalGeneralAdapter
from quoting.carriers.nyaip import NyaipAdapter
from quoting.carriers.progressive import ProgressiveAdapter


class CarrierRegistry:
    def __init__(self):
        self._adapters: dict = {}

    def register(self, adapter) -> None:
        if not adapter.key:
            raise ValueError("A carrier adapter needs a key.")
        if adapter.key in self._adapters:
            raise ValueError(f"Carrier {adapter.key} is already registered.")
        self._adapters[adapter.key] = adapter

    def for_line(self, line: str, jurisdiction: str) -> tuple:
        return tuple(
            adapter
            for adapter in self._adapters.values()
            if (line, jurisdiction) in adapter.supported
        )

    def get(self, key: str):
        return self._adapters[key]


def default_registry() -> CarrierRegistry:
    registry = CarrierRegistry()
    registry.register(ProgressiveAdapter())
    registry.register(NationalGeneralAdapter())
    registry.register(NyaipAdapter())
    return registry


REGISTRY = default_registry()
