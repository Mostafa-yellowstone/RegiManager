"""Playwright implementation of the driver's Page interface. Needs `pip install playwright` and
`playwright install chromium` on the server (not installed in the review sandbox, so this file has only
been checked for syntax). Uses one persistent profile so the portal keeps the session between runs."""
from __future__ import annotations

import os
import time


class PlaywrightPage:
    def __init__(self, profile_dir: str, headless: bool = True):
        from playwright.sync_api import sync_playwright  # imported late: optional dependency
        self._pw = sync_playwright().start()
        os.makedirs(profile_dir, exist_ok=True)
        self._ctx = self._pw.chromium.launch_persistent_context(profile_dir, headless=headless, viewport={"width": 1280, "height": 720})
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")

    def _loc(self, label: str):
        p = self.page
        for loc in (p.get_by_label(label, exact=False), p.get_by_role("button", name=label), p.get_by_role("link", name=label),
                    p.get_by_text(label, exact=False)):
            if loc.count():
                return loc.first
        raise LookupError(f"No element for '{label}'")

    def text(self) -> str:
        return self.page.inner_text("body")

    def fill(self, label: str, value: str) -> None:
        el = self._loc(label)
        el.click()
        el.fill("")  # clear first, typing appends on this portal
        el.press_sequentially(value, delay=60)

    def read(self, label: str) -> str:
        el = self._loc(label)
        try:
            return el.input_value()
        except Exception:
            return el.inner_text()

    def select(self, label: str, option: str) -> None:
        self._loc(label).select_option(label=option)

    def click(self, label: str) -> None:
        self._loc(label).click()

    def pick_suggestion(self, text: str) -> None:
        self.page.get_by_role("option", name=text, exact=False).first.click()

    def screenshot(self) -> str:
        path = f"/tmp/progressive-{int(time.time())}.png"
        self.page.screenshot(path=path)
        return path

    def close(self) -> None:
        try:
            self._ctx.close()
        finally:
            self._pw.stop()
