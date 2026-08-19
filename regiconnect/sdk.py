"""Insurance connector protocol. Implementations live under connectors/."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .exceptions import CapabilityNotSupported


class InsuranceConnector(ABC):
    slug = ""
    display_name = ""
    version = "1.0"
    missing_carrier_spec = False

    def capabilities(self) -> dict[str, bool]:
        return {
            "supportsSubmission": True,
            "supportsRating": False,
            "supportsQuote": True,
            "supportsBind": True,
            "supportsPolicyDownload": False,
            "supportsDocuments": True,
            "supportsCommissionDownload": False,
            "supportsClaims": False,
            "supportsWebhooks": True,
            "supportsSFTP": False,
            "supportsACORD": False,
            "supportsRealTimeRating": True,
        }

    def _require(self, key: str) -> None:
        if not self.capabilities().get(key):
            raise CapabilityNotSupported(f"{self.slug} does not support {key}")

    @abstractmethod
    def health_check(self, connection) -> dict[str, Any]:
        ...

    def validate_connection(self, connection) -> dict[str, Any]:
        return self.health_check(connection)

    def submit_submission(self, connection, submission) -> dict[str, Any]:
        self._require("supportsSubmission")
        raise CapabilityNotSupported(self.slug)

    def get_submission_status(self, connection, submission) -> dict[str, Any]:
        return {"status": submission.status}

    def request_quote(self, connection, submission) -> dict[str, Any]:
        self._require("supportsQuote")
        raise CapabilityNotSupported(self.slug)

    def get_quote(self, connection, submission) -> dict[str, Any]:
        return self.request_quote(connection, submission)

    def request_bind(self, connection, bind) -> dict[str, Any]:
        self._require("supportsBind")
        raise CapabilityNotSupported(self.slug)

    def get_bind_status(self, connection, bind) -> dict[str, Any]:
        return {"status": bind.status}

    def get_policy(self, connection, bind) -> dict[str, Any]:
        raise CapabilityNotSupported(self.slug)

    def download_transactions(self, connection) -> list[dict[str, Any]]:
        return []

    def download_documents(self, connection, submission) -> list[dict[str, Any]]:
        return []

    def handle_webhook(self, connection, payload: dict) -> dict[str, Any]:
        return {"accepted": True, "payload": payload}
