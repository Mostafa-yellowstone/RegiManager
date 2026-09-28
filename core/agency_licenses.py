"""Agency license renewal status and portal-wide reminder banners."""

from __future__ import annotations

from datetime import date

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

EVENT_EXPIRING = "agency_license_expiring"
EVENT_EXPIRED = "agency_license_expired"
LICENSE_EVENT_TYPES = (EVENT_EXPIRING, EVENT_EXPIRED)

US_STATES = (
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
    ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"),
    ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
    ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"),
    ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"),
    ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
    ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"),
    ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
    ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"),
    ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"),
    ("WI", "Wisconsin"), ("WY", "Wyoming"), ("DC", "District of Columbia"),
)
US_STATE_NAMES = dict(US_STATES)


def parse_reminder_days(raw) -> tuple[int, ...]:
    """Return unique reminder offsets, tightest first (e.g. 5, 30, 45)."""
    text = str(raw or "45,30,5")
    found = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        days = int(part)
        if 1 <= days <= 365 and days not in found:
            found.append(days)
    if not found:
        found = [45, 30, 5]
    return tuple(sorted(found))


def active_milestone(days_left: int | None, milestones: tuple[int, ...]) -> int | str | None:
    if days_left is None or not milestones:
        return None
    if days_left < 0:
        return "expired"
    for milestone in milestones:
        if days_left <= milestone:
            return milestone
    return None


def license_status(license_obj, *, today: date | None = None) -> dict:
    today = today or timezone.localdate()
    milestones = parse_reminder_days(license_obj.reminder_days)
    expiration = license_obj.expiration_date
    base = {
        "milestones": list(milestones),
        "expiration_date": expiration,
        "title": license_obj.title,
        "license_number": license_obj.license_number or "",
        "milestone": None,
    }
    if not license_obj.is_active:
        return {**base, "state": "archived", "days_left": None, "label": "Archived", "needs_alert": False}
    if not expiration:
        return {
            **base,
            "state": "missing",
            "days_left": None,
            "label": "No expiration date",
            "needs_alert": False,
        }
    days_left = (expiration - today).days
    milestone = active_milestone(days_left, milestones)
    if days_left < 0:
        ago = abs(days_left)
        return {
            **base,
            "state": "expired",
            "days_left": days_left,
            "milestone": "expired",
            "label": f"Expired {ago} day{'s' if ago != 1 else ''} ago",
            "needs_alert": True,
        }
    if milestone is not None:
        label = "Expires today" if days_left == 0 else f"Renew in {days_left} day{'s' if days_left != 1 else ''}"
        return {
            **base,
            "state": "expiring",
            "days_left": days_left,
            "milestone": milestone,
            "label": f"{label} (≤{milestone}-day reminder)",
            "needs_alert": True,
        }
    return {
        **base,
        "state": "ok",
        "days_left": days_left,
        "label": f"Expires in {days_left} days",
        "needs_alert": False,
    }


def _space_url(license_obj) -> str:
    try:
        base = reverse("inventory-detail", kwargs={"inventory_id": license_obj.space_id})
    except Exception:
        return "/dashboard/spaces/"
    return f"{base}?folder={license_obj.folder_id}&license={license_obj.id}"


def sync_agency_license_alerts(license_obj, *, today: date | None = None) -> dict:
    from .models import Notification, OrganizationMembership

    today = today or timezone.localdate()
    status = license_status(license_obj, today=today)
    org = license_obj.organization
    open_qs = Notification.objects.filter(
        organization=org,
        event_type__in=LICENSE_EVENT_TYPES,
        is_read=False,
        message__contains=f"Lic:{license_obj.id}:",
    )
    if not status["needs_alert"] or status["milestone"] is None or not status["expiration_date"]:
        cleared = open_qs.update(is_read=True)
        return {"created": 0, "cleared": cleared}

    milestone = status["milestone"]
    event_type = EVENT_EXPIRED if milestone == "expired" else EVENT_EXPIRING
    token = f"Lic:{license_obj.id}:{status['expiration_date'].isoformat()}:{milestone}"
    title = f"License reminder — {license_obj.title}"
    message = f"{status['label']}. {license_obj.title}. Ref:{token}"
    open_qs.exclude(message__contains=f"Ref:{token}").update(is_read=True)

    recipients = OrganizationMembership.objects.filter(
        organization=org,
        is_active=True,
        role=OrganizationMembership.Role.OWNER,
    ).select_related("user")
    created = 0
    action = _space_url(license_obj)
    for membership in recipients:
        exists = Notification.objects.filter(
            user=membership.user,
            organization=org,
            event_type=event_type,
            message__contains=f"Ref:{token}",
        ).exists()
        if exists:
            continue
        Notification.objects.create(
            user=membership.user,
            organization=org,
            event_type=event_type,
            title=title[:140],
            message=message,
            action_url=action[:400],
            level=Notification.Level.WARNING,
            is_read=False,
        )
        created += 1
    return {"created": created, "cleared": 0}


def attention_rows_for_user(user, *, today: date | None = None) -> list[dict]:
    from .models import AgencyLicense, OrganizationMembership

    if not getattr(user, "is_authenticated", False):
        return []
    today = today or timezone.localdate()
    org_ids = list(
        OrganizationMembership.objects.filter(
            user=user,
            is_active=True,
            role=OrganizationMembership.Role.OWNER,
            organization__is_active=True,
        ).values_list("organization_id", flat=True)
    )
    if not org_ids:
        return []
    cache_key = f"agency_lic_sync:{user.pk}:{today.isoformat()}"
    if not cache.get(cache_key):
        for lic in AgencyLicense.objects.filter(organization_id__in=org_ids, is_active=True).select_related(
            "organization", "folder", "space"
        ):
            try:
                sync_agency_license_alerts(lic, today=today)
            except Exception:
                continue
        cache.set(cache_key, 1, 300)

    rows = []
    for lic in AgencyLicense.objects.filter(organization_id__in=org_ids, is_active=True).select_related(
        "folder", "space", "organization"
    ):
        status = license_status(lic, today=today)
        if status["needs_alert"]:
            rows.append({"license": lic, "status": status, "url": _space_url(lic)})
    rows.sort(key=lambda row: row["status"]["days_left"] if row["status"]["days_left"] is not None else -9999)
    return rows
