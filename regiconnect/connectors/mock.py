"""Fully simulated market for development and automated tests. No network I/O."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ..exceptions import RetryableConnectorError, TerminalConnectorError
from ..sdk import InsuranceConnector


class MockCarrierConnector(InsuranceConnector):
    slug = "mock"
    display_name = "RegiConnect Mock Carrier"
    version = "1.0"
    missing_carrier_spec = False

    def health_check(self, connection) -> dict[str, Any]:
        return {"ok": True, "connector": self.slug, "environment": connection.environment}

    def submit_submission(self, connection, submission) -> dict[str, Any]:
        scenario = _scenario(submission)
        if scenario == "invalid":
            raise TerminalConnectorError("Mock carrier rejected invalid request.")
        if scenario == "auth":
            raise TerminalConnectorError("Mock carrier authentication failed.")
        return {"external_reference": f"MOCK-SUB-{submission.id}", "status": "received"}

    def request_quote(self, connection, submission) -> dict[str, Any]:
        scenario = _scenario(submission)
        if scenario == "timeout":
            raise RetryableConnectorError("Mock timeout")
        if scenario == "429":
            raise RetryableConnectorError("429 rate limited")
        if scenario == "500":
            raise RetryableConnectorError("500 upstream")
        if scenario == "decline":
            return {"status": "declined", "reason": "Mock decline"}
        if scenario == "refer":
            return {"status": "referred", "reason": "Mock referral"}
        payload = submission.canonical_payload or {}
        premium = _mock_premium(payload)
        vehicle = payload.get("vehicle") or {}
        driver = payload.get("driver") or {}
        coverage = payload.get("coverage") or {}
        return {
            "status": "quoted",
            "external_reference": f"MOCK-Q-{submission.id}",
            "premium": str(premium),
            "taxes": "24.00",
            "fees": "15.00",
            "total": str(premium + Decimal("39.00")),
            "effective_date": str(date.today()),
            "expiration_date": str(date.today() + timedelta(days=180)),
            "coverage": {
                "type": coverage.get("type") or submission.line_of_business or "auto_personal",
                "vin": vehicle.get("vin") or "",
                "driver_license": driver.get("driver_license") or "",
                "mock": True,
            },
        }

    def request_bind(self, connection, bind) -> dict[str, Any]:
        scenario = _scenario(bind.submission)
        if scenario == "bind_fail":
            raise TerminalConnectorError("Mock bind declined.")
        return {
            "status": "bound",
            "external_reference": f"MOCK-B-{bind.id}",
            "policy_number": f"MOCK-POL-{bind.submission_id}",
        }

    def download_documents(self, connection, submission) -> list[dict[str, Any]]:
        return [{"doc_type": "quote", "external_reference": f"MOCK-DOC-{submission.id}"}]

    def handle_webhook(self, connection, payload: dict) -> dict[str, Any]:
        return {"accepted": True, "event": payload.get("event") or "mock"}


def _scenario(submission) -> str:
    extra = getattr(getattr(submission, "extension", None), "scenario", "") or ""
    notes = (submission.canonical_payload or {}).get("scenario") or ""
    return (extra or notes or "quote").lower()


def _mock_premium(payload: dict) -> Decimal:
    """Sandbox illustration only — not a real underwriting rate."""
    premium = Decimal("1200.00")
    vehicle = payload.get("vehicle") or {}
    try:
        year = int(vehicle.get("year") or 0)
    except (TypeError, ValueError):
        year = 0
    if year >= 2022:
        premium += Decimal("150.00")
    elif year and year <= 2010:
        premium -= Decimal("100.00")
    coverage = payload.get("coverage") or {}
    if (coverage.get("type") or "").lower() == "full":
        premium += Decimal("300.00")
    risk = payload.get("risk") or {}
    if risk.get("has_accident"):
        premium += Decimal("200.00")
    try:
        points = int(risk.get("mvr_points") or 0)
    except (TypeError, ValueError):
        points = 0
    if points > 0:
        premium += Decimal(str(min(points, 20) * 25))
    return premium
