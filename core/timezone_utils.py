"""Timezone helpers for portal display and per-request activation."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings

from .us_states import US_STATE_CODES, normalize_state_code

DEFAULT_PORTAL_TIMEZONE = "America/New_York"

EASTERN_STATES = frozenset(
    {
        "CT",
        "DC",
        "DE",
        "FL",
        "GA",
        "IN",
        "KY",
        "MA",
        "MD",
        "ME",
        "MI",
        "NC",
        "NH",
        "NJ",
        "NY",
        "OH",
        "PA",
        "RI",
        "SC",
        "VT",
        "VA",
        "WV",
    }
)
CENTRAL_STATES = frozenset(
    {
        "AL",
        "AR",
        "IA",
        "IL",
        "KS",
        "LA",
        "MN",
        "MO",
        "MS",
        "ND",
        "NE",
        "OK",
        "SD",
        "TN",
        "TX",
        "WI",
    }
)
MOUNTAIN_STATES = frozenset({"CO", "ID", "MT", "NM", "UT", "WY"})
PACIFIC_STATES = frozenset({"CA", "NV", "OR", "WA"})


def is_valid_timezone(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    name = name.strip()
    if not name or len(name) > 64:
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, KeyError, ValueError, OSError):
        return False


def state_to_timezone_name(state_code: str) -> str:
    code = normalize_state_code(state_code)
    if code == "AK":
        return "America/Anchorage"
    if code == "HI":
        return "Pacific/Honolulu"
    if code == "AZ":
        return "America/Phoenix"
    if code in PACIFIC_STATES:
        return "America/Los_Angeles"
    if code in MOUNTAIN_STATES:
        return "America/Denver"
    if code in CENTRAL_STATES:
        return "America/Chicago"
    if code in EASTERN_STATES:
        return "America/New_York"
    if code in US_STATE_CODES:
        return DEFAULT_PORTAL_TIMEZONE
    return settings.TIME_ZONE


def timezone_for_organization(organization) -> ZoneInfo:
    state = getattr(organization, "state", None) if organization else None
    return ZoneInfo(state_to_timezone_name(state))


def resolve_portal_timezone_name(
    *,
    session_timezone: str | None = None,
    organization=None,
) -> str:
    if session_timezone and is_valid_timezone(session_timezone):
        return session_timezone.strip()
    if organization is not None:
        return state_to_timezone_name(getattr(organization, "state", None))
    return settings.TIME_ZONE


def active_timezone_name() -> str:
    """Timezone active for this request (browser zone, else org state, else default)."""
    from django.utils import timezone

    name = timezone.get_current_timezone_name()
    return name if is_valid_timezone(name) else settings.TIME_ZONE


def local_label(value, fmt: str = "%b %d, %H:%M") -> str:
    """Format a stored (UTC) datetime in the zone active for this request."""
    from django.utils import timezone

    if not value:
        return ""
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_default_timezone())
    return timezone.localtime(value).strftime(fmt)


def zone_abbreviation(local_dt) -> str:
    """EST/EDT, EET/EEST…; numeric offsets such as +03 become UTC+03."""
    label = local_dt.strftime("%Z") or ""
    if label[:1] in {"+", "-"}:
        return f"UTC{label}"
    return label


def timezone_label(tz_name: str) -> str:
    """Short label such as EST/EDT or America/New_York."""
    from django.utils import timezone

    if not is_valid_timezone(tz_name):
        return tz_name
    try:
        with timezone.override(ZoneInfo(tz_name)):
            return timezone.localtime(timezone.now()).strftime("%Z")
    except Exception:
        return tz_name.replace("_", " ")
