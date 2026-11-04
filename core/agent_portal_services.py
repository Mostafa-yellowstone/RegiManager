"""New York–aware attendance, task progress, and activity timeline services."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.utils import timezone

from .agent_portal_models import AgentActivityEvent, AgentAttendanceSession, AgentDayOff, AgentTask
from .models import Organization, OrganizationMembership
from .space_access import filter_accessible_spaces

# Business day / close clock = USA New York.
PORTAL_TZ = ZoneInfo("America/New_York")
# Agents sit in Egypt; their wall-clock start is 4:00 PM Cairo.
TEAM_TZ = ZoneInfo("Africa/Cairo")
# Backward-compatible alias (historically Cairo; now means portal/NY "now").
CAIRO_TZ = PORTAL_TZ


def portal_now() -> datetime:
    return timezone.now().astimezone(PORTAL_TZ)


def cairo_now() -> datetime:
    """Legacy name — returns America/New_York local time."""
    return portal_now()


# Team opens at 4:00 PM Egypt (= NY morning when offsets are 7h).
# Close follows USA business hours (6:00 PM New York).
SHIFT_OPEN_HOUR_EGYPT = 16  # 4:00 PM Africa/Cairo
SHIFT_CLOSE_HOUR = 18       # 6:00 PM America/New_York
# Kept for older imports that expected a NY open hour constant.
SHIFT_OPEN_HOUR = 9


def current_work_date(now: datetime | None = None):
    """
    Work-date for attendance shifts = America/New_York calendar date.

    Team clocks in by 4:00 PM Egypt that same calendar date; shift ends
    6:00 PM New York.
    """
    local = (now or portal_now()).astimezone(PORTAL_TZ)
    return local.date()


def shift_open_at(work_date) -> datetime:
    """
    16:00 (4:00 PM) Africa/Cairo on work_date.

    That is the Egypt team start. When Egypt/US offsets are 7 hours apart it
    equals 9:00 AM New York; when DST drifts, Egypt 4 PM stays the rule so
    the whole Egypt team is not marked late.
    """
    return datetime.combine(
        work_date, time(SHIFT_OPEN_HOUR_EGYPT, 0), tzinfo=TEAM_TZ
    )


def shift_close_at(work_date) -> datetime:
    """18:00 (6 PM) America/New_York on work_date."""
    return datetime.combine(work_date, time(SHIFT_CLOSE_HOUR, 0), tzinfo=PORTAL_TZ)


def attendance_punctuality(opened_at: datetime | None, work_date=None) -> dict:
    """
    Late if first clock-in is strictly after 4:00 PM Africa/Cairo.
    Exact 4:00 PM Egypt or earlier = on time.
    """
    if opened_at is None:
        return {"is_late": False, "is_on_time": False, "attendance_status": "none"}
    wd = work_date or opened_at.astimezone(PORTAL_TZ).date()
    open_at = shift_open_at(wd)
    if opened_at.astimezone(TEAM_TZ) > open_at:
        return {"is_late": True, "is_on_time": False, "attendance_status": "late"}
    return {"is_late": False, "is_on_time": True, "attendance_status": "on_time"}


def format_ny_time(dt: datetime | None) -> str:
    """Always render a datetime as New York wall-clock (e.g. '9:05 AM')."""
    if dt is None:
        return "—"
    local = dt.astimezone(PORTAL_TZ)
    hour12 = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{hour12}:{local.minute:02d} {suffix}"


def format_egypt_time(dt: datetime | None) -> str:
    """Render as Egypt wall-clock (e.g. '4:05 PM')."""
    if dt is None:
        return "—"
    local = dt.astimezone(TEAM_TZ)
    hour12 = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{hour12}:{local.minute:02d} {suffix}"


def is_within_shift_window(now: datetime | None = None) -> bool:
    """True from 4:00 PM Egypt open through 6:00 PM New York close."""
    instant = now or portal_now()
    work_date = current_work_date(instant)
    return shift_open_at(work_date) <= instant < shift_close_at(work_date)


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

    Agents may clock in any time from midnight until 6:00 PM America/New_York
    so arrivals at/before 4:00 PM Egypt can be marked on time.
    After 6:00 PM New York: no new session is created.
    """
    if membership is None or not membership.is_active:
        return None
    if membership.role == OrganizationMembership.Role.OWNER:
        return None

    close_stale_attendance_sessions(now=now)
    local_now = (now or portal_now()).astimezone(PORTAL_TZ)
    work_date = current_work_date(local_now)
    deadline = shift_close_at(work_date)

    existing = (
        AgentAttendanceSession.objects.filter(membership=membership, work_date=work_date)
        .order_by("-opened_at")
        .first()
    )
    if existing is None:
        return AgentAttendanceSession.objects.create(
            membership=membership,
            organization=membership.organization,
            work_date=work_date,
            opened_at=local_now,
            closed_at=deadline if local_now >= deadline else None,
        )

    if existing.closed_at is not None and local_now < deadline:
        # Re-open only if somehow closed early during the same work day.
        # Keep the original opened_at so punctuality is based on first clock-in.
        existing.closed_at = None
        if existing.opened_at is None:
            existing.opened_at = local_now
        existing.save(update_fields=["closed_at", "opened_at", "updated_at"])
    return existing


def start_attendance_on_login(user, *, now: datetime | None = None) -> list:
    """
    Start attendance for every active non-owner membership when the user signs in
    (website or companion app). Allowed from midnight until 6 PM New York.
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
    qs = (
        AgentTask.objects.filter(assigned_to=membership)
        .select_related("created_by", "assigned_to__user")
        .prefetch_related("quote_leads__documents", "email_marketing_contacts")
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
    if membership.can_use_insurance and not membership.organization.has_psb_portal:
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

    days_off_by_membership = {
        d.membership_id: d
        for d in AgentDayOff.objects.filter(
            membership__in=agents,
            day_off_date=selected_date,
        )
    }

    rows = []
    on_shift = 0
    closed = 0
    absent = 0
    days_off_count = 0
    for membership in agents:
        session = sessions_by_membership.get(membership.id)
        day_off = days_off_by_membership.get(membership.id)
        if session is None:
            if day_off is not None:
                status = "day_off"
                days_off_count += 1
            else:
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
                "day_off": day_off,
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
            "day_off": days_off_count,
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


def monthly_attendance_for_membership(
    membership: OrganizationMembership,
    *,
    year: int | None = None,
    month: int | None = None,
    now: datetime | None = None,
) -> dict:
    """
    Month-by-month attendance statistics and full daily session breakdown for an agent.
    Computes:
    - Days attended (total sessions recorded this month)
    - Days absent / missed (past working days with no check-in)
    - Days remaining / left in the month (upcoming working days)
    - On-time vs late clock-in counts
    - Total shift duration (hours & minutes)
    - Attendance percentage
    - Full list of all calendar days in the month with check-in, check-out, duration, and status
    - Navigation metadata (prev month, next month, month options list)
    """
    local_now = (now or portal_now()).astimezone(PORTAL_TZ)
    today = current_work_date(local_now)

    try:
        y = int(year) if year is not None else today.year
        m = int(month) if month is not None else today.month
        target_date = date(y, m, 1)
    except (ValueError, TypeError):
        target_date = date(today.year, today.month, 1)

    target_year = target_date.year
    target_month = target_date.month

    num_days = calendar.monthrange(target_year, target_month)[1]
    month_start = date(target_year, target_month, 1)
    month_end = date(target_year, target_month, num_days)

    prev_month_date = (month_start - timedelta(days=1)).replace(day=1)
    next_month_date = (month_end + timedelta(days=1)).replace(day=1)

    # 12-month selector options around target
    month_options = []
    base_cursor = date(today.year, today.month, 1)
    for offset in range(-11, 2):
        m_offset = base_cursor.month + offset
        y_offset = base_cursor.year
        while m_offset < 1:
            m_offset += 12
            y_offset -= 1
        while m_offset > 12:
            m_offset -= 12
            y_offset += 1
        opt_d = date(y_offset, m_offset, 1)
        month_options.append({
            "year": y_offset,
            "month": m_offset,
            "label": opt_d.strftime("%B %Y"),
            "is_selected": (y_offset == target_year and m_offset == target_month),
            "is_current": (y_offset == today.year and m_offset == today.month),
        })

    # Close any stale sessions so closed_at is accurate
    close_stale_attendance_sessions(now=now)

    sessions = (
        AgentAttendanceSession.objects.filter(
            membership=membership,
            work_date__gte=month_start,
            work_date__lte=month_end,
        )
        .order_by("work_date")
    )
    sessions_by_date = {s.work_date: s for s in sessions}

    days_off_qs = AgentDayOff.objects.filter(
        membership=membership,
        day_off_date__gte=month_start,
        day_off_date__lte=month_end,
    )
    days_off_by_date = {d.day_off_date: d for d in days_off_qs}

    days = []
    days_attended = 0
    days_on_time = 0
    days_late = 0
    days_absent = 0
    days_off_count = 0
    working_days_total = 0
    past_working_days = 0
    future_working_days = 0
    total_seconds_worked = 0

    for day_num in range(1, num_days + 1):
        cur_date = date(target_year, target_month, day_num)
        is_past = cur_date < today
        is_today = cur_date == today
        is_future = cur_date > today
        is_sunday = cur_date.weekday() == 6
        is_saturday = cur_date.weekday() == 5
        is_weekend = is_sunday  # Only Sunday is week-off; Saturday and Mon-Fri are working days
        is_work_day = not is_weekend

        if is_work_day:
            working_days_total += 1
            if is_past or is_today:
                past_working_days += 1
            if is_future:
                future_working_days += 1

        session = sessions_by_date.get(cur_date)

        if session is not None:
            days_attended += 1
            punc = attendance_punctuality(session.opened_at, cur_date)
            is_on_time = punc["is_on_time"]
            is_late = punc["is_late"]
            if is_on_time:
                days_on_time += 1
            elif is_late:
                days_late += 1

            shift_secs = 0
            if session.opened_at and session.closed_at:
                shift_secs = max(0, int((session.closed_at - session.opened_at).total_seconds()))
            elif session.opened_at and session.is_open and is_today:
                shift_secs = max(0, int((local_now - session.opened_at).total_seconds()))
            total_seconds_worked += shift_secs

            hrs = shift_secs // 3600
            mins = (shift_secs % 3600) // 60
            dur_display = f"{hrs}h {mins:02d}m" if shift_secs > 0 else "—"

            if session.is_open and is_today:
                status_key = "on_shift"
                status_label = "On shift (Active)"
                status_badge = "success"
            elif is_on_time:
                status_key = "on_time"
                status_label = "Present · On time"
                status_badge = "success"
            elif is_late:
                status_key = "late"
                status_label = "Present · Late"
                status_badge = "warning"
            else:
                status_key = "present"
                status_label = "Present"
                status_badge = "info"

            days.append({
                "date": cur_date,
                "day_num": day_num,
                "weekday_name": cur_date.strftime("%a"),
                "is_today": is_today,
                "is_past": is_past,
                "is_future": is_future,
                "is_weekend": is_weekend,
                "is_work_day": is_work_day,
                "has_session": True,
                "session": session,
                "day_off": None,
                "status_key": status_key,
                "status_label": status_label,
                "status_badge": status_badge,
                "opened_ny": format_ny_time(session.opened_at),
                "opened_egypt": format_egypt_time(session.opened_at),
                "closed_ny": format_ny_time(session.closed_at) if session.closed_at else ("On shift" if session.is_open and is_today else "—"),
                "closed_egypt": format_egypt_time(session.closed_at) if session.closed_at else ("On shift" if session.is_open and is_today else "—"),
                "duration_display": dur_display,
                "duration_seconds": shift_secs,
            })
        else:
            if is_weekend:
                status_key = "weekend"
                status_label = "Sunday (Off)"
                status_badge = "neutral"
            elif cur_date in days_off_by_date:
                day_off_obj = days_off_by_date[cur_date]
                status_key = "day_off"
                status_label = f"Day Off · {day_off_obj.get_reason_display()}"
                status_badge = "amber"
                days_off_count += 1
            elif is_future:
                status_key = "upcoming"
                status_label = "Upcoming"
                status_badge = "neutral"
            elif is_today:
                status_key = "no_checkin"
                status_label = "No check-in yet"
                status_badge = "warning"
                if is_work_day:
                    days_absent += 1
            else:
                status_key = "absent"
                status_label = "Absent / Missed"
                status_badge = "danger"
                if is_work_day:
                    days_absent += 1

            days.append({
                "date": cur_date,
                "day_num": day_num,
                "weekday_name": cur_date.strftime("%a"),
                "is_today": is_today,
                "is_past": is_past,
                "is_future": is_future,
                "is_weekend": is_weekend,
                "is_work_day": is_work_day,
                "has_session": False,
                "session": None,
                "day_off": days_off_by_date.get(cur_date),
                "status_key": status_key,
                "status_label": status_label,
                "status_badge": status_badge,
                "opened_ny": "—",
                "opened_egypt": "—",
                "closed_ny": "—",
                "closed_egypt": "—",
                "duration_display": "—",
                "duration_seconds": 0,
            })

    past_effective_working_days = max(0, past_working_days - days_off_count)
    att_rate = round((days_attended / past_effective_working_days * 100), 1) if past_effective_working_days > 0 else 100.0
    if att_rate > 100.0:
        att_rate = 100.0

    total_hrs = total_seconds_worked // 3600
    total_mins = (total_seconds_worked % 3600) // 60
    total_hours_display = f"{total_hrs}h {total_mins:02d}m"

    avg_secs = (total_seconds_worked / days_attended) if days_attended > 0 else 0
    avg_hrs = int(avg_secs // 3600)
    avg_mins = int((avg_secs % 3600) // 60)
    avg_hours_display = f"{avg_hrs}h {avg_mins:02d}m" if days_attended > 0 else "—"

    is_current_month = (target_year == today.year and target_month == today.month)

    return {
        "membership": membership,
        "year": target_year,
        "month": target_month,
        "month_label": target_date.strftime("%B %Y"),
        "month_start": month_start,
        "month_end": month_end,
        "prev_year": prev_month_date.year,
        "prev_month": prev_month_date.month,
        "next_year": next_month_date.year,
        "next_month": next_month_date.month,
        "month_options": month_options,
        "is_current_month": is_current_month,
        "days": days,
        "days_attended": days_attended,
        "days_absent": days_absent,
        "days_off_count": days_off_count,
        "days_off_by_date": days_off_by_date,
        "days_left_in_month": future_working_days,
        "days_on_time": days_on_time,
        "days_late": days_late,
        "working_days_total": working_days_total,
        "past_working_days": past_working_days,
        "attendance_rate": att_rate,
        "total_hours_display": total_hours_display,
        "avg_hours_display": avg_hours_display,
    }


def save_agent_attendance_session_record(
    membership: OrganizationMembership,
    *,
    work_date: date,
    opened_time_str: str | None = None,
    closed_time_str: str | None = None,
    actor=None,
) -> AgentAttendanceSession:
    """Manual adjustment / backfill of an attendance session by owner/manager."""
    session, _ = AgentAttendanceSession.objects.get_or_create(
        membership=membership,
        work_date=work_date,
        defaults={
            "organization": membership.organization,
            "opened_at": shift_open_at(work_date),
            "closed_at": shift_close_at(work_date),
        },
    )

    if opened_time_str:
        try:
            parts = [int(p) for p in opened_time_str.split(":")]
            session.opened_at = datetime.combine(
                work_date, time(parts[0], parts[1]), tzinfo=PORTAL_TZ
            )
        except Exception:
            pass

    if closed_time_str:
        try:
            parts = [int(p) for p in closed_time_str.split(":")]
            session.closed_at = datetime.combine(
                work_date, time(parts[0], parts[1]), tzinfo=PORTAL_TZ
            )
        except Exception:
            pass
    elif closed_time_str == "":
        session.closed_at = None

    session.save()
    if actor:
        log_agent_activity(
            organization=membership.organization,
            actor=actor,
            membership=membership,
            domain="attendance",
            event_type="attendance_adjusted",
            title=f"Attendance adjusted for {work_date.isoformat()}",
            detail=f"Opened: {format_ny_time(session.opened_at)}, Closed: {format_ny_time(session.closed_at)}",
            object_id=session.id,
        )
    return session
