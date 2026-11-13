"""Expense watch: alert owners about large expenses and categories running ahead of last month."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from .expense_models import Expense, ExpenseWatchSettings
from .models import BankTransaction, Notification
from .owner_notifications import notify_owners_expense_alert

SEGMENT_LABELS = {"dmv": "DMV expense", "insurance": "Insurance bank expense"}
# Older entries are bookkeeping catch-up; alerting on them would be noise.
MAX_ALERT_AGE_DAYS = 31


def watch_settings_for(organization) -> ExpenseWatchSettings:
    settings_row, _created = ExpenseWatchSettings.objects.get_or_create(organization=organization)
    return settings_row


def is_bank_expense(tx: BankTransaction) -> bool:
    tx_type = str(tx.transaction_type or "")
    return "expense" in tx_type or tx_type in {str(t) for t in BankTransaction.expense_metric_types()}


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return value


def _month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


def _previous_month_bounds(day: date) -> tuple[date, date]:
    this_start, _ = _month_bounds(day)
    return _month_bounds(this_start - timedelta(days=1))


def _bank_expense_qs(organization):
    return BankTransaction.objects.filter(bank_account__organization=organization).filter(
        Q(transaction_type__icontains="expense")
        | Q(transaction_type__in=list(BankTransaction.expense_metric_types()))
    )


def category_total(organization, segment: str, category: str, start: date, end: date) -> Decimal:
    if segment == "dmv":
        qs = Expense.objects.filter(
            organization=organization,
            label__name=category,
            expense_date__gte=start,
            expense_date__lte=end,
        )
    else:
        qs = _bank_expense_qs(organization).filter(
            category=category,
            date__gte=start,
            date__lte=end,
        )
    return qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")


def category_watch_rows(organization, *, today: date | None = None) -> list[dict]:
    """This month vs last month per category, both segments; rows past the threshold are flagged."""
    today = today or timezone.localdate()
    settings_row = watch_settings_for(organization)
    month_start, month_end = _month_bounds(today)
    prev_start, prev_end = _previous_month_bounds(today)

    def totals(segment, start, end):
        if segment == "dmv":
            rows = (
                Expense.objects.filter(organization=organization, expense_date__gte=start, expense_date__lte=end)
                .values("label__name")
                .annotate(total=Sum("amount"))
            )
            return {row["label__name"] or "Expense": row["total"] or Decimal("0") for row in rows}
        rows = (
            _bank_expense_qs(organization)
            .filter(date__gte=start, date__lte=end)
            .values("category")
            .annotate(total=Sum("amount"))
        )
        out: dict[str, Decimal] = {}
        for row in rows:
            key = row["category"] or "Expense"
            out[key] = out.get(key, Decimal("0")) + (row["total"] or Decimal("0"))
        return out

    threshold = Decimal(settings_row.category_jump_percent)
    result = []
    for segment in ("dmv", "insurance"):
        current = totals(segment, month_start, month_end)
        previous = totals(segment, prev_start, prev_end)
        for category in set(current) | set(previous):
            this_month = current.get(category, Decimal("0"))
            last_month = previous.get(category, Decimal("0"))
            change_pct = None
            if last_month > 0:
                change_pct = ((this_month - last_month) / last_month * 100).quantize(Decimal("0.1"))
            over = bool(
                settings_row.enabled
                and threshold > 0
                and change_pct is not None
                and change_pct > threshold
            )
            result.append(
                {
                    "segment": segment,
                    "category": category,
                    "this_month": str(this_month.quantize(Decimal("0.01"))),
                    "last_month": str(last_month.quantize(Decimal("0.01"))),
                    "change_pct": str(change_pct) if change_pct is not None else None,
                    "over": over,
                }
            )
    result.sort(key=lambda row: (not row["over"], -Decimal(row["this_month"])))
    return result


def _already_alerted(organization, watch_key: str) -> bool:
    return Notification.objects.filter(
        organization=organization,
        event_type="expense_alert",
        data__watch_key=watch_key,
    ).exists()


def check_new_expense(
    organization,
    *,
    segment: str,
    category: str,
    amount,
    expense_date,
    description: str = "",
) -> list[str]:
    """Run both watch rules for one new expense. Returns the alert kinds sent."""
    settings_row = watch_settings_for(organization)
    if not settings_row.enabled:
        return []
    spent_on = _as_date(expense_date) or timezone.localdate()
    if (timezone.localdate() - spent_on).days > MAX_ALERT_AGE_DAYS:
        return []

    amount = Decimal(amount or 0).quantize(Decimal("0.01"))
    category = category or "Expense"
    segment_label = SEGMENT_LABELS.get(segment, "Expense")
    sent: list[str] = []

    limit = settings_row.single_expense_limit or Decimal("0")
    if limit > 0 and amount >= limit:
        notify_owners_expense_alert(
            organization,
            title="Large expense",
            message=f"{segment_label}: {category} ${amount:,.2f} on {spent_on.isoformat()}.",
            push_title=f"Large expense · ${amount:,.2f}",
            push_body=f"{segment_label} · {category}" + (f"\n{description}" if description else ""),
            data={
                "kind": "expense",
                "segment": segment,
                "client": category,
                "subtitle": f"{segment_label} · {spent_on.isoformat()}",
                "headline": {"label": "Expense", "amount": str(amount)},
                "lines": [
                    {"label": "Your alert limit", "amount": str(limit)},
                ],
                "note": description[:200],
            },
        )
        sent.append("large")

    pct = settings_row.category_jump_percent or 0
    if pct > 0:
        month_start, month_end = _month_bounds(spent_on)
        prev_start, prev_end = _previous_month_bounds(spent_on)
        this_month = category_total(organization, segment, category, month_start, month_end)
        last_month = category_total(organization, segment, category, prev_start, prev_end)
        watch_key = f"{segment}:{category}:{month_start:%Y-%m}"
        if last_month > 0 and this_month > last_month * (1 + Decimal(pct) / 100):
            if not _already_alerted(organization, watch_key):
                change = ((this_month - last_month) / last_month * 100).quantize(Decimal("1"))
                notify_owners_expense_alert(
                    organization,
                    title="Category over last month",
                    message=(
                        f"{segment_label}: {category} is at ${this_month:,.2f} this month, "
                        f"{change}% above last month (${last_month:,.2f})."
                    ),
                    push_title=f"{category} is up {change}% vs last month",
                    push_body=f"{segment_label} · ${this_month:,.2f} so far vs ${last_month:,.2f} last month",
                    data={
                        "kind": "expense",
                        "segment": segment,
                        "watch_key": watch_key,
                        "client": category,
                        "subtitle": f"{segment_label} · {month_start:%B %Y}",
                        "headline": {"label": f"Up {change}%", "amount": str(this_month - last_month)},
                        "lines": [
                            {"label": "This month so far", "amount": str(this_month.quantize(Decimal('0.01')))},
                            {"label": "All of last month", "amount": str(last_month.quantize(Decimal('0.01')))},
                        ],
                    },
                )
                sent.append("category")
    return sent
