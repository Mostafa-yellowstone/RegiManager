"""Shared date-range parsing for owner companion API endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from rest_framework.exceptions import ValidationError

FROM_ALIASES = ("from_date", "start_date", "date_from", "start")
TO_ALIASES = ("to_date", "end_date", "date_to", "end")
MAX_RANGE_DAYS = 366


def _first_param(query_params: Any, names: tuple[str, ...]) -> str:
    for name in names:
        raw = query_params.get(name)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return ""


def _parse_iso_date(value: str, *, field: str) -> date:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Use YYYY-MM-DD."}) from exc


def parse_owner_date_range(query_params: Any) -> tuple[date, date] | None:
    """
    Parse inclusive custom date range from query params.

    Returns None when neither side is provided (presets-only mode).
    Raises ValidationError when the range is partial, invalid, inverted, or too wide.
    """
    from_raw = _first_param(query_params, FROM_ALIASES)
    to_raw = _first_param(query_params, TO_ALIASES)

    if not from_raw and not to_raw:
        return None
    if not from_raw or not to_raw:
        raise ValidationError(
            {"detail": "Both from_date and to_date are required (YYYY-MM-DD)."}
        )

    from_d = _parse_iso_date(from_raw, field="from_date")
    to_d = _parse_iso_date(to_raw, field="to_date")
    if from_d > to_d:
        raise ValidationError({"detail": "from_date must be on or before to_date."})

    span_days = (to_d - from_d).days + 1
    if span_days > MAX_RANGE_DAYS:
        raise ValidationError(
            {"detail": f"Date range cannot exceed {MAX_RANGE_DAYS} days."}
        )
    return from_d, to_d


def range_meta(from_d: date, to_d: date) -> dict:
    return {
        "from": from_d.isoformat(),
        "to": to_d.isoformat(),
        "source": "ledger",
        "days": (to_d - from_d).days + 1,
    }


def empty_dmv_period() -> dict:
    return {
        "total_records": 0,
        "total_revenue": "0.00",
        "gross_profit": "0.00",
        "net_profit_after_referral": "0.00",
        "referral_commission": "0.00",
        "dmv_fee": "0.00",
        "sales_tax": "0.00",
        "credit_card_fee": "0.00",
        "completed": 0,
        "pending": 0,
        "failed": 0,
        "refund": 0,
    }


def empty_insurance_period() -> dict:
    return {
        "bound_count": 0,
        "premium": "0.00",
        "commission": "0.00",
        "broker_fee": "0.00",
        "total_profit": "0.00",
        "quotes_count": 0,
        "conversion_pct": "0",
    }


def empty_space_period() -> dict:
    return {"profit": "0.00", "revenue": "0.00", "transactions": 0}
