"""Shared VIN validation for modern (17-digit) and legacy (pre-1981) identifiers."""

import re

LEGACY_VIN_MIN = 5
LEGACY_VIN_MAX = 16
MODERN_VIN_LENGTH = 17
FORBIDDEN_MODERN = frozenset("IOQ")


def normalize_vin(vin):
    return (vin or "").strip().upper().replace(" ", "").replace("-", "")


def is_modern_vin(vin):
    normalized = normalize_vin(vin)
    return (
        len(normalized) == MODERN_VIN_LENGTH
        and normalized.isalnum()
        and not any(char in normalized for char in FORBIDDEN_MODERN)
    )


def is_legacy_vin_length(vin):
    normalized = normalize_vin(vin)
    return LEGACY_VIN_MIN <= len(normalized) <= LEGACY_VIN_MAX


def validate_modern_vin(vin):
    normalized = normalize_vin(vin)
    if not normalized:
        return False, "VIN is required."
    if len(normalized) != MODERN_VIN_LENGTH:
        return (
            False,
            f"A modern VIN must be exactly {MODERN_VIN_LENGTH} characters, "
            "or enable Legacy VIN for pre-1981 vehicles.",
        )
    if any(char in normalized for char in FORBIDDEN_MODERN):
        return False, "A modern VIN cannot contain the letters I, O, or Q."
    if not normalized.isalnum():
        return False, "VIN must contain only letters and numbers."
    return True, ""


def validate_legacy_vin(vin):
    normalized = normalize_vin(vin)
    if not normalized:
        return False, "VIN is required."
    if len(normalized) == MODERN_VIN_LENGTH and is_modern_vin(normalized):
        return False, "This is a 17-digit VIN — disable Legacy VIN to use standard validation."
    if not is_legacy_vin_length(normalized):
        return (
            False,
            f"Legacy VIN must be between {LEGACY_VIN_MIN} and {LEGACY_VIN_MAX} characters.",
        )
    if not re.fullmatch(r"[A-Z0-9]+", normalized):
        return False, "Legacy VIN must contain only letters and numbers."
    return True, ""


def validate_vin(vin, *, legacy=False):
    if legacy:
        return validate_legacy_vin(vin)
    return validate_modern_vin(vin)
