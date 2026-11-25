"""Run one validated request against all eligible carriers in parallel."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date

from .carriers import CarrierAdapter, QuoteResult, get_carriers
from .validators import Issue, has_errors, validate_quote_request


@dataclass
class RunReport:
    issues: list[Issue]
    results: list[QuoteResult] = field(default_factory=list)
    blocked: bool = False

    def best(self) -> QuoteResult | None:
        quoted = [r for r in self.results if r.status == "quoted" and r.premium_term]
        return min(quoted, key=lambda r: r.premium_term) if quoted else None


def run_quotes(req: dict, carriers: list[CarrierAdapter] | None = None, today: date | None = None,
               max_workers: int = 6, per_carrier_timeout: float = 600.0,
               allowed_keys: set[str] | None = None, carrier_emails: dict[str, str] | None = None, spend_approved: bool = False) -> RunReport:
    issues = validate_quote_request(req, today)
    if has_errors(issues):
        return RunReport(issues=issues, blocked=True)
    pool = carriers if carriers is not None else get_carriers(req.get("line_of_business"))
    report = RunReport(issues=issues)
    todo: list[CarrierAdapter] = []
    for c in pool:
        why = c.eligibility(req)
        if not why and allowed_keys is not None and c.key not in allowed_keys:
            why = f"No enabled login for {c.name} (turn it on in Carrier credentials)."
        if why:
            report.results.append(QuoteResult(c.name, "skipped", detail=why))
        else:
            todo.append(c)

    def one(c: CarrierAdapter) -> QuoteResult:
        t = time.monotonic()
        try:
            creq = dict(req)
            creq["spend_approved"] = spend_approved
            if carrier_emails and carrier_emails.get(c.key):
                creq["otp_email"] = carrier_emails[c.key]
            r = c.quote(creq)
        except Exception as exc:  # one carrier failing must never stop the others
            r = QuoteResult(c.name, "error", detail=f"{type(exc).__name__}: {exc}")
        r.duration_s = round(time.monotonic() - t, 3)
        return r

    if todo:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(one, c): c for c in todo}
            for f in as_completed(futs, timeout=per_carrier_timeout * max(1, len(todo))):
                report.results.append(f.result())
    report.results.sort(key=lambda r: (r.status != "quoted", r.premium_term or 1e12, r.carrier))
    return report
