"""PSB (Organization) license status and renewal alert helpers."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Iterable

from django.utils import timezone

from .insurance_company_license import clamp_alert_days

if TYPE_CHECKING:
    from .models import Organization

EVENT_EXPIRING = "psb_license_expiring"
EVENT_EXPIRED = "psb_license_expired"
LICENSE_EVENT_TYPES = (EVENT_EXPIRING, EVENT_EXPIRED)


def psb_license_status(organization: Organization, *, today: date | None = None) -> dict:
    """
    Compute PSB license renewal status for UI and alerts.

    States: missing | ok | expiring | expired
    """
    today = today or timezone.localdate()
    alert_days = clamp_alert_days(getattr(organization, "psbc_license_alert_days", 5))
    effective = organization.psbc_license_effective_date
    expiration = organization.psbc_license_expiration_date
    license_number = (organization.psbc_license or "").strip()

    base = {
        "license_number": license_number,
        "effective_date": effective,
        "expiration_date": expiration,
        "alert_days": alert_days,
        "organization_name": organization.name,
    }

    if not expiration:
        incomplete = bool(license_number or effective)
        return {
            **base,
            "state": "missing",
            "days_left": None,
            "label": "License dates incomplete" if incomplete else "No PSB license expiration on file",
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
            "label": f"PSB license expired {ago} day{'s' if ago != 1 else ''} ago",
            "tone": "danger",
            "needs_alert": True,
        }

    if days_left <= alert_days:
        if days_left == 0:
            label = "PSB license expires today — renew now"
        else:
            label = f"PSB license renews in {days_left} day{'s' if days_left != 1 else ''}"
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
        "label": f"PSB license OK · {days_left} days left",
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
    if not owner_ids:
        return []
    return list(User.objects.filter(id__in=owner_ids, is_active=True))


def _expiration_token(expiration: date) -> str:
    return expiration.isoformat()


def sync_psb_license_alerts(organization: Organization, *, today: date | None = None) -> dict:
    """
    Create/update/clear PSB license renewal notifications for one organization.

    Safe to call repeatedly. Dedupes by event type + expiration date token.
    """
    from .models import Notification

    today = today or timezone.localdate()
    status = psb_license_status(organization, today=today)

    open_qs = Notification.objects.filter(
        organization=organization,
        insurance_company__isnull=True,
        event_type__in=LICENSE_EVENT_TYPES,
        is_read=False,
    )

    if not status["needs_alert"] or not status["expiration_date"]:
        cleared = open_qs.update(is_read=True)
        return {"created": 0, "cleared": cleared, "state": status["state"]}

    event_type = EVENT_EXPIRED if status["state"] == "expired" else EVENT_EXPIRING
    token = _expiration_token(status["expiration_date"])
    title = (
        f"PSB license expired — {organization.name}"
        if event_type == EVENT_EXPIRED
        else f"PSB license renewal due — {organization.name}"
    )
    message = (
        f"{status['label']}. Expiration: {status['expiration_date']:%b %d, %Y}."
        f" Ref:{token}"
    )
    if status["license_number"]:
        message = f"PSBC No. {status['license_number']} · {message}"

    open_qs.exclude(event_type=event_type, message__contains=f"Ref:{token}").update(is_read=True)

    created = 0
    for user in _alert_recipients_for_org(organization):
        exists = Notification.objects.filter(
            user=user,
            organization=organization,
            insurance_company__isnull=True,
            event_type=event_type,
            message__contains=f"Ref:{token}",
        ).exists()
        if exists:
            continue
        Notification.objects.create(
            user=user,
            organization=organization,
            client=None,
            insurance_company=None,
            event_type=event_type,
            title=title[:140],
            message=message,
            level=Notification.Level.WARNING,
            is_read=False,
        )
        created += 1

    return {"created": created, "cleared": 0, "state": status["state"]}


def organizations_needing_license_attention(
    organizations: Iterable[Organization],
    *,
    today: date | None = None,
) -> list[dict]:
    today = today or timezone.localdate()
    rows = []
    for org in organizations:
        status = psb_license_status(org, today=today)
        if status["needs_alert"]:
            rows.append({"organization": org, "status": status})
    rows.sort(key=lambda row: (row["status"]["days_left"] is not None, row["status"]["days_left"] or 0))
    return rows


def sync_organizations_license_alerts(
    organizations: Iterable[Organization],
    *,
    today: date | None = None,
) -> dict:
    today = today or timezone.localdate()
    totals = {"created": 0, "cleared": 0, "organizations": 0}
    for org in organizations:
        result = sync_psb_license_alerts(org, today=today)
        totals["created"] += result["created"]
        totals["cleared"] += result["cleared"]
        totals["organizations"] += 1
    return totals


def sync_all_psb_license_alerts(*, today: date | None = None) -> dict:
    from .models import Organization

    today = today or timezone.localdate()
    return sync_organizations_license_alerts(
        Organization.objects.filter(is_active=True).only(
            "id",
            "name",
            "psbc_license",
            "psbc_license_effective_date",
            "psbc_license_expiration_date",
            "psbc_license_alert_days",
        ),
        today=today,
    )
