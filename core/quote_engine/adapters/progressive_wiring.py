"""Connects the Progressive browser driver to the carrier registry.

Credentials come from the server environment (PROGRESSIVE_USER, PROGRESSIVE_PASSWORD), never from agents or
the database. The quote is enabled only when both are set AND PROGRESSIVE_AUTOMATION=1, so a missing setting
leaves the carrier on "not_implemented" instead of failing. The OTP is typed by a person in the Regi modal:
the caller passes `req["otp_provider"]` (a callable that blocks until the code is entered). No mailbox reading.
`req["spend_approved"]` is the modal approval for MVR/Point of Sale. Bind and Final Sale are never done.
"""
from __future__ import annotations

import os
import time

from ..carriers import QuoteResult, get_carriers
from .progressive import run_progressive
from .progressive_driver import PortalBlocked, PortalValidation, ProgressiveBrowserDriver

LOGIN_URL = "https://www.foragentsonly.com"


def enabled() -> bool:
    return os.environ.get("PROGRESSIVE_AUTOMATION") == "1" and bool(os.environ.get("PROGRESSIVE_USER")) and bool(os.environ.get("PROGRESSIVE_PASSWORD"))


def make_quote_fn(page_factory=None, env=os.environ):
    def quote_fn(req: dict) -> QuoteResult:
        t0 = time.time()
        otp = req.get("otp_provider")
        if otp is None:
            return QuoteResult("Progressive", "needs_input", detail="The login code is entered by a person in the Regi modal.")
        if page_factory is None:
            from .playwright_page import PlaywrightPage
            page = PlaywrightPage(env.get("PROGRESSIVE_PROFILE_DIR", "/var/lib/regi/progressive-profile"))
            page.goto(LOGIN_URL)
        else:
            page = page_factory()
        driver = ProgressiveBrowserDriver(page, env["PROGRESSIVE_USER"], env["PROGRESSIVE_PASSWORD"])
        try:
            res = run_progressive(req, driver, otp, bool(req.get("spend_approved")), answers=req.get("answers"), coverage=req.get("coverage"))
        except PortalBlocked as exc:
            res = QuoteResult("Progressive", "error", detail=f"Portal showed a challenge or lockout. Stopped, a person must check. ({exc})")
        except PortalValidation as exc:
            res = QuoteResult("Progressive", "needs_input", detail="Portal rejected a field: " + "; ".join(exc.errors))
        res.duration_s = time.time() - t0
        return res
    return quote_fn


def install() -> bool:
    """Attach the driver to the registered Progressive adapter when the server is configured for it."""
    if not enabled():
        return False
    for c in get_carriers():
        if c.key == "progressive":
            c.quote_fn = make_quote_fn()
            return True
    return False
