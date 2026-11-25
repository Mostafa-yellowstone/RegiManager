"""Browser driver for the Progressive agent portal.

Talks to the site through a small `Page` interface so the logic is testable without a browser. A Playwright
implementation (`PlaywrightPage`) is at the bottom. Rules learned live on Nov 25 2026:
- Typing appends: always clear a field first, then type, then read it back.
- Changing a dependent dropdown RESETS the fields after it: after each select, read back and set again once.
- Locate fields by their visible label, never by id (ids change on each render).
- The address needs the autocomplete suggestion clicked. Modals need an explicit close.
- Pace like a person (small random delays), one session, one step at a time. Never retry in a loop.
- A challenge, lockout or captcha page stops the run (PortalBlocked). We do not try to get around it.
"""
from __future__ import annotations

import random
import time
from typing import Callable

from . import progressive_portal_spec as spec
from .progressive import PortalQuestion


class PortalBlocked(Exception):
    """The portal showed a challenge or lockout. A human must look at it."""


class PortalValidation(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class Page:  # interface
    def text(self) -> str: ...
    def fill(self, label: str, value: str) -> None: ...  # clear, type
    def read(self, label: str) -> str: ...
    def select(self, label: str, option: str) -> None: ...
    def click(self, label: str) -> None: ...
    def pick_suggestion(self, text: str) -> None: ...
    def screenshot(self) -> str: ...
    def close(self) -> None: ...


def _pause(lo=0.25, hi=0.9, sleep=time.sleep):
    sleep(random.uniform(lo, hi))


class ProgressiveBrowserDriver:
    def __init__(self, page: Page, username: str, password: str, sleep: Callable[[float], None] = time.sleep):
        self.page, self._user, self._pw, self._sleep = page, username, password, sleep
        self.errors_seen: list[str] = []

    # --- helpers
    def _guard(self):
        t = self.page.text().lower()
        if any(m in t for m in spec.CHALLENGE_MARKERS):
            raise PortalBlocked("The portal showed a challenge or lockout page.")

    def _set(self, label: str, value: str, kind: str = "text"):
        for attempt in (1, 2):
            if kind == "select":
                self.page.select(label, value)
            else:
                self.page.fill(label, value)
            _pause(sleep=self._sleep)
            got = self.page.read(label)
            if value.lower() in (got or "").lower() or (got or "").lower().startswith(value.lower()[:6]) \
                    or (kind == "text" and "".join(ch for ch in got if ch.isalnum()) == "".join(ch for ch in value if ch.isalnum())):
                return
        raise PortalQuestion(f"Could not set '{label}' to the requested value (the portal kept a different value).")

    def _errors(self) -> list[str]:
        out, lines = [], self.page.text().splitlines()
        for i, ln in enumerate(lines):
            if ln.strip().startswith("Error:"):
                msg = ln.strip()[6:].strip() or (lines[i + 1].strip() if i + 1 < len(lines) else "")
                if msg:
                    out.append(msg)
        return out

    def _next(self, step: str):
        self.page.click(spec.NEXT_BUTTON[step])
        _pause(1.0, 2.0, sleep=self._sleep)
        self._guard()
        errs = self._errors()
        if errs:
            self.errors_seen += errs
            raise PortalValidation(errs)

    # --- ProgressiveDriver protocol
    def login(self, otp: Callable[[], str]) -> None:
        self.page.fill("User ID", self._user)
        self.page.fill("User Password", self._pw)
        self.page.click("Log In")
        _pause(2, 4, sleep=self._sleep)
        self._guard()
        if any(m in self.page.text().lower() for m in spec.OTP_MARKERS):
            code = otp()  # blocks until the user types it in the Regi modal; raises OtpNotFound on timeout
            self.page.fill("One-time passcode", code)
            self.page.click("Continue")
            _pause(2, 4, sleep=self._sleep)
            if any(m in self.page.text().lower() for m in spec.OTP_MARKERS):
                raise PortalQuestion("The login code was rejected. Request a new code.")
        self._guard()

    def new_auto_quote(self, state: str) -> None:
        self.page.select("State", state)
        self.page.click("Select Product(s)")
        self.page.click("AUTO")
        self.page.click("Add Products to Quote")
        _pause(3, 5, sleep=self._sleep)
        self._guard()

    def enter_drivers(self, drivers: list[dict], answers: dict) -> None:  # Named insured + household
        d, ni = drivers[0], spec.NAMED_INSURED
        a = d.get("address") or {}
        self._set(ni["first_name"], d["first_name"]); self._set(ni["last_name"], d["last_name"])
        self._set(ni["dob"], d["dob"].replace("/", "").replace("-", ""))
        self._set(ni["gender"], {"M": "Male", "F": "Female"}.get(d.get("gender", "M"), d.get("gender", "Male")), "select")
        if d.get("phone"):
            self._set(ni["phone"], "".join(c for c in d["phone"] if c.isdigit())[-10:])
        self._set(ni["zip"], a.get("zip", "")); self._set(ni["city"], a.get("city", ""))
        self.page.fill(ni["address1"], a.get("line1", "")); _pause(sleep=self._sleep); self.page.pick_suggestion(a.get("line1", ""))
        self._set(ni["moved"], "No", "select"); self._set(ni["disclosure"], "Yes", "select")
        self._next("Named Insured")
        self._pending_drivers = drivers

    def enter_vehicles(self, vehicles: list[dict], answers: dict) -> None:
        v, vh = vehicles[0], spec.VEHICLE
        self._set(vh["effective"], v.get("effective_date", "").replace("/", ""))
        self.page.fill(vh["vin"], v["vin"]); self.page.click("Search for and verify the VIN")
        _pause(2, 3, sleep=self._sleep)
        if "VERIFIED" not in self.page.text():
            raise PortalQuestion("The portal could not verify the VIN.")
        self._set(vh["owned_for"], v.get("owned_for", "Less than 1 month"), "select")
        self._set(vh["use"], "Pleasure/Personal" if answers.get("vehicle_use") == "personal" else "Commute", "select")
        self._set(vh["for_hire"], "No", "select")
        self._set(vh["miles"], spec.miles_band(int(answers.get("annual_miles", 10000))), "select")
        self._next("Products")
        hh = spec.HOUSEHOLD
        self._set(hh["marital"], answers.get("marital_status", "single").capitalize(), "select")
        self._set(hh["license_type"], "Personal Auto", "select"); self._set(hh["license_status"], "Valid", "select")
        self._set(hh["years_licensed"], "3 years or more", "select")
        self._next("Household Members")
        ad = spec.ADDITIONAL
        self._set(ad["prior"], "Yes, currently insured", "select")
        self._set(ad["term12"], "Yes", "select")
        self._set(ad["prior_pgr"], "No", "select")
        self._set(ad["prior_bi"], "State Minimum Limits", "select")
        self._set(ad["prior_years"], "At least 1 year but less than 3 years", "select")
        self._set(ad["titled"], "Yes", "select"); self._set(ad["everyone"], "Yes", "select")
        self._set(ad["pip_claims"], "0", "select"); self._set(ad["residents"], "1", "select")
        self._set(ad["residence"], answers.get("residence", "other").capitalize(), "select")
        self.page.click("No additional risks apply")
        self._next("Additional Details")

    def set_coverage(self, coverage: dict) -> None:
        # Coverages screen recorded live; setting each coverage is the next live pass.
        self._guard()

    def go_to_point_of_sale(self) -> None:
        raise PortalQuestion("Portfolio and Point of Sale screens are not recorded yet, so the driver cannot go past Coverages.")

    def read_rate(self) -> dict:
        raise PortalQuestion("Rate page not recorded yet.")

    def screenshot(self) -> str:
        return self.page.screenshot()

    def close(self) -> None:
        self.page.close()
