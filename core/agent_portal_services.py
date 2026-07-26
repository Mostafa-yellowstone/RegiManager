"""Cairo-aware attendance, task progress, and activity timeline services."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.utils import timezone

from .agent_portal_models import AgentActivityEvent, AgentAttendanceSession, AgentTask
from .models import OrganizationMembership
from .space_access import filter_accessible_spaces

CAIRO_TZ = ZoneInfo("Africa/Cairo")


def cairo_now() -> datetime:
    return timezone.now().astimezone(CAIRO_TZ)


def current_work_date(now: datetime | None = None):
    """
    Work-date for attendance shifts.

    Before 01:00 Cairo, the previous calendar day is still the active shift
    (Monday 09:00 → Monday; Tuesday 00:30 → Monday; Tuesday 01:30 → Tuesday).
    """
    local = (now or cairo_now()).astimezone(CAIRO_TZ)
    if local.hour < 1:
        return (local - timedelta(days=1)).date()
    return local.date()


def shift_close_at(work_date) -> datetime:
    """01:00 Cairo on the calendar day after work_date."""
    close_local = datetime.combine(work_date + timedelta(days=1), time(1, 0), tzinfo=CAIRO_TZ)
    return close_local


def close_stale_attendance_sessions(*, now: datetime | None = None) -> int:
    """Close any open sessions whose 01:00 Cairo deadline has passed."""
    local_now = (now or cairo_now()).astimezone(CAIRO_TZ)
    closed = 0
    open_sessions = AgentAttendanceSession.objects.filter(closed_at__isnull=True).only(
        "id", "work_date", "closed_at"
    )
    for session in open_sessions.iterator():
        deadline = shift_close_at(session.work_date)
        if local_now >= deadline:
            session.closed_at = deadline
            session.save(update_fields=["closed_at", "updated_at"])
            closed += 1
    return closed


def ensure_attendance_open(membership: OrganizationMembership, *, now: datetime | None = None):
    """Open (or reuse) today's attendance session for this membership."""
    close_stale_attendance_sessions(now=now)
    local_now = (now or cairo_now()).astimezone(CAIRO_TZ)
    work_date = current_work_date(local_now)
    session, created = AgentAttendanceSession.objects.get_or_create(
        membership=membership,
        work_date=work_date,
        defaults={
            "organization": membership.organization,
            "opened_at": local_now,
        },
    )
    if not created and session.closed_at is not None and local_now < shift_close_at(work_date):
        # Re-open only if somehow closed early during the same shift window.
        session.closed_at = None
        if session.opened_at is None:
            session.opened_at = local_now
        session.save(update_fields=["closed_at", "opened_at", "updated_at"])
    return session


def task_progress_for_membership(membership: OrganizationMembership) -> dict:
    qs = AgentTask.objects.filter(assigned_to=membership).select_related(
        "created_by", "assigned_to__user"
    )
    totals = qs.aggregate(
        total=Count("id"),
        done=Count("id", filter=Q(is_done=True)),
    )
    total = totals["total"] or 0
    done = totals["done"] or 0
    pct = int(round((done / total) * 100)) if total else 0
    tasks = list(qs.order_by("is_done", "-created_at")[:200])
    return {
        "total": total,
        "done": done,
        "open": max(total - done, 0),
        "percent": pct,
        "tasks": tasks,
        "open_tasks": [t for t in tasks if not t.is_done],
        "done_tasks": [t for t in tasks if t.is_done],
    }


def activity_for_user(
    user,
    organization,
    *,
    start=None,
    end=None,
    limit: int = 80,
    now: datetime | None = None,
):
    """Activity events for an actor; defaults to current Cairo work-date window."""
    qs = AgentActivityEvent.objects.filter(organization=organization, actor=user)
    if start is None and end is None:
        local_now = (now or cairo_now()).astimezone(CAIRO_TZ)
        work_date = current_work_date(local_now)
        start_dt = datetime.combine(work_date, time(0, 0), tzinfo=CAIRO_TZ)
        end_dt = shift_close_at(work_date)
        qs = qs.filter(created_at__gte=start_dt, created_at__lt=end_dt)
    else:
        if start is not None:
            start_dt = datetime.combine(start, time(0, 0), tzinfo=CAIRO_TZ)
            qs = qs.filter(created_at__gte=start_dt)
        if end is not None:
            end_dt = datetime.combine(end + timedelta(days=1), time(0, 0), tzinfo=CAIRO_TZ)
            qs = qs.filter(created_at__lt=end_dt)
    return list(qs.order_by("-created_at")[:limit])


def today_activity_for_user(user, organization, *, now: datetime | None = None):
    """Activity events for the current Cairo work-date window for this actor."""
    return activity_for_user(user, organization, now=now)


def latest_attendance_for_membership(membership: OrganizationMembership):
    return (
        AgentAttendanceSession.objects.filter(membership=membership)
        .order_by("-work_date", "-opened_at")
        .first()
    )


def agent_workboard_payload(membership: OrganizationMembership, *, activity_limit: int = 60):
    """Bundle tasks, progress, attendance, and recent activity for audit/board UIs."""
    progress = task_progress_for_membership(membership)
    activity = activity_for_user(
        membership.user,
        membership.organization,
        start=None,
        end=None,
        limit=activity_limit,
    )
    # Also pull a longer recent trail (last 14 Cairo days) for audit profiles.
    local_now = cairo_now()
    recent_start = (local_now - timedelta(days=14)).date()
    recent_activity = activity_for_user(
        membership.user,
        membership.organization,
        start=recent_start,
        end=local_now.date(),
        limit=activity_limit,
    )
    return {
        "progress": progress,
        "today_activity": activity,
        "recent_activity": recent_activity,
        "attendance": latest_attendance_for_membership(membership),
        "work_date": current_work_date(local_now),
    }


def accessible_space_cards(membership: OrganizationMembership):
    if not membership.can_view_spaces:
        return []
    return list(filter_accessible_spaces(membership, membership.organization).order_by("label", "key"))


def uses_agent_portal_home(membership: OrganizationMembership | None) -> bool:
    """Insurance agents (non-owner) land on the agent portal home."""
    if membership is None:
        return False
    if membership.role == OrganizationMembership.Role.OWNER:
        return False
    return bool(membership.can_deal_with_insurance and membership.is_active)


def can_manage_agent_tasks(membership: OrganizationMembership | None) -> bool:
    if membership is None:
        return False
    if membership.role == OrganizationMembership.Role.OWNER:
        return True
    return bool(membership.can_assign_agent_tasks and membership.is_active)


def log_agent_activity(
    *,
    organization,
    actor,
    domain: str,
    event_type: str,
    title: str,
    detail: str = "",
    object_id: int | None = None,
    membership: OrganizationMembership | None = None,
):
    if actor is None or organization is None:
        return None
    if membership is None and getattr(actor, "pk", None):
        membership = (
            OrganizationMembership.objects.filter(
                organization=organization,
                user=actor,
                is_active=True,
            )
            .order_by("-role")
            .first()
        )
    return AgentActivityEvent.objects.create(
        organization=organization,
        actor=actor,
        membership=membership,
        domain=domain,
        event_type=event_type,
        title=title[:200],
        detail=(detail or "")[:400],
        object_id=object_id,
    )
