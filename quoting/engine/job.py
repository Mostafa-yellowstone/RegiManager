"""Run one quote job across the carriers registered for the line."""

from __future__ import annotations

from datetime import date

from quoting.engine.lines import validate_application
from quoting.engine.types import Application, Issue, JobResult


def run_quote_job(
    application: Application,
    *,
    mode: str = "demo",
    carriers: tuple[str, ...] | None = None,
    sessions=None,
    registry=None,
    today: date | None = None,
) -> JobResult:
    """Quote each selected carrier.

    A carrier that needs an MVR, a referral, a special case, or a portal step
    the agent has not finished returns a stop for that carrier only. Other
    carriers still run. Premiums are never filled in for a stop.
    """

    from quoting.carriers.registry import REGISTRY

    registry = registry if registry is not None else REGISTRY
    sessions = sessions or {}
    if today is None:
        from quoting.intake import ny_today

        today = ny_today()

    if mode not in ("demo", "live"):
        return JobResult(
            status="intake_incomplete",
            mode=mode,
            issues=(Issue("mode", "Quote mode must be demo or live."),),
            results=(),
        )

    issues = list(validate_application(application, today=today))
    if issues:
        return JobResult(status="intake_incomplete", mode=mode, issues=tuple(issues), results=())

    available = list(registry.for_line(application.line, application.jurisdiction))
    by_key = {adapter.key: adapter for adapter in available}
    if carriers is None:
        selected = available
    else:
        unknown = [key for key in carriers if key not in by_key]
        if unknown:
            issues.append(Issue("carriers", "Unknown carrier: " + ", ".join(unknown) + "."))
        if not carriers:
            issues.append(Issue("carriers", "Choose at least one carrier."))
        selected = [by_key[key] for key in carriers if key in by_key]
    if issues:
        return JobResult(status="intake_incomplete", mode=mode, issues=tuple(issues), results=())
    if not selected:
        return JobResult(
            status="intake_incomplete",
            mode=mode,
            issues=(Issue("carriers", "No carrier is registered for this line."),),
            results=(),
        )

    results = []
    for adapter in selected:
        session = sessions.get(adapter.key)
        try:
            results.append(adapter.quote(application, mode=mode, session=session))
        except Exception:
            from quoting.carriers.common import stopped

            results.append(
                stopped(
                    adapter,
                    code="carrier_error",
                    title="Carrier adapter stopped",
                    detail="The adapter stopped before a quote. No premium was estimated.",
                    missing=("a completed carrier response",),
                    origin="portal" if mode == "live" else "demo",
                )
            )
    return JobResult(status="completed", mode=mode, issues=(), results=tuple(results))
