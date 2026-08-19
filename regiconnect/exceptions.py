class RegiConnectError(Exception):
    """Base error for the connectivity layer."""


class CapabilityNotSupported(RegiConnectError):
    pass


class MissingCarrierSpec(RegiConnectError):
    """Raised when a real connector has no official carrier documentation."""


class RetryableConnectorError(RegiConnectError):
    """Timeouts, 429, 5xx — safe to retry."""


class TerminalConnectorError(RegiConnectError):
    """Auth failures, validation, carrier rejection — do not retry."""


class SecretAccessError(RegiConnectError):
    pass
