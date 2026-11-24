"""Portal credential names.

Values stay in the process environment. This module reports whether a name
is set. It never returns, logs, or stores the value.
"""

from __future__ import annotations

import os


def is_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def missing_names(names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if not is_set(name))


def status_for(adapters) -> tuple[dict, ...]:
    """One row per secret name, in carrier order. `present` is only a boolean."""

    rows = []
    seen = set()
    for adapter in adapters:
        for name in adapter.secret_names:
            if name in seen:
                continue
            seen.add(name)
            rows.append(
                {
                    "carrier_key": adapter.key,
                    "carrier_name": adapter.display_name,
                    "name": name,
                    "present": is_set(name),
                }
            )
    return tuple(rows)
