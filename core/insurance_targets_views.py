"""Web endpoints for Insurance Space Targets & Forecast planner."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .access import organizations_for_user
from .http import deny_access
from .insurance_targets_metrics import get_or_init_monthly_target
from .insurance_targets_models import (
    InsuranceLineTarget,
    InsuranceMarketPremiumAssumption,
    InsuranceMonthlyTarget,
)
from .models import OrganizationMembership, Space
from .policies import redirect_back


MAX_TARGET_AMOUNT = Decimal("999999999999.99")
MAX_MARKET_PREMIUM = Decimal("9999999999.99")


def _parse_money(raw, default="0"):
    try:
        value = Decimal(str(raw or default).replace(",", "").replace("$", "").strip() or default)
    except (InvalidOperation, TypeError, ValueError):
        value = Decimal(default)
    if not value.is_finite():
        value = Decimal(default)
    return min(max(value, Decimal("0")), MAX_TARGET_AMOUNT).quantize(Decimal("0.01"))


def _can_edit_targets(membership, is_owner: bool) -> bool:
    if is_owner:
        return True
    if membership is None:
        return False
    return bool(
        getattr(membership, "can_view_banking", False)
        or getattr(membership, "can_view_reports", False)
    )


def _resolve_insurance_org(request):
    organizations = organizations_for_user(request)
    posted_id = (request.POST.get("organization_id") or "").strip()
    if posted_id:
        org = organizations.filter(id=int(posted_id)).first() if posted_id.isdigit() else None
        if org is None:
            deny_access("You do not have access to that PSB.")
    else:
        session_id = request.session.get("active_org_id")
        org = organizations.filter(id=session_id).first() if session_id else None
        org = org or organizations.first()
    if org is None:
        deny_access("No active PSB.")
    membership = (
        OrganizationMembership.objects.filter(
            user=request.user,
            organization=org,
            is_active=True,
        )
        .select_related("organization")
        .first()
    )
    is_owner = bool(
        membership and membership.role == OrganizationMembership.Role.OWNER
    )
    return org, membership, is_owner


def _insurance_space_redirect(org):
    from django.urls import reverse

    return reverse("insurance-targets")


@login_required
@require_POST
def save_insurance_monthly_target(request):
    org, membership, is_owner = _resolve_insurance_org(request)
    if not _can_edit_targets(membership, is_owner):
        deny_access("You do not have permission to edit insurance targets.")

    try:
        year = int(request.POST.get("year") or 0)
        month = int(request.POST.get("month") or 0)
    except (TypeError, ValueError):
        year, month = 0, 0
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        messages.error(request, "Invalid target month.")
        return redirect(_insurance_space_redirect(org))

    monthly = get_or_init_monthly_target(org, year, month)
    monthly.premium_target = _parse_money(request.POST.get("premium_target"))
    monthly.commission_target = _parse_money(request.POST.get("commission_target"))
    monthly.notes = (request.POST.get("notes") or "").strip()[:2000]
    monthly.save()

    # Optional bulk line targets: line_premium_<type>, line_commission_<type>
    for key, value in request.POST.items():
        if not key.startswith("line_premium_"):
            continue
        itype = key[len("line_premium_") :]
        if not itype or len(itype) > InsuranceLineTarget._meta.get_field("insurance_type").max_length:
            continue
        lt, _ = InsuranceLineTarget.objects.get_or_create(
            monthly_target=monthly,
            insurance_type=itype,
            defaults={"premium_target": Decimal("0"), "commission_target": Decimal("0")},
        )
        lt.premium_target = _parse_money(value)
        lt.commission_target = _parse_money(
            request.POST.get(f"line_commission_{itype}"),
            default=str(lt.commission_target),
        )
        # Checkbox only posts when checked.
        lt.is_active = request.POST.get(f"line_active_{itype}") in {
            "1",
            "true",
            "on",
            "yes",
        }
        market_raw = request.POST.get(f"line_market_{itype}")
        if market_raw is not None and str(market_raw).strip() != "":
            lt.market_avg_premium = min(_parse_money(market_raw), MAX_MARKET_PREMIUM)
        elif market_raw is not None and str(market_raw).strip() == "":
            lt.market_avg_premium = None
        lt.save()

    messages.success(request, "Monthly insurance targets saved.")
    return redirect_back(request, _insurance_space_redirect(org))


@login_required
@require_POST
def save_insurance_line_target(request):
    org, membership, is_owner = _resolve_insurance_org(request)
    if not _can_edit_targets(membership, is_owner):
        deny_access("You do not have permission to edit insurance targets.")

    line_id = request.POST.get("line_target_id")
    lt = get_object_or_404(
        InsuranceLineTarget.objects.select_related("monthly_target"),
        id=line_id,
        monthly_target__organization=org,
    )
    lt.premium_target = _parse_money(request.POST.get("premium_target"))
    lt.commission_target = _parse_money(request.POST.get("commission_target"))
    market_raw = request.POST.get("market_avg_premium")
    if market_raw is not None and str(market_raw).strip() != "":
        lt.market_avg_premium = min(_parse_money(market_raw), MAX_MARKET_PREMIUM)
    elif request.POST.get("clear_market") in {"1", "true", "on"}:
        lt.market_avg_premium = None
    if "is_active" in request.POST:
        lt.is_active = request.POST.get("is_active") in {"1", "true", "on", "yes"}
    lt.save()
    messages.success(request, f"Updated {lt.insurance_type.replace('_', ' ')} target.")
    return redirect_back(request, _insurance_space_redirect(org))


@login_required
@require_POST
def save_insurance_market_assumption(request):
    org, membership, is_owner = _resolve_insurance_org(request)
    if not _can_edit_targets(membership, is_owner):
        deny_access("You do not have permission to edit market assumptions.")

    itype = (request.POST.get("insurance_type") or "").strip()
    if not itype:
        messages.error(request, "Insurance type is required.")
        return redirect(_insurance_space_redirect(org))

    avg = min(_parse_money(request.POST.get("avg_premium")), MAX_MARKET_PREMIUM)
    obj, _ = InsuranceMarketPremiumAssumption.objects.update_or_create(
        organization=org,
        insurance_type=itype,
        defaults={"avg_premium": avg},
    )
    messages.success(
        request,
        f"Market premium for {itype.replace('_', ' ')} set to ${obj.avg_premium}.",
    )
    return redirect_back(request, _insurance_space_redirect(org))
