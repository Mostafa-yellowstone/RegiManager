"""Connects the Progressive browser driver to the carrier registry and the Regi backend.

The login is read from the backend Carrier credentials screen (CarrierCredential, encrypted, every read logged).
The runner passes it in req["_credential"]. No environment variables. The login code is typed by a person in
the Regi modal: req["otp_provider"] blocks until it is entered. No mailbox reading.
req["spend_approved"] is the modal approval for MVR / Point of Sale. Bind and Final Sale are never done.
"""
from __future__ import annotations

import os
import time

from ..carriers import QuoteResult, get_carriers
from .progressive import run_progressive
from .progressive_driver import PortalBlocked, PortalValidation, ProgressiveBrowserDriver

LOGIN_URL = "https://www.foragentsonly.com"


def to_driver_input(req: dict) -> tuple[list[dict], list[dict], str | None]:
    """Engine request -> driver input. Returns (drivers, vehicles, missing_reason)."""
    g = req.get("garaging_address") or {}
    contact = req.get("contact") or {}
    drivers = []
    for i, d in enumerate(req.get("drivers") or []):
        dob = str(d.get("date_of_birth") or "")
        if len(dob) == 10 and dob[4] == "-":
            dob = f"{dob[5:7]}/{dob[8:10]}/{dob[:4]}"
        gender = {"m": "M", "male": "M", "f": "F", "female": "F"}.get(str(d.get("gender") or "").strip().lower())
        if i == 0 and not gender:
            return [], [], "The portal requires the driver's gender and the lead does not have it. Add it, then run again."
        drivers.append({"first_name": d.get("first_name", ""), "last_name": d.get("last_name", ""), "dob": dob, "gender": gender or "M",
                        "phone": contact.get("phone", "") if i == 0 else "",
                        "address": {"line1": g.get("street", ""), "city": g.get("city", ""), "zip": g.get("zip", "")}})
    eff = str(req.get("effective_date") or "")
    if len(eff) == 10 and eff[4] == "-":
        eff = f"{eff[5:7]}/{eff[8:10]}/{eff[:4]}"
    vehicles = [{"vin": v.get("vin", ""), "effective_date": eff} for v in req.get("vehicles") or []]
    return drivers, vehicles, None


def make_quote_fn(page_factory=None):
    def quote_fn(req: dict) -> QuoteResult:
        t0 = time.time()
        cred, otp = req.get("_credential"), req.get("otp_provider")
        if cred is None or not cred.enabled or not cred.has_password():
            return QuoteResult("Progressive", "needs_input", detail="Turn on the Progressive login in Carrier credentials.")
        if otp is None:
            return QuoteResult("Progressive", "needs_input", detail="The login code is entered by a person in the Regi modal.")
        drivers, vehicles, why = to_driver_input(req)
        if why:
            return QuoteResult("Progressive", "needs_input", detail=why)
        req = {**req, "drivers": drivers, "vehicles": vehicles}
        try:
            if page_factory is None:
                from .playwright_page import PlaywrightPage
                page = PlaywrightPage(os.environ.get("QUOTE_BROWSER_PROFILE_DIR", "/var/lib/regi/progressive-profile"))
                page.goto(cred.portal_url or LOGIN_URL)
            else:
                page = page_factory()
        except ImportError:
            return QuoteResult("Progressive", "needs_input", detail="The browser (Playwright/Chromium) is not installed on the server yet.")
        driver = ProgressiveBrowserDriver(page, cred.username, cred.get_password(actor="quote-engine", purpose="progressive quote"))
        try:
            res = run_progressive(req, driver, otp, bool(req.get("spend_approved")), answers=req.get("answers"), coverage=req.get("coverage"))
            if res.status in ("quoted", "needs_approval"):
                cred.record_result(True)
        except PortalBlocked as exc:
            cred.record_result(False, status=cred.Status.LOCKED, error="Portal showed a challenge or lockout page.")
            res = QuoteResult("Progressive", "error", detail="Portal showed a challenge or lockout. Stopped: a person must check the login. Login turned off.")
        except PortalValidation as exc:
            res = QuoteResult("Progressive", "needs_input", detail="Portal rejected a field: " + "; ".join(exc.errors))
        res.duration_s = time.time() - t0
        return res
    return quote_fn


def install() -> None:
    for c in get_carriers():
        if c.key == "progressive" and c.quote_fn is None:
            c.quote_fn = make_quote_fn()
