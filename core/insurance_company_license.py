"""Insurance company license status and renewal alert helpers."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

if TYPE_CHECKING:
    from .models import InsuranceCompany, Organization

EVENT_EXPIRING = "company_license_expiring"
EVENT_EXPIRED = "company_license_expired"
LICENSE_EVENT_TYPES = (EVENT_EXPIRING, EVENT_EXPIRED)


def clamp_alert_days(value, default: int = 5) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(days, 365))


def company_license_status(company: InsuranceCompany, *, today: date | None = None) -> dict:
    """
    Compute license renewal status for UI and alerts.

    States:
      - missing: no expiration date on file
      - ok: more than alert_days away
      - expiring: within alert window (includes day-of)
      - expired: past expiration
    """
    today = today or timezone.localdate()
    alert_days = clamp_alert_days(getattr(company, "license_alert_days", 5))
    effective = company.license_effective_date
    expiration = company.license_expiration_date

    base = {
        "license_number": (company.license_number or "").strip(),
        "effective_date": effective,
        "expiration_date": expiration,
        "alert_days": alert_days,
        "broker_arrangement": company.broker_arrangement or "",
        "broker_arrangement_label": company.get_broker_arrangement_display()
        if company.broker_arrangement
        else "Not set",
        "takes_broker_fees": company.takes_broker_fees,
    }

    if not expiration:
        incomplete = bool(base["license_number"] or effective)
        return {
            **base,
            "state": "missing",
            "days_left": None,
            "label": "License dates incomplete" if incomplete else "No license expiration on file",
            "tone": "muted",
            "needs_alert": False,
        }

    days_left = (expiration - today).days
    if days_left < 0:
        ago = abs(days_left)
        return {
            **base,
            "state": "expired",
            "days_left": days_left,
            "label": f"License expired {ago} day{'s' if ago != 1 else ''} ago",
            "tone": "danger",
            "needs_alert": True,
        }

    if days_left <= alert_days:
        if days_left == 0:
            label = "License expires today — renew now"
        else:
            label = f"License renews in {days_left} day{'s' if days_left != 1 else ''}"
        return {
            **base,
            "state": "expiring",
            "days_left": days_left,
            "label": label,
            "tone": "warning",
            "needs_alert": True,
        }

    return {
        **base,
        "state": "ok",
        "days_left": days_left,
        "label": f"License OK · {days_left} days left",
        "tone": "success",
        "needs_alert": False,
    }


def _alert_recipients_for_org(organization: Organization):
    from django.contrib.auth import get_user_model

    from .models import OrganizationMembership

    User = get_user_model()
    owner_ids = OrganizationMembership.objects.filter(
        organization=organization,
        is_active=True,
        role=OrganizationMembership.Role.OWNER,
        user__is_active=True,
    ).values_list("user_id", flat=True)
    finance_ids = OrganizationMembership.objects.filter(
        organization=organization,
        is_active=True,
        can_deal_with_insurance=True,
        user__is_active=True,
    ).values_list("user_id", flat=True)
    user_ids = set(owner_ids) | set(finance_ids)
    if not user_ids:
        return []
    return list(User.objects.filter(id__in=user_ids, is_active=True))


def _expiration_token(expiration: date) -> str:
    return expiration.isoformat()


def sync_company_license_alerts(company: InsuranceCompany, *, today: date | None = None) -> dict:
    """
    Create/update/clear license renewal notifications for one company.

    Safe to call repeatedly:
    - No expiration → clear open license alerts
    - OK window → mark open alerts read
    - Expiring/expired → one unread alert per user for current expiration date
    """
    from .models import Notification

    today = today or timezone.localdate()
    status = company_license_status(company, today=today)
    org = company.organization

    open_qs = Notification.objects.filter(
        insurance_company=company,
        event_type__in=LICENSE_EVENT_TYPES,
        is_read=False,
    )

    if not status["needs_alert"] or not status["expiration_date"]:
        cleared = open_qs.update(is_read=True)
        return {"created": 0, "cleared": cleared, "state": status["state"]}

    event_type = EVENT_EXPIRED if status["state"] == "expired" else EVENT_EXPIRING
    token = _expiration_token(status["expiration_date"])
    title = (
        f"License expired — {company.name}"
        if event_type == EVENT_EXPIRED
        else f"License renewal due — {company.name}"
    )
    message = (
        f"{status['label']}. Expiration: {status['expiration_date']:%b %d, %Y}."
        f" Ref:{token}"
    )
    if status["license_number"]:
        message = f"License # {status['license_number']} · {message}"

    # Close alerts for a different expiration or the opposite event type.
    open_qs.exclude(event_type=event_type, message__contains=f"Ref:{token}").update(is_read=True)

    created = 0
    for user in _alert_recipients_for_org(org):
        exists = Notification.objects.filter(
            user=user,
            insurance_company=company,
            event_type=event_type,
            message__contains=f"Ref:{token}",
        ).exists()
        if exists:
            continue
        Notification.objects.create(
            user=user,
            organization=org,
            client=None,
            insurance_company=company,
            event_type=event_type,
            title=title[:140],
            message=message,
            level=Notification.Level.WARNING,
            is_read=False,
        )
        created += 1

    return {"created": created, "cleared": 0, "state": status["state"]}


def sync_org_company_license_alerts(organization: Organization, *, today: date | None = None) -> dict:
    from .models import InsuranceCompany

    today = today or timezone.localdate()
    totals = {"created": 0, "cleared": 0, "companies": 0}
    for company in InsuranceCompany.objects.filter(organization=organization):
        result = sync_company_license_alerts(company, today=today)
        totals["created"] += result["created"]
        totals["cleared"] += result["cleared"]
        totals["companies"] += 1
    return totals


def sync_all_company_license_alerts(*, today: date | None = None) -> dict:
    from .models import Organization

    today = today or timezone.localdate()
    totals = {"created": 0, "cleared": 0, "organizations": 0}
    for org in Organization.objects.all().only("id"):
        result = sync_org_company_license_alerts(org, today=today)
        totals["created"] += result["created"]
        totals["cleared"] += result["cleared"]
        totals["organizations"] += 1
    return totals


def companies_needing_license_attention(organization: Organization, *, today: date | None = None):
    from .models import InsuranceCompany

    today = today or timezone.localdate()
    rows = []
    for company in InsuranceCompany.objects.filter(organization=organization):
        status = company_license_status(company, today=today)
        if status["needs_alert"]:
            rows.append({"company": company, "status": status})
    rows.sort(key=lambda row: (row["status"]["days_left"] is not None, row["status"]["days_left"] or 0))
    return rows
