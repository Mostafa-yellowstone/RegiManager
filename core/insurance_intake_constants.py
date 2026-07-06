"""Insurance public intake: line-of-business groupings and validation helpers."""

from __future__ import annotations

PERSONAL_AUTO_INSURANCE_TYPES = frozenset({"auto_personal", "motor_cycle"})

COMMERCIAL_AUTO_INSURANCE_TYPES = frozenset({
    "commercial_auto",
    "trucking",
    "dealer_plates",
    "contractors",
    "landscaping",
})

# Excluded from public intake (medical / human lines).
EXCLUDED_INSURANCE_INTAKE_TYPES = frozenset({"disability"})

AUTO_INSURANCE_TYPES = PERSONAL_AUTO_INSURANCE_TYPES | COMMERCIAL_AUTO_INSURANCE_TYPES


def is_personal_auto(insurance_type: str) -> bool:
    return insurance_type in PERSONAL_AUTO_INSURANCE_TYPES


def is_commercial_auto(insurance_type: str) -> bool:
    return insurance_type in COMMERCIAL_AUTO_INSURANCE_TYPES


def requires_vehicle_fields(insurance_type: str) -> bool:
    return insurance_type in AUTO_INSURANCE_TYPES


def requires_business_fields(insurance_type: str) -> bool:
    return is_commercial_auto(insurance_type) or insurance_type in {
        "business_owners_policy",
        "general_liability",
        "workers_compensation",
    }


def insurance_intake_type_choices():
    from .models import InsurancePolicy

    return [
        (key, label)
        for key, label in InsurancePolicy.INSURANCE_TYPE_CHOICES
        if key not in EXCLUDED_INSURANCE_INTAKE_TYPES
    ]


INSURANCE_INTAKE_PORTAL_MODES = (
    ("native", "RegiManager full intake form"),
    ("ezlynx_dual", "EZLynx quote embed + RegiManager lead capture"),
    ("ezlynx_only", "EZLynx quote embed only"),
)

EZLYNX_QUOTE_TYPE_CHOICES = (
    ("auto", "Auto"),
    ("home", "Home / Condo / Renters"),
    ("both", "Auto & Home"),
)


def map_ezlynx_quote_type_to_insurance_type(quote_type: str) -> str:
    if quote_type == "home":
        return "home_owners"
    return "auto_personal"


def insurance_intake_effective_portal_mode(organization) -> str:
    mode = (getattr(organization, "insurance_intake_portal_mode", None) or "").strip()
    if mode:
        return mode
    if (getattr(organization, "insurance_ezlynx_quote_url", None) or "").strip():
        return "ezlynx_dual"
    return "native"
