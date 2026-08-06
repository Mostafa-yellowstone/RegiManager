"""Targets, pace forecast, and deterministic planner for Insurance Space."""

from __future__ import annotations

import calendar
import math
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Avg, Count, Sum

from .insurance_space_metrics import filter_policies_by_quote_period
from .insurance_targets_models import (
    InsuranceLineTarget,
    InsuranceMarketPremiumAssumption,
    InsuranceMonthlyTarget,
)
from .models import InsurancePolicy

ZERO = Decimal("0.00")
Q2 = Decimal("0.01")
Q1 = Decimal("0.1")


def _d(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _q(value, places=Q2) -> Decimal:
    return _d(value).quantize(places, rounding=ROUND_HALF_UP)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def resolve_target_month(raw: str = "", *, today: date | None = None) -> tuple[int, int]:
    today = today or date.today()
    raw = (raw or "").strip()
    if raw:
        try:
            parsed = date.fromisoformat(f"{raw}-01") if len(raw) == 7 else date.fromisoformat(raw)
            return parsed.year, parsed.month
        except ValueError:
            pass
    return today.year, today.month


def insurance_type_catalog(organization) -> list[dict]:
    from .models import InsurancePolicy, InsuranceTypeOption

    built_in = [
        {"key": key, "label": label}
        for key, label in InsurancePolicy.INSURANCE_TYPE_CHOICES
    ]
    extra = list(
        InsuranceTypeOption.objects.filter(organization=organization)
        .order_by("label")
        .values("key", "label")
    )
    seen = {item["key"] for item in built_in}
    for item in extra:
        if item["key"] not in seen:
            built_in.append(item)
            seen.add(item["key"])
    return built_in


def label_for_type(organization, key: str) -> str:
    if not key:
        return "Unspecified"
    for item in insurance_type_catalog(organization):
        if item["key"] == key:
            return item["label"]
    return key.replace("_", " ").title()


def bound_policies_in_month(policy_qs, year: int, month: int):
    start, end = month_bounds(year, month)
    return policy_qs.filter(
        stage__in=InsurancePolicy.BOUND_STAGES,
        bound_date__gte=start,
        bound_date__lte=end,
    )


def historical_avg_premium_map(policy_qs, *, as_of: date, lookback_days: int = 90) -> dict[str, Decimal]:
    start = as_of - timedelta(days=lookback_days)
    rows = (
        policy_qs.filter(
            stage__in=InsurancePolicy.BOUND_STAGES,
            bound_date__gte=start,
            bound_date__lte=as_of,
        )
        .exclude(insurance_type="")
        .values("insurance_type")
        .annotate(avg_premium=Avg("premium"), n=Count("id"))
    )
    return {
        row["insurance_type"]: _q(row["avg_premium"] or ZERO)
        for row in rows
        if row["n"]
    }


def historical_avg_commission_rate_map(policy_qs, *, as_of: date, lookback_days: int = 90) -> dict[str, Decimal]:
    start = as_of - timedelta(days=lookback_days)
    rows = (
        policy_qs.filter(
            stage__in=InsurancePolicy.BOUND_STAGES,
            bound_date__gte=start,
            bound_date__lte=as_of,
            premium__gt=0,
        )
        .exclude(insurance_type="")
        .values("insurance_type")
        .annotate(
            premium=Sum("premium"),
            commission=Sum("commission_amount"),
        )
    )
    out = {}
    for row in rows:
        prem = _d(row["premium"])
        if prem <= 0:
            continue
        out[row["insurance_type"]] = (_d(row["commission"]) / prem).quantize(
            Decimal("0.0001")
        )
    return out


def actuals_by_line(policy_qs, year: int, month: int) -> dict[str, dict]:
    start, end = month_bounds(year, month)
    period_qs = filter_policies_by_quote_period(policy_qs, start, end)
    bound_qs = bound_policies_in_month(policy_qs, year, month)

    quote_rows = (
        period_qs.filter(stage__in=InsurancePolicy.QUOTE_STAGES)
        .values("insurance_type")
        .annotate(quotes=Count("id"))
    )
    bound_rows = bound_qs.values("insurance_type").annotate(
        binds=Count("id"),
        premium=Sum("premium"),
        commission=Sum("commission_amount"),
        broker_fee=Sum("broker_fee"),
    )

    by_type: dict[str, dict] = {}
    for row in quote_rows:
        key = row["insurance_type"] or ""
        by_type.setdefault(
            key,
            {
                "insurance_type": key,
                "quotes": 0,
                "binds": 0,
                "premium": ZERO,
                "commission": ZERO,
                "broker_fee": ZERO,
            },
        )
        by_type[key]["quotes"] = row["quotes"] or 0

    for row in bound_rows:
        key = row["insurance_type"] or ""
        bucket = by_type.setdefault(
            key,
            {
                "insurance_type": key,
                "quotes": 0,
                "binds": 0,
                "premium": ZERO,
                "commission": ZERO,
                "broker_fee": ZERO,
            },
        )
        bucket["binds"] = row["binds"] or 0
        bucket["premium"] = _q(row["premium"])
        bucket["commission"] = _q(row["commission"])
        bucket["broker_fee"] = _q(row["broker_fee"])

    for bucket in by_type.values():
        total = bucket["quotes"] + bucket["binds"]
        bucket["conversion"] = (
            round(bucket["binds"] / total * 100, 1) if total else 0.0
        )
    return by_type


def get_or_init_monthly_target(organization, year: int, month: int) -> InsuranceMonthlyTarget:
    target, _ = InsuranceMonthlyTarget.objects.get_or_create(
        organization=organization,
        year=year,
        month=month,
        defaults={"premium_target": ZERO, "commission_target": ZERO},
    )
    return target


def ensure_line_targets(monthly: InsuranceMonthlyTarget, type_keys: list[str]) -> list[InsuranceLineTarget]:
    existing = {
        lt.insurance_type: lt
        for lt in monthly.line_targets.all()
    }
    created = []
    for key in type_keys:
        if key in existing:
            continue
        created.append(
            InsuranceLineTarget(
                monthly_target=monthly,
                insurance_type=key,
                premium_target=ZERO,
                commission_target=ZERO,
                is_active=True,
            )
        )
    if created:
        InsuranceLineTarget.objects.bulk_create(created, ignore_conflicts=True)
    return list(monthly.line_targets.order_by("insurance_type"))


def pace_for_metric(
    *,
    mtd: Decimal,
    target: Decimal,
    days_elapsed: int,
    days_in_month: int,
    days_remaining: int,
) -> dict:
    days_elapsed = max(days_elapsed, 1)
    daily_run_rate = mtd / Decimal(days_elapsed)
    projected = daily_run_rate * Decimal(days_in_month)
    if days_remaining > 0:
        required = (target - mtd) / Decimal(days_remaining)
    else:
        required = ZERO
    if target > 0:
        pace_pct = (projected / target) * Decimal("100")
        mtd_pct = (mtd / target) * Decimal("100")
    else:
        pace_pct = ZERO
        mtd_pct = ZERO

    if target <= 0:
        status, label, detail = (
            "unset",
            "Set a target",
            "Dial in this month’s premium goal and we’ll coach the pace.",
        )
    elif projected >= target:
        status, label, detail = (
            "on_track",
            "On track",
            "Current bind pace projects hitting the premium target. Keep the champagne on ice—not the hustle.",
        )
    elif pace_pct >= Decimal("85"):
        status, label, detail = (
            "caution",
            "Close — push pace",
            "You’re within striking distance. A few more quality binds close the gap.",
        )
    else:
        status, label, detail = (
            "behind",
            "Behind pace",
            "Daily run-rate needs a glow-up before month-end. See the planner playbook below.",
        )

    return {
        "mtd": _q(mtd),
        "target": _q(target),
        "gap": _q(target - mtd),
        "projected_month_end": _q(projected),
        "daily_run_rate": _q(daily_run_rate),
        "required_daily_pace": _q(max(required, ZERO)),
        "pace_pct": _q(min(pace_pct, Decimal("999")), Q1),
        "mtd_pct": _q(mtd_pct, Q1),
        "status": status,
        "status_label": label,
        "status_detail": detail,
    }


def planner_recommendations(
    *,
    organization,
    line_cards: list[dict],
    premium_gap: Decimal,
) -> dict:
    ranked = sorted(
        [c for c in line_cards if c["premium_gap"] > 0 and c["is_active"]],
        key=lambda c: c["premium_gap"],
        reverse=True,
    )
    plays = []
    remaining = premium_gap
    mix_parts = []
    est_commission = ZERO

    witty = [
        "Feed the beast with {n} more {label} binds (~${prem:,.0f} each).",
        "Queue {n} {label} wins — market ticket ~${prem:,.0f}.",
        "Close {n} {label} policies to shave this gap (avg ${prem:,.0f}).",
    ]

    for idx, card in enumerate(ranked[:8]):
        assumed = _d(card["assumed_premium"])
        if assumed <= 0:
            continue
        gap = _d(card["premium_gap"])
        need = max(int(math.ceil(float(gap / assumed))), 1)
        # Cap suggestion so one LOB doesn’t invent 500 policies
        need = min(need, 50)
        contrib = _q(Decimal(need) * assumed)
        rate = _d(card.get("avg_commission_rate") or ZERO)
        est_commission += _q(contrib * rate)
        mix_parts.append(f"{need}× {card['label']}")
        plays.append(
            {
                "insurance_type": card["insurance_type"],
                "label": card["label"],
                "binds_needed": need,
                "assumed_premium": _q(assumed),
                "premium_impact": contrib,
                "estimated_commission": _q(contrib * rate),
                "message": witty[idx % len(witty)].format(
                    n=need, label=card["label"], prem=float(assumed)
                ),
                "rank": idx + 1,
            }
        )
        remaining -= contrib
        if remaining <= 0:
            break

    headline = (
        "You’re already crushing the month — protect the lead and bank the commission."
        if premium_gap <= 0
        else (
            "Hit the month by stacking: " + " + ".join(mix_parts[:5]) + "."
            if mix_parts
            else "Set market premiums or write a few binds so the planner can coach smarter."
        )
    )

    return {
        "headline": headline,
        "plays": plays,
        "estimated_commission_from_plays": _q(est_commission),
        "remaining_gap_after_plays": _q(max(remaining, ZERO)),
    }


def six_month_trends(policy_qs, *, end_year: int, end_month: int) -> list[dict]:
    points = []
    y, m = end_year, end_month
    for _ in range(6):
        bound = bound_policies_in_month(policy_qs, y, m)
        agg = bound.aggregate(
            premium=Sum("premium"),
            commission=Sum("commission_amount"),
            binds=Count("id"),
        )
        by_lob = []
        for row in (
            bound.exclude(insurance_type="")
            .values("insurance_type")
            .annotate(
                premium=Sum("premium"),
                commission=Sum("commission_amount"),
                binds=Count("id"),
            )
            .order_by("insurance_type")
        ):
            by_lob.append(
                {
                    "insurance_type": row["insurance_type"],
                    "premium": _q(row["premium"]),
                    "commission": _q(row["commission"]),
                    "binds": row["binds"] or 0,
                }
            )
        points.append(
            {
                "year": y,
                "month": m,
                "label": date(y, m, 1).strftime("%b %Y"),
                "premium": _q(agg["premium"]),
                "commission": _q(agg["commission"]),
                "binds": agg["binds"] or 0,
                "by_lob": by_lob,
            }
        )
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    points.reverse()
    return points


def build_insurance_targets_dashboard(
    organization,
    policy_qs,
    *,
    year: int,
    month: int,
    today: date | None = None,
    type_options: list[dict] | None = None,
) -> dict:
    today = today or date.today()
    type_options = type_options or insurance_type_catalog(organization)
    type_keys = [t["key"] for t in type_options]
    labels = {t["key"]: t["label"] for t in type_options}

    monthly = get_or_init_monthly_target(organization, year, month)
    line_targets = ensure_line_targets(monthly, type_keys)
    line_map = {lt.insurance_type: lt for lt in line_targets}

    assumptions = {
        a.insurance_type: a.avg_premium
        for a in InsuranceMarketPremiumAssumption.objects.filter(
            organization=organization
        )
    }
    hist_prem = historical_avg_premium_map(policy_qs, as_of=today)
    hist_rate = historical_avg_commission_rate_map(policy_qs, as_of=today)
    actuals = actuals_by_line(policy_qs, year, month)

    start, end = month_bounds(year, month)
    if today.year == year and today.month == month:
        days_elapsed = today.day
        as_of = today
    elif (today.year, today.month) > (year, month):
        days_elapsed = end.day
        as_of = end
    else:
        days_elapsed = 1
        as_of = start
    days_in_month = end.day
    days_remaining = max(days_in_month - days_elapsed, 0)

    # Include types that have actuals even if not in catalog
    all_keys = list(dict.fromkeys(type_keys + [k for k in actuals if k]))

    line_cards = []
    total_premium_actual = ZERO
    total_commission_actual = ZERO
    total_binds = 0
    total_quotes = 0

    for key in all_keys:
        lt = line_map.get(key)
        act = actuals.get(
            key,
            {
                "quotes": 0,
                "binds": 0,
                "premium": ZERO,
                "commission": ZERO,
                "broker_fee": ZERO,
                "conversion": 0.0,
            },
        )
        prem_target = _d(lt.premium_target) if lt else ZERO
        comm_target = _d(lt.commission_target) if lt else ZERO
        assumed = None
        if lt and lt.market_avg_premium:
            assumed = _d(lt.market_avg_premium)
        elif key in assumptions:
            assumed = _d(assumptions[key])
        elif key in hist_prem:
            assumed = hist_prem[key]
        else:
            assumed = ZERO

        prem_actual = _d(act["premium"])
        comm_actual = _d(act["commission"])
        total_premium_actual += prem_actual
        total_commission_actual += comm_actual
        total_binds += act["binds"]
        total_quotes += act["quotes"]

        prem_gap = prem_target - prem_actual
        binds_needed = 0
        if prem_gap > 0 and assumed > 0:
            binds_needed = min(int(math.ceil(float(prem_gap / assumed))), 50)

        is_active = lt.is_active if lt else bool(key in type_keys or act["binds"] or act["quotes"])
        progress = (
            float((prem_actual / prem_target) * 100) if prem_target > 0 else 0.0
        )

        line_cards.append(
            {
                "insurance_type": key,
                "label": labels.get(key) or (key.replace("_", " ").title() if key else "Unspecified"),
                "is_active": is_active,
                "premium_target": _q(prem_target),
                "commission_target": _q(comm_target),
                "premium_actual": _q(prem_actual),
                "commission_actual": _q(comm_actual),
                "premium_gap": _q(prem_gap),
                "commission_gap": _q(comm_target - comm_actual),
                "quotes": act["quotes"],
                "binds": act["binds"],
                "conversion": act.get("conversion", 0.0),
                "assumed_premium": _q(assumed),
                "market_avg_premium": _q(lt.market_avg_premium) if lt and lt.market_avg_premium else None,
                "org_assumption": _q(assumptions[key]) if key in assumptions else None,
                "historical_avg_premium": hist_prem.get(key),
                "avg_commission_rate": hist_rate.get(key, ZERO),
                "binds_needed": binds_needed,
                "progress_pct": round(min(progress, 999.0), 1),
                "line_target_id": lt.id if lt else None,
            }
        )

    # Prefer catalog order, then extras
    order = {k: i for i, k in enumerate(type_keys)}
    line_cards.sort(key=lambda c: (order.get(c["insurance_type"], 999), c["label"]))

    premium_pace = pace_for_metric(
        mtd=total_premium_actual,
        target=_d(monthly.premium_target),
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        days_remaining=days_remaining,
    )
    commission_pace = pace_for_metric(
        mtd=total_commission_actual,
        target=_d(monthly.commission_target),
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        days_remaining=days_remaining,
    )

    planner = planner_recommendations(
        organization=organization,
        line_cards=line_cards,
        premium_gap=_d(premium_pace["gap"]),
    )
    trends = six_month_trends(policy_qs, end_year=year, end_month=month)

    insights = []
    if premium_pace["status"] == "behind":
        insights.append(
            f"Premium pace is {premium_pace['pace_pct']}% of target — need "
            f"${premium_pace['required_daily_pace']}/day to catch up."
        )
    elif premium_pace["status"] == "on_track":
        insights.append(
            f"Premium projection ${premium_pace['projected_month_end']} vs target "
            f"${premium_pace['target']} — looking sharp."
        )
    top_gap = next((c for c in sorted(line_cards, key=lambda x: x["premium_gap"], reverse=True) if c["premium_gap"] > 0), None)
    if top_gap:
        insights.append(
            f"Biggest gap: {top_gap['label']} short ${top_gap['premium_gap']} "
            f"(~{top_gap['binds_needed']} binds at ${top_gap['assumed_premium']})."
        )
    if total_binds + total_quotes > 0:
        conv = round(total_binds / (total_binds + total_quotes) * 100, 1)
        insights.append(f"Month conversion so far: {conv}% ({total_binds} bound / {total_binds + total_quotes} touched).")

    return {
        "year": year,
        "month": month,
        "month_label": date(year, month, 1).strftime("%B %Y"),
        "month_key": f"{year:04d}-{month:02d}",
        "as_of": as_of.isoformat(),
        "days_in_month": days_in_month,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "monthly_target": {
            "id": monthly.id,
            "premium_target": _q(monthly.premium_target),
            "commission_target": _q(monthly.commission_target),
            "notes": monthly.notes or "",
        },
        "totals": {
            "premium_actual": _q(total_premium_actual),
            "commission_actual": _q(total_commission_actual),
            "binds": total_binds,
            "quotes": total_quotes,
        },
        "premium_pace": premium_pace,
        "commission_pace": commission_pace,
        "line_cards": line_cards,
        "planner": planner,
        "trends": trends,
        "insights": insights,
        "type_options": type_options,
        "market_assumptions": [
            {
                "insurance_type": key,
                "label": labels.get(key, key),
                "avg_premium": _q(val),
            }
            for key, val in sorted(assumptions.items())
        ],
    }


def serialize_targets_dashboard(dashboard: dict) -> dict:
    """JSON-safe copy for APIs (Decimals → strings)."""

    def conv(obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, dict):
            return {k: conv(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [conv(v) for v in obj]
        return obj

    return conv(dashboard)
