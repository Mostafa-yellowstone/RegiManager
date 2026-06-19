"""NY DMV / sales tax estimate helpers for the public intake portal."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .us_states import normalize_state_code

NY_SALES_TAX_CALCULATOR_URL = "https://www.salestaxhandbook.com/new-york/calculator"
NY_DMV_FEE_CALCULATOR_URL = "https://process.dmv.ny.gov/regfeecalc/"


def show_ny_fee_estimate_section(organization) -> bool:
    state = normalize_state_code(getattr(organization, "state", None) or "NY")
    return state == "NY"


def parse_fee_estimate(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if amount < 0:
        return None
    return amount.quantize(Decimal("0.01"))


def get_fee_estimate(additional_data, key: str) -> Decimal | None:
    if not additional_data:
        return None
    return parse_fee_estimate(additional_data.get(key))


def merge_fee_estimates_into_additional_data(additional_data, *, sales_tax=None, dmv_fees=None) -> dict:
    data = dict(additional_data or {})
    for key, value in (
        ("estimated_sales_tax", sales_tax),
        ("estimated_dmv_fees", dmv_fees),
    ):
        parsed = parse_fee_estimate(value)
        if parsed is None:
            data.pop(key, None)
        else:
            data[key] = str(parsed)
    return data
