"""Metrics helpers for the Finance & BI hub hero section."""

import calendar
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum

from .daily_payments import PAYMENT_METHOD_META
from .models import DailyPaymentTransaction

CARD_METHODS = frozenset({
    "visa",
    "mastercard",
    "discover",
    "diners_club",
    "american_express",
})


def _bucket_for_method(payment_method):
    if payment_method == "cash":
        return "cash"
    if payment_method == "zelle":
        return "zelle"
    if payment_method == "checks":
        return "checks"
    if payment_method in CARD_METHODS:
        return "credit_card"
    return None


def _add_to_bucket(totals, payment_method, amount):
    bucket = _bucket_for_method(payment_method)
    if bucket and amount:
        totals[bucket] += amount


def _record_amounts(record):
    paid = record.paid_amount or Decimal("0")
    fee = record.service_fee or Decimal("0")
    if record.status == "refund":
        return (None, Decimal("0")), (None, Decimal("0"))
    if record.payment_method_2 and record.paid_amount_2:
        amt2 = record.paid_amount_2 or Decimal("0")
        amt1 = paid - amt2 if paid else fee - amt2
        return (record.payment_method, amt1), (record.payment_method_2, amt2)
    if paid <= Decimal("0") and record.refund_entries.filter(status="refund").exists():
        amount = Decimal("0")
    else:
        amount = paid if paid else fee
    return (record.payment_method, amount), (None, Decimal("0"))


def _cards_from_totals(totals):
    cards = []
    for method, meta in PAYMENT_METHOD_META.items():
        cards.append({
            "key": method,
            "label": meta["label"],
            "icon": meta["icon"],
            "gradient": meta["gradient"],
            "accent": meta["accent"],
            "total": totals.get(method, Decimal("0.00")),
        })
    grand_total = sum(totals.values(), Decimal("0.00"))
    return cards, grand_total


def build_daily_payment_cards(records, target_date):
    """DMV registration intake by payment bucket (ServiceRecord only)."""
    totals = {method: Decimal("0.00") for method in PAYMENT_METHOD_META}

    today_records = records.filter(transaction_date=target_date).exclude(status="refund")
    for record in today_records.iterator():
        primary, secondary = _record_amounts(record)
        _add_to_bucket(totals, primary[0], primary[1])
        if secondary[0]:
            _add_to_bucket(totals, secondary[0], secondary[1])

    return _cards_from_totals(totals)


def build_insurance_daily_payment_cards(organization_ids, target_date):
    """Insurance Space daily intake by payment method (DailyPaymentTransaction only)."""
    totals = {method: Decimal("0.00") for method in PAYMENT_METHOD_META}

    daily_txs = DailyPaymentTransaction.objects.filter(
        organization_id__in=organization_ids,
        transaction_date=target_date,
    )
    for tx in daily_txs.iterator():
        if tx.payment_method in totals:
            totals[tx.payment_method] += tx.amount

    return _cards_from_totals(totals)


def build_month_goal_forecast(records, target_date):
    """Month-to-date profit pace and end-of-month projection using transaction_date."""
    month_start = target_date.replace(day=1)
    days_in_month = calendar.monthrange(target_date.year, target_date.month)[1]
    days_elapsed = max(target_date.day, 1)
    days_remaining = max(days_in_month - target_date.day, 0)

    mtd_qs = records.filter(
        transaction_date__gte=month_start,
        transaction_date__lte=target_date,
    )
    mtd_revenue = mtd_qs.aggregate(total=Sum("processing_fee"))["total"] or Decimal("0")
    mtd_records = mtd_qs.count()

    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    prev_month_revenue = (
        records.filter(
            transaction_date__gte=prev_month_start,
            transaction_date__lte=prev_month_end,
        ).aggregate(total=Sum("processing_fee"))["total"]
        or Decimal("0")
    )

    daily_run_rate = mtd_revenue / Decimal(days_elapsed)
    projected_month_end = daily_run_rate * Decimal(days_in_month)
    suggested_goal = (prev_month_revenue * Decimal("1.05")).quantize(Decimal("0.01"))

    if days_remaining > 0:
        required_daily_pace = (suggested_goal - mtd_revenue) / Decimal(days_remaining)
    else:
        required_daily_pace = Decimal("0")

    if suggested_goal > 0:
        pace_pct = (projected_month_end / suggested_goal) * Decimal("100")
        mtd_pct = (mtd_revenue / suggested_goal) * Decimal("100")
    else:
        pace_pct = Decimal("0")
        mtd_pct = Decimal("0")

    if projected_month_end >= suggested_goal:
        status = "on_track"
        status_label = "On Track"
        status_detail = "Current pace projects meeting your profit target."
    elif pace_pct >= Decimal("85"):
        status = "caution"
        status_label = "Close — Push Pace"
        status_detail = "You are within striking distance. Increase daily collections slightly."
    else:
        status = "behind"
        status_label = "Behind Pace"
        status_detail = "Daily run-rate must rise to close the gap before month-end."

    return {
        "month_label": target_date.strftime("%B %Y"),
        "month_key": target_date.strftime("%Y-%m"),
        "days_in_month": days_in_month,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "mtd_revenue": mtd_revenue,
        "mtd_records": mtd_records,
        "prev_month_revenue": prev_month_revenue,
        "suggested_goal": suggested_goal,
        "daily_run_rate": daily_run_rate.quantize(Decimal("0.01")),
        "projected_month_end": projected_month_end.quantize(Decimal("0.01")),
        "required_daily_pace": max(required_daily_pace, Decimal("0")).quantize(Decimal("0.01")),
        "pace_pct": min(pace_pct, Decimal("999")).quantize(Decimal("0.1")),
        "mtd_pct": mtd_pct.quantize(Decimal("0.1")),
        "status": status,
        "status_label": status_label,
        "status_detail": status_detail,
        "gap_to_goal": (suggested_goal - projected_month_end).quantize(Decimal("0.01")),
    }
