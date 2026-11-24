"""Run a quote from a form submission. HTTP callers never attach a portal session."""

from __future__ import annotations

from datetime import date

from quoting.engine.job import run_quote_job
from quoting.engine.types import JobResult
from quoting.intake import parse_form, requested_carriers, requested_mode


def run_from_form(data, *, mode: str | None = None, today: date | None = None, sessions=None) -> JobResult:
    application, _invalid = parse_form(data)
    # Unchecked boxes are omitted. `carriers_submitted` marks a form that showed
    # the picker, so an empty selection stays empty instead of quoting everyone.
    if _has_key(data, "carriers_submitted") or _has_key(data, "carriers"):
        selected = requested_carriers(data)
    else:
        selected = None
    return run_quote_job(
        application,
        mode=mode or requested_mode(data),
        carriers=selected,
        sessions=sessions,
        today=today,
    )


def _has_key(data, key: str) -> bool:
    if hasattr(data, "getlist"):
        return key in data
    return key in data
