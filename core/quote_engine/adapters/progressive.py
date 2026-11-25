"""Progressive agent portal flow (personal auto), as done by hand on Nov 24 2026.

This module is the ORCHESTRATION only: the order of steps, the defaults, the safety stops. Talking to
the real site is a `ProgressiveDriver` (browser) that must be written and verified against the live
portal; none exists yet, so nothing here has touched Progressive. Tested with a fake driver.

Safety rules baked in:
- Fully automatic up to the money step, including the login OTP (read from the carrier's OTP mailbox).
- The only human gate is spend: Point of Sale orders CLUE/MVR and can cost money. Without
  `spend_approved` the run stops right before it with status "needs_approval".
- The driver interface has no bind/pay method. The flow ends at Point of Sale (rate visible).
- Any unknown question the portal asks that has no default stops the run with needs_input.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..carriers import QuoteResult
from ..otp import OtpNotFound

# Defaults the owner stated ("ثبت دول لحد ما تسمع غير كدا") and used on the second quote.
DEFAULT_COVERAGE = {"bi_pd": "25/50/25", "med_pay": 5000, "obel": 25000}
DEFAULT_ANSWERS = {
    "vehicle_use": "personal",
    "annual_miles": 10000,
    "marital_status": "single",
    "residence": "other",
    "known_accidents": "no",
}


class PortalQuestion(Exception):
    """The portal asked something we have no default for."""

    def __init__(self, question: str):
        super().__init__(question)
        self.question = question


class ProgressiveDriver(Protocol):
    def login(self, otp: Callable[[], str]) -> None: ...
    def new_auto_quote(self, state: str) -> None: ...
    def enter_drivers(self, drivers: list[dict], answers: dict) -> None: ...
    def enter_vehicles(self, vehicles: list[dict], answers: dict) -> None: ...
    def set_coverage(self, coverage: dict) -> None: ...
    def go_to_point_of_sale(self) -> None: ...  # orders CLUE/MVR
    def read_rate(self) -> dict: ...  # {"premium_term":..,"premium_monthly":..,"term_months":..,"ref":..,"alerts":[..]}
    def screenshot(self) -> str: ...
    def close(self) -> None: ...


@dataclass
class ProgressiveRun:
    steps_done: list[str] = field(default_factory=list)


def run_progressive(req: dict, driver: ProgressiveDriver, otp: Callable[[], str], spend_approved: bool,
                    answers: dict | None = None, coverage: dict | None = None, name: str = "Progressive") -> QuoteResult:
    if req.get("line_of_business") != "auto":
        return QuoteResult(name, "skipped", detail="Automation covers personal auto only for now.")
    ans = {**DEFAULT_ANSWERS, **(answers or {})}
    cov = {**DEFAULT_COVERAGE, **(coverage or {})}
    # Liability only vs full coverage, owned vs financed. Everything else stays default.
    veh_cov = []
    for i, v in enumerate(req.get("vehicles") or []):
        full = (v.get("coverage") or "liability") == "full"
        fin = (v.get("ownership") or "owned") in ("financed", "leased")
        if fin and not full:
            return QuoteResult(name, "needs_input", detail=f"Vehicle {i + 1} is financed/leased but set to liability only. The lender requires full coverage: confirm.")
        if fin and not (v.get("lienholder") or "").strip():
            return QuoteResult(name, "needs_input", detail=f"Vehicle {i + 1} is financed/leased: lienholder name is needed.")
        veh_cov.append({"index": i, "comp_collision": full, "lienholder": (v.get("lienholder") or "").strip() if fin else "",
                        "deductible_comp": v.get("deductible_comp"), "deductible_collision": v.get("deductible_collision")})
    cov["vehicles"] = veh_cov
    run = ProgressiveRun()
    try:
        driver.login(otp)
        run.steps_done.append("login")
        driver.new_auto_quote((req.get("garaging_address") or {}).get("state", ""))
        run.steps_done.append("new_quote")
        driver.enter_drivers(req["drivers"], ans)
        run.steps_done.append("drivers")
        driver.enter_vehicles(req["vehicles"], ans)
        run.steps_done.append("vehicles")
        driver.set_coverage(cov)
        run.steps_done.append("coverage")
        if not spend_approved:
            return QuoteResult(name, "needs_approval", detail="Ready for Point of Sale. Approve the MVR/Point of Sale charge to continue.",
                               extra={"steps_done": run.steps_done})
        driver.go_to_point_of_sale()
        run.steps_done.append("point_of_sale")
        rate = driver.read_rate()
        run.steps_done.append("rate")
    except OtpNotFound:
        return QuoteResult(name, "needs_input", detail="The login code was not entered. Type the code from the Progressive email, or run again.",
                           extra={"steps_done": run.steps_done})
    except PortalQuestion as q:
        return QuoteResult(name, "needs_input", detail=f"Portal asked: {q.question}", extra={"steps_done": run.steps_done})
    except Exception as exc:
        if type(exc).__name__ in ("PortalBlocked", "PortalValidation"):
            raise
        return QuoteResult(name, "error", detail=f"{type(exc).__name__} after {run.steps_done[-1] if run.steps_done else 'start'}", extra={"steps_done": run.steps_done})
    finally:
        try:
            driver.close()
        except Exception:
            pass
    if not rate or not rate.get("premium_term"):
        return QuoteResult(name, "declined", detail="; ".join(rate.get("alerts", [])) if rate else "No rate returned.",
                           extra={"steps_done": run.steps_done})
    return QuoteResult(name, "quoted", premium_monthly=rate.get("premium_monthly"), premium_term=rate["premium_term"],
                       term_months=rate.get("term_months") or 6, quote_ref=str(rate.get("ref") or ""),
                       detail="; ".join(rate.get("alerts", [])), extra={"steps_done": run.steps_done})
