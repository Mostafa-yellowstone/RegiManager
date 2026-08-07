"""New York–aware attendance, task progress, and activity timeline services."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.utils import timezone

from .agent_portal_models import AgentActivityEvent, AgentAttendanceSession, AgentTask
from .models import Organization, OrganizationMembership
from .space_access import filter_accessible_spaces

# Business clock for agent attendance / portal shifts (USA — New York).
PORTAL_TZ = ZoneInfo("America/New_York")
# Backward-compatible alias used by older imports/tests.
CAIRO_TZ = PORTAL_TZ


def portal_now() -> datetime:
    return timezone.now().astimezone(PORTAL_TZ)


def cairo_now() -> datetime:
    """Legacy name — returns America/New_York local time."""
    return portal_now()


# Standard agent shift in America/New_York (wall clock).
SHIFT_OPEN_HOUR = 9   # 9:00 AM
SHIFT_CLOSE_HOUR = 18  # 6:00 PM


def current_work_date(now: datetime | None = None):
    """
    Work-date for attendance shifts = America/New_York calendar date.

    Shifts run 09:00–18:00 New York on that same date.
    """
    local = (now or portal_now()).astimezone(PORTAL_TZ)
    return local.date()


def shift_open_at(work_date) -> datetime:
    """09:00 (9 AM) America/New_York on work_date."""
    return datetime.combine(work_date, time(SHIFT_OPEN_HOUR, 0), tzinfo=PORTAL_TZ)


def shift_close_at(work_date) -> datetime:
    """18:00 (6 PM) America/New_York on work_date."""
    return datetime.combine(work_date, time(SHIFT_CLOSE_HOUR, 0), tzinfo=PORTAL_TZ)


def format_ny_time(dt: datetime | None) -> str:
    """Always render a datetime as New York wall-clock (e.g. '9:05 AM')."""
    if dt is None:
        return "—"
    local = dt.astimezone(PORTAL_TZ)
    hour12 = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{hour12}:{local.minute:02d} {suffix}"


def is_within_shift_window(now: datetime | None = None) -> bool:
    """True when New York local time is inside [9:00 AM, 6:00 PM)."""
    local_now = (now or portal_now()).astimezone(PORTAL_TZ)
    work_date = current_work_date(local_now)
    return shift_open_at(work_date) <= local_now < shift_close_at(work_date)


def close_stale_attendance_sessions(*, now: datetime | None = None) -> int:
    """Close any open sessions whose 6 PM New York deadline has passed."""
    local_now = (now or portal_now()).astimezone(PORTAL_TZ)
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
    """
    Open (or reuse) today's attendance session for this membership.

    Shift window is 9:00 AM–6:00 PM America/New_York only.
    Before 9 AM / after 6 PM New York: no new session is created.
    """
    if membership is None or not membership.is_active:
        return None
    if membership.role == OrganizationMembership.Role.OWNER:
        return None

    close_stale_attendance_sessions(now=now)
    local_now = (now or portal_now()).astimezone(PORTAL_TZ)
    work_date = current_work_date(local_now)
    open_at = shift_open_at(work_date)
    deadline = shift_close_at(work_date)

    existing = (
        AgentAttendanceSession.objects.filter(membership=membership, work_date=work_date)
        .order_by("-opened_at")
        .first()
    )
    # Outside the 9 AM–6 PM NY window: return whatever exists, never open new.
    if local_now < open_at or local_now >= deadline:
        return existing

    if existing is None:
        return AgentAttendanceSession.objects.create(
            membership=membership,
            organization=membership.organization,
            work_date=work_date,
            opened_at=local_now,
        )

    if existing.closed_at is not None and local_now < deadline:
        # Re-open only if somehow closed early during the same shift window.
        existing.closed_at = None
        if existing.opened_at is None:
            existing.opened_at = local_now
        existing.save(update_fields=["closed_at", "opened_at", "updated_at"])
    return existing


def start_attendance_on_login(user, *, now: datetime | None = None) -> list:
    """
    Start attendance for every active non-owner membership when the user signs in
    (website or companion app). Only during 9 AM–6 PM New York.
    """
    if user is None or not getattr(user, "is_active", False):
        return []
    memberships = (
        OrganizationMembership.objects.filter(
            user=user,
            is_active=True,
            organization__is_active=True,
        )
        .exclude(role=OrganizationMembership.Role.OWNER)
        .select_related("organization")
    )
    sessions = []
    for membership in memberships:
        session = ensure_attendance_open(membership, now=now)
        if session is not None:
            sessions.append(session)
    return sessions


def task_progress_for_membership(membership: OrganizationMembership) -> dict:
    qs = AgentTask.objects.filter(assigned_to=membership).select_related(
        "created_by", "assigned_to__user"
    )
    totals = qs.aggregate(
        total=Count("id"),
        done=Count("id", filter=Q(status=AgentTask.Status.DONE) | Q(is_done=True)),
        todo=Count("id", filter=Q(status=AgentTask.Status.TODO, is_done=False)),
        in_progress=Count(
            "id", filter=Q(status=AgentTask.Status.IN_PROGRESS, is_done=False)
        ),
        waiting=Count("id", filter=Q(status=AgentTask.Status.WAITING, is_done=False)),
    )
    total = totals["total"] or 0
    done = totals["done"] or 0
    todo = totals["todo"] or 0
    in_progress = totals["in_progress"] or 0
    waiting = totals["waiting"] or 0
    open_count = max(total - done, 0)
    pct = int(round((done / total) * 100)) if total else 0

    pipeline_order = {key: idx for idx, key in enumerate(AgentTask.STATUS_PIPELINE)}
    tasks = list(qs.order_by("-created_at")[:200])
    tasks.sort(key=lambda t: (pipeline_order.get(t.status, 99), -t.created_at.timestamp()))

    by_status = {key: [] for key in AgentTask.STATUS_PIPELINE}
    for task in tasks:
        key = task.status if task.status in by_status else (
            AgentTask.Status.DONE if task.is_done else AgentTask.Status.TODO
        )
        by_status[key].append(task)

    return {
        "total": total,
        "done": done,
        "open": open_count,
        "todo": todo,
        "in_progress": in_progress,
        "waiting": waiting,
        "percent": pct,
        "tasks": tasks,
        "open_tasks": [t for t in tasks if not t.is_done],
        "done_tasks": [t for t in tasks if t.is_done],
        "todo_tasks": by_status[AgentTask.Status.TODO],
        "in_progress_tasks": by_status[AgentTask.Status.IN_PROGRESS],
        "waiting_tasks": by_status[AgentTask.Status.WAITING],
        "stages": [
            {
                "key": AgentTask.Status.TODO,
                "label": "To do",
                "count": todo,
                "tasks": by_status[AgentTask.Status.TODO],
            },
            {
                "key": AgentTask.Status.IN_PROGRESS,
                "label": "In progress",
                "count": in_progress,
                "tasks": by_status[AgentTask.Status.IN_PROGRESS],
            },
            {
                "key": AgentTask.Status.WAITING,
                "label": "Waiting",
                "count": waiting,
                "tasks": by_status[AgentTask.Status.WAITING],
            },
            {
                "key": AgentTask.Status.DONE,
                "label": "Done",
                "count": done,
                "tasks": by_status[AgentTask.Status.DONE],
            },
        ],
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
    """Activity events for an actor; defaults to current New York work-date window."""
    qs = AgentActivityEvent.objects.filter(organization=organization, actor=user)
    if start is None and end is None:
        local_now = (now or portal_now()).astimezone(PORTAL_TZ)
        work_date = current_work_date(local_now)
        start_dt = datetime.combine(work_date, time(0, 0), tzinfo=PORTAL_TZ)
        end_dt = shift_close_at(work_date)
        qs = qs.filter(created_at__gte=start_dt, created_at__lt=end_dt)
    else:
        if start is not None:
            start_dt = datetime.combine(start, time(0, 0), tzinfo=PORTAL_TZ)
            qs = qs.filter(created_at__gte=start_dt)
        if end is not None:
            end_dt = datetime.combine(end + timedelta(days=1), time(0, 0), tzinfo=PORTAL_TZ)
            qs = qs.filter(created_at__lt=end_dt)
    return list(qs.order_by("-created_at")[:limit])


def staff_day_audit_trail(user, organization, *, work_date, limit: int = 80) -> dict:
    """
    Day-scoped audit for a staff profile: activity events + service records handled.
    Used by managers, accountants, and insurance agents on portal/profile.
    """
    from .models import ServiceRecord

    events = activity_for_user(
        user,
        organization,
        start=work_date,
        end=work_date,
        limit=limit,
    )
    services = list(
        ServiceRecord.objects.filter(
            organization=organization,
            handled_by=user,
            transaction_date=work_date,
            deleted_at__isnull=True,
        )
        .order_by("-created_at")[:limit]
    )
    task_updates = list(
        AgentTask.objects.filter(
            organization=organization,
            assigned_to__user=user,
            updated_at__gte=datetime.combine(work_date, time(0, 0), tzinfo=PORTAL_TZ),
            updated_at__lt=datetime.combine(
                work_date + timedelta(days=1), time(0, 0), tzinfo=PORTAL_TZ
            ),
        )
        .select_related("assigned_to__user")
        .order_by("-updated_at")[:limit]
    )
    return {
        "work_date": work_date,
        "activity_events": events,
        "service_records": services,
        "task_updates": task_updates,
        "total_events": len(events) + len(services) + len(task_updates),
    }


def today_activity_for_user(user, organization, *, now: datetime | None = None):
    """Activity events for the current New York work-date window for this actor."""
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
    # Also pull a longer recent trail (last 14 New York days) for audit profiles.
    local_now = portal_now()
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
    """Insurance agents, managers, and accountants land on the personal portal home."""
    if membership is None or not membership.is_active:
        return False
    if membership.role == OrganizationMembership.Role.OWNER:
        return False
    from .role_permissions import normalize_role

    role = normalize_role(membership.role)
    if role in {
        OrganizationMembership.Role.INSURANCE_AGENT,
        OrganizationMembership.Role.MANAGER,
        OrganizationMembership.Role.ACCOUNTANT,
    }:
        return True
    return bool(membership.can_deal_with_insurance)


def can_access_agent_portal(membership: OrganizationMembership | None) -> bool:
    """Personal portal (tasks + day audit) for insurance agents, managers, accountants."""
    return uses_agent_portal_home(membership)


def can_create_personal_tasks(membership: OrganizationMembership | None) -> bool:
    """Staff roles may create and manage tasks assigned to themselves."""
    return can_access_agent_portal(membership)


def can_manage_agent_tasks(membership: OrganizationMembership | None) -> bool:
    if membership is None:
        return False
    if membership.role == OrganizationMembership.Role.OWNER:
        return True
    if membership.role == OrganizationMembership.Role.MANAGER:
        return bool(membership.is_active)
    return bool(membership.can_assign_agent_tasks and membership.is_active)


def owner_can_review_agent(viewer: OrganizationMembership | None, agent: OrganizationMembership) -> bool:
    """Owners and managers may open the workboard for any active non-owner in their PSB."""
    if viewer is None or agent is None:
        return False
    if not agent.is_active:
        return False
    if agent.role == OrganizationMembership.Role.OWNER:
        return False
    if viewer.organization_id != agent.organization_id:
        return False
    if not viewer.is_active:
        return False
    return viewer.role in {
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.MANAGER,
    }


def attendance_roster_for_owner(owner_user, *, work_date=None, organization_id=None) -> dict:
    """Owner-facing attendance tracker for all agents across owned PSBs."""
    close_stale_attendance_sessions()
    local_now = portal_now()
    selected_date = work_date or current_work_date(local_now)

    owned_orgs = Organization.objects.filter(
        memberships__user=owner_user,
        memberships__role=OrganizationMembership.Role.OWNER,
        memberships__is_active=True,
        is_active=True,
    ).distinct()
    if organization_id:
        owned_orgs = owned_orgs.filter(id=organization_id)

    agents = (
        OrganizationMembership.objects.filter(
            organization__in=owned_orgs,
            is_active=True,
        )
        .exclude(user=owner_user)
        .exclude(role=OrganizationMembership.Role.OWNER)
        .select_related("user", "organization")
        .order_by("organization__name", "user__first_name", "user__last_name", "user__username")
    )

    sessions_by_membership = {
        s.membership_id: s
        for s in AgentAttendanceSession.objects.filter(
            membership__in=agents,
            work_date=selected_date,
        )
    }

    rows = []
    on_shift = 0
    closed = 0
    absent = 0
    for membership in agents:
        session = sessions_by_membership.get(membership.id)
        if session is None:
            status = "absent"
            absent += 1
        elif session.is_open:
            status = "on_shift"
            on_shift += 1
        else:
            status = "closed"
            closed += 1
        open_at = shift_open_at(selected_date)
        close_at = shift_close_at(selected_date)
        rows.append(
            {
                "membership": membership,
                "session": session,
                "status": status,
                "open_at": open_at,
                "close_at": close_at,
                "opened_display": format_ny_time(session.opened_at if session else None),
                "closed_display": format_ny_time(session.closed_at if session else None),
                "open_display": format_ny_time(open_at),
                "close_display": format_ny_time(close_at),
            }
        )

    open_at = shift_open_at(selected_date)
    close_at = shift_close_at(selected_date)
    return {
        "work_date": selected_date,
        "cairo_now": local_now,
        "local_now": local_now,
        "ny_now_display": format_ny_time(local_now),
        "open_at": open_at,
        "close_at": close_at,
        "open_display": format_ny_time(open_at),
        "close_display": format_ny_time(close_at),
        "organizations": list(owned_orgs.order_by("name")),
        "rows": rows,
        "counts": {
            "total": len(rows),
            "on_shift": on_shift,
            "closed": closed,
            "absent": absent,
        },
    }


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
