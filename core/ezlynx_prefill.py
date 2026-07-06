"""Build AgentInsure / EZLynx Consumer Quoting prefill payloads."""

from __future__ import annotations

import re

EZLYNX_LOB_AUTO = "Auto"
EZLYNX_LOB_HOME = "Home"
EZLYNX_LOB_BOTH = "Both"


def split_us_phone(phone: str) -> tuple[str, str, str]:
    """Split a US phone into AgentInsure's three HomePhone segments."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return ("", "", "")
    return digits[:3], digits[3:6], digits[6:10]


def map_quote_type_to_lob(quote_type: str) -> str:
    return {
        "auto": EZLYNX_LOB_AUTO,
        "home": EZLYNX_LOB_HOME,
        "both": EZLYNX_LOB_BOTH,
    }.get((quote_type or "").strip().lower(), EZLYNX_LOB_AUTO)


def build_ezlynx_prefill_fields(intake) -> dict[str, str]:
    """
    Map a RegiManager InsuranceIntake row to AgentInsure quote.aspx POST fields.

    The CQ landing form expects a POST (not query-string) with these control names.
    """
    additional = intake.additional_data or {}
    quote_type = additional.get("ezlynx_quote_type", "auto")
    lob = map_quote_type_to_lob(quote_type)
    area, prefix, line = split_us_phone(intake.phone_number)

    fields = {
        "page": "0",
        "pagename": "Landing",
        "action": "",
        "arg": "",
        "Applicant_FirstName": (intake.first_name or "").strip(),
        "Applicant_LastName": (intake.last_name or "").strip(),
        "Applicant_Email": (intake.email or "").strip(),
        "Applicant_HomePhone": area,
        "Applicant_HomePhone_1": prefix,
        "Applicant_HomePhone_2": line,
        "Rating_Zip": (intake.zip_code or "").strip(),
        "Applicant_LOB": lob,
    }

    if lob in (EZLYNX_LOB_AUTO, EZLYNX_LOB_BOTH):
        fields["Custom_MobileHome"] = "No"

    return fields
