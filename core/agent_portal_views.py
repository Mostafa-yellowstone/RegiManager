"""Agent portal views: home, photo, tasks, owner review."""

from __future__ import annotations

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .access import organizations_for_user
from .agent_portal_forms import AgentProfilePhotoForm, AgentTaskAssignForm, AgentTaskEditForm
from .agent_portal_models import AgentTask
from .agent_portal_services import (
    accessible_space_cards,
    agent_workboard_payload,
    attendance_roster_for_owner,
    can_access_agent_portal,
    can_create_personal_tasks,
    can_manage_agent_tasks,
    cairo_now,
    current_work_date,
    ensure_attendance_open,
    format_ny_time,
    owner_can_review_agent,
    shift_close_at,
    shift_open_at,
    staff_day_audit_trail,
    task_progress_for_membership,
    today_activity_for_user,
    uses_agent_portal_home,
)
from .http import deny_access
from .models import OrganizationMembership
from .policies import redirect_back


def _notify_task_assigned(task: AgentTask):
    if not task.assigned_to_id or not task.assigned_to.user_id:
        return
    from django.urls import reverse

    from core.models import Notification
    from core.notification_actions import task_board_action_url
    from core.realtime import publish_user_event

    action_url = task_board_action_url(task_id=task.id)
    notif = Notification.objects.create(
        user=task.assigned_to.user,
        organization=task.organization,
        event_type="agent_task_assigned",
        level=Notification.Level.INFO,
        title="New task assigned",
        message=task.title[:200],
        action_url=action_url,
    )
    unread = Notification.objects.filter(
        user=task.assigned_to.user, is_read=False
    ).count()
    publish_user_event(
        task.assigned_to.user_id,
        "notification.created",
        {
            "id": notif.id,
            "title": notif.title,
            "message": notif.message,
            "level": notif.level,
            "event_type": notif.event_type,
            "action_url": notif.action_url,
            "open_url": reverse("open-notification", args=[notif.id]),
            "created_at": notif.created_at.isoformat() if notif.created_at else "",
            "unread_count": unread,
        },
    )


def _task_progress_payload(progress: dict, task: AgentTask) -> dict:
    return {
        "ok": True,
        "task_id": task.id,
        "status": task.status,
        "status_label": task.get_status_display(),
        "is_done": task.is_done,
        "completion_note": task.completion_note or "",
        "percent": progress["percent"],
        "done": progress["done"],
        "open": progress["open"],
        "todo": progress.get("todo", 0),
        "in_progress": progress.get("in_progress", 0),
        "waiting": progress.get("waiting", 0),
        "total": progress["total"],
    }


def _resolve_portal_membership(request) -> OrganizationMembership | None:
    organizations = organizations_for_user(request)
    if not organizations.exists():
        return None
    active_org_id = request.session.get("active_org_id")
    qs = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
        organization__in=organizations,
    ).select_related("organization", "user")
    if active_org_id:
        membership = qs.filter(organization_id=active_org_id).first()
        if membership:
            return membership
    insurance = qs.filter(can_deal_with_insurance=True).first()
    if insurance:
        return insurance
    from .role_permissions import Role, normalize_role

    for preferred in (Role.MANAGER, Role.ACCOUNTANT, Role.INSURANCE_AGENT, Role.AGENT):
        match = next((m for m in qs if normalize_role(m.role) == preferred), None)
        if match:
            return match
    return qs.first()


def _viewer_owner_membership(request, organization) -> OrganizationMembership | None:
    return (
        OrganizationMembership.objects.filter(
            user=request.user,
            organization=organization,
            is_active=True,
            role=OrganizationMembership.Role.OWNER,
        )
        .select_related("organization", "user")
        .first()
    )


def agent_portal_login_redirect(request):
    """Return agent-portal URL name if this user should land there."""
    membership = _resolve_portal_membership(request)
    if uses_agent_portal_home(membership):
        return "agent-portal-home"
    return "dashboard"


@login_required
def agent_portal_home(request):
    if request.user.is_superuser:
        return redirect("/admin/")

    membership = _resolve_portal_membership(request)
    if not can_access_agent_portal(membership):
        messages.info(
            request,
            "Your workspace portal is available to managers, accountants, and insurance agents.",
        )
        return redirect("dashboard")

    attendance = ensure_attendance_open(membership)
    progress = task_progress_for_membership(membership)
    local_now = cairo_now()
    work_date = current_work_date(local_now)
    activity_date_raw = (request.GET.get("activity_date") or "").strip()
    activity_date = work_date
    if activity_date_raw:
        try:
            activity_date = datetime.strptime(activity_date_raw, "%Y-%m-%d").date()
        except ValueError:
            activity_date = work_date

    day_audit = staff_day_audit_trail(
        request.user,
        membership.organization,
        work_date=activity_date,
    )
    spaces = accessible_space_cards(membership)
    open_at = shift_open_at(work_date)
    close_at = shift_close_at(work_date)

    photo_form = AgentProfilePhotoForm(instance=membership)
    can_add_own = can_create_personal_tasks(membership)
    assign_form = None
    if can_add_own:
        assign_form = AgentTaskAssignForm(
            organization=membership.organization,
            fixed_assignee=membership,
            allow_staff=True,
        )

    from .role_permissions import normalize_role, role_label

    return render(
        request,
        "core/agent_portal/home.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "attendance": attendance,
            "work_date": work_date,
            "activity_date": activity_date,
            "open_at": open_at,
            "close_at": close_at,
            "open_display": format_ny_time(open_at),
            "close_display": format_ny_time(close_at),
            "ny_now_display": format_ny_time(local_now),
            "opened_display": format_ny_time(attendance.opened_at if attendance else None),
            "closed_display": format_ny_time(attendance.closed_at if attendance else None),
            "cairo_now": local_now,
            "task_progress": progress,
            "activity_events": day_audit["activity_events"],
            "service_audit_records": day_audit["service_records"],
            "task_audit_updates": day_audit["task_updates"],
            "day_audit_total": day_audit["total_events"],
            "space_cards": spaces,
            "photo_form": photo_form,
            "can_manage_tasks": can_manage_agent_tasks(membership),
            "can_add_own_tasks": can_add_own,
            "assign_form": assign_form,
            "portal_role_label": role_label(normalize_role(membership.role)),
            "is_agent_portal_home": True,
        },
    )


@login_required
@require_POST
def agent_portal_upload_photo(request):
    membership = _resolve_portal_membership(request)
    if not can_access_agent_portal(membership):
        deny_access("Access denied.")
    form = AgentProfilePhotoForm(request.POST, request.FILES, instance=membership)
    if form.is_valid():
        form.save()
        messages.success(request, "Profile photo updated.")
    else:
        messages.error(request, "Could not update photo. Use a JPG or PNG under 5 MB.")
    return redirect("agent-portal-home")


@login_required
@require_POST
def agent_portal_toggle_task(request, task_id):
    membership = _resolve_portal_membership(request)
    if membership is None:
        deny_access("Access denied.")
    task = get_object_or_404(
        AgentTask.objects.select_related("assigned_to__user"),
        id=task_id,
        organization=membership.organization,
    )
    is_assignee = task.assigned_to_id == membership.id
    is_manager = can_manage_agent_tasks(membership)
    if not (is_assignee or is_manager):
        deny_access("You cannot update this task.")

    status_raw = (request.POST.get("status") or "").strip().lower()
    note = request.POST.get("completion_note")
    if note is None:
        note = request.POST.get("note")

    note_required_statuses = {
        AgentTask.Status.IN_PROGRESS,
        AgentTask.Status.WAITING,
        AgentTask.Status.DONE,
    }

    def _missing_progress_note(status_value: str) -> bool:
        return status_value in note_required_statuses and not (note or "").strip()

    try:
        if status_raw:
            if _missing_progress_note(status_raw):
                error = "Add a progress note for In progress, Waiting, or Complete."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {"ok": False, "error": error, "requires_note": True, "task_id": task.id},
                        status=400,
                    )
                messages.error(request, error)
                return redirect_back(request, "agent-portal-tasks-board")
            task.set_status(status_raw, note=note if note is not None else None)
        elif request.POST.get("toggle") == "1":
            target_done = not task.is_done
            if target_done and not (note or "").strip():
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "A progress note is required.",
                            "requires_note": True,
                            "task_id": task.id,
                        },
                        status=400,
                    )
                messages.error(request, "Add a progress note before marking done.")
                return redirect_back(request, "agent-portal-tasks-board")
            task.mark_done(
                done=target_done,
                note=note if note is not None else None,
            )
        else:
            done = request.POST.get("done", "").lower() in {"1", "true", "on", "yes"}
            if done and not (note or "").strip():
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "A progress note is required.",
                            "requires_note": True,
                            "task_id": task.id,
                        },
                        status=400,
                    )
                messages.error(request, "Add a progress note before marking done.")
                return redirect_back(request, "agent-portal-tasks-board")
            task.mark_done(done=done, note=note if note is not None else None)
    except ValueError as exc:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect_back(request, "agent-portal-tasks-board")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        progress = task_progress_for_membership(task.assigned_to)
        return JsonResponse(_task_progress_payload(progress, task))
    return redirect_back(request, "agent-portal-home")


@login_required
def agent_portal_manage_tasks(request):
    """Org-wide staged Tasks CRM for owners and lead agents."""
    membership = _resolve_portal_membership(request)
    if membership is None or not can_manage_agent_tasks(membership):
        deny_access("You do not have permission to manage agent tasks.")

    organization = membership.organization
    agents = (
        OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            can_deal_with_insurance=True,
        )
        .exclude(role=OrganizationMembership.Role.OWNER)
        .select_related("user")
        .order_by("user__first_name", "user__username")
    )

    selected_agent = (request.GET.get("agent") or "").strip()
    selected_status = (request.GET.get("status") or "all").strip().lower()
    search_query = (request.GET.get("q") or "").strip()
    view_mode = (request.GET.get("view") or "board").strip().lower()
    if view_mode not in {"board", "list"}:
        view_mode = "board"
    valid_statuses = {c.value for c in AgentTask.Status} | {"all", "open"}
    if selected_status not in valid_statuses:
        selected_status = "all"

    tasks = (
        AgentTask.objects.filter(organization=organization)
        .select_related("assigned_to__user", "created_by")
        .order_by("-created_at")
    )
    if selected_agent.isdigit():
        tasks = tasks.filter(assigned_to_id=int(selected_agent))
    if selected_status == "open":
        tasks = tasks.exclude(status=AgentTask.Status.DONE)
    elif selected_status in {c.value for c in AgentTask.Status}:
        tasks = tasks.filter(status=selected_status)
    if search_query:
        tasks = tasks.filter(
            Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(completion_note__icontains=search_query)
            | Q(assigned_to__user__first_name__icontains=search_query)
            | Q(assigned_to__user__last_name__icontains=search_query)
            | Q(assigned_to__user__username__icontains=search_query)
        )

    task_list = list(tasks[:300])
    by_status = {key: [] for key in AgentTask.STATUS_PIPELINE}
    for task in task_list:
        key = task.status if task.status in by_status else AgentTask.Status.TODO
        by_status[key].append(task)

    stages = [
        {
            "key": key,
            "label": label,
            "count": len(by_status[key]),
            "tasks": by_status[key],
        }
        for key, label in AgentTask.Status.choices
    ]

    totals = AgentTask.objects.filter(organization=organization).aggregate(
        total=Count("id"),
        done=Count("id", filter=Q(status=AgentTask.Status.DONE)),
        open=Count("id", filter=~Q(status=AgentTask.Status.DONE)),
    )

    assign_form = AgentTaskAssignForm(organization=organization)

    return render(
        request,
        "core/agent_portal/manage_tasks.html",
        {
            "membership": membership,
            "organization": organization,
            "agents": agents,
            "assign_form": assign_form,
            "stages": stages,
            "tasks": task_list,
            "selected_agent": selected_agent,
            "selected_status": selected_status,
            "search_query": search_query,
            "view_mode": view_mode,
            "status_choices": AgentTask.Status.choices,
            "crm_totals": {
                "total": totals["total"] or 0,
                "done": totals["done"] or 0,
                "open": totals["open"] or 0,
            },
            "can_manage_tasks": True,
            "is_agent_tasks_crm": True,
        },
    )


@login_required
@require_POST
def agent_portal_create_task(request):
    """Owners/leads assign tasks; managers/accountants/agents may also add personal tasks."""
    membership = _resolve_portal_membership(request)
    if membership is None:
        deny_access("Access denied.")

    agent_id = request.POST.get("assigned_membership_id") or request.POST.get("assigned_to")
    fixed_assignee = None
    if agent_id:
        fixed_assignee = get_object_or_404(
            OrganizationMembership,
            id=agent_id,
            organization=membership.organization,
            is_active=True,
        )

    assigning_to_self = fixed_assignee is not None and fixed_assignee.id == membership.id
    if assigning_to_self:
        if not can_create_personal_tasks(membership):
            deny_access("You do not have permission to create personal tasks.")
    elif not can_manage_agent_tasks(membership):
        deny_access("You do not have permission to assign agent tasks.")
    elif fixed_assignee and not (
        fixed_assignee.can_deal_with_insurance
        or fixed_assignee.role
        in {
            OrganizationMembership.Role.MANAGER,
            OrganizationMembership.Role.ACCOUNTANT,
            OrganizationMembership.Role.INSURANCE_AGENT,
            OrganizationMembership.Role.AGENT,
        }
    ):
        deny_access("Invalid assignee.")

    form = AgentTaskAssignForm(
        request.POST,
        organization=membership.organization,
        fixed_assignee=fixed_assignee,
        allow_staff=assigning_to_self or can_manage_agent_tasks(membership),
    )
    if assigning_to_self:
        fallback = reverse("agent-portal-home")
    elif fixed_assignee:
        fallback = reverse("agent-profile", args=[fixed_assignee.id]) + "?tab=workboard"
    else:
        fallback = reverse("agent-portal-manage-tasks")

    if form.is_valid():
        task = form.save(commit=False)
        task.organization = membership.organization
        task.created_by = request.user
        task.status = AgentTask.Status.TODO
        task.is_done = False
        task.save()
        if not assigning_to_self:
            _notify_task_assigned(task)
        messages.success(
            request,
            "Task added to your list." if assigning_to_self else "Task assigned.",
        )
    else:
        messages.error(request, "Could not create task. Check the title and assignee.")
    return redirect_back(request, fallback)


@login_required
@require_POST
def agent_portal_update_task(request, task_id):
    """Owner/lead edit, reassign, or move stage for a task."""
    membership = _resolve_portal_membership(request)
    if membership is None or not can_manage_agent_tasks(membership):
        deny_access("You do not have permission to manage agent tasks.")

    task = get_object_or_404(
        AgentTask.objects.select_related("assigned_to__user"),
        id=task_id,
        organization=membership.organization,
    )
    previous_assignee_id = task.assigned_to_id
    form = AgentTaskEditForm(
        request.POST,
        instance=task,
        organization=membership.organization,
    )
    if form.is_valid():
        updated = form.save(commit=False)
        status_raw = (request.POST.get("status") or updated.status or "").strip().lower()
        note = request.POST.get("completion_note")
        try:
            updated.set_status(status_raw, note=note if note is not None else None, save=False)
        except ValueError:
            messages.error(request, "Invalid task status.")
            return redirect_back(request, "agent-portal-manage-tasks")
        updated.save()
        if updated.assigned_to_id != previous_assignee_id:
            _notify_task_assigned(updated)
        messages.success(request, "Task updated.")
    else:
        messages.error(request, "Could not update task.")
    return redirect_back(request, "agent-portal-manage-tasks")


@login_required
@require_POST
def agent_portal_delete_task(request, task_id):
    membership = _resolve_portal_membership(request)
    if membership is None or not can_manage_agent_tasks(membership):
        deny_access("You do not have permission to manage agent tasks.")

    task = get_object_or_404(
        AgentTask,
        id=task_id,
        organization=membership.organization,
    )
    task.delete()
    messages.success(request, "Task deleted.")
    return redirect_back(request, "agent-portal-manage-tasks")


@login_required
def agent_portal_tasks_board(request):
    """Staged personal tasks board for insurance agents."""
    if request.user.is_superuser:
        return redirect("/admin/")

    membership = _resolve_portal_membership(request)
    if not can_access_agent_portal(membership):
        messages.info(request, "The agent portal is only available to insurance agents.")
        return redirect("dashboard")

    ensure_attendance_open(membership)
    progress = task_progress_for_membership(membership)
    local_now = cairo_now()
    view_mode = (request.GET.get("view") or "board").lower()
    if view_mode not in {"board", "list"}:
        view_mode = "board"
    status_filter = (request.GET.get("status") or "all").lower()
    valid = {"all", "open", "todo", "in_progress", "waiting", "done"}
    if status_filter not in valid:
        status_filter = "all"

    return render(
        request,
        "core/agent_portal/tasks_board.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "task_progress": progress,
            "cairo_now": local_now,
            "view_mode": view_mode,
            "status_filter": status_filter,
            "status_choices": AgentTask.Status.choices,
            "can_manage_tasks": False,
            "is_agent_tasks_board": True,
        },
    )


@login_required
def agent_portal_owner_review(request, membership_id):
    """Legacy URL — redirect into the unified agent profile workboard tab."""
    from django.urls import reverse
    from django.shortcuts import redirect

    qs = request.GET.copy()
    qs["tab"] = "workboard"
    return redirect(f"{reverse('agent-profile', args=[membership_id])}?{qs.urlencode()}")


@login_required
def agent_attendance_tracker(request):
    """Owner attendance board — live on-shift / closed / absent for all agents."""
    if request.user.is_superuser:
        return redirect("/admin/")

    owned = OrganizationMembership.objects.filter(
        user=request.user,
        role=OrganizationMembership.Role.OWNER,
        is_active=True,
        organization__is_active=True,
    )
    if not owned.exists():
        deny_access("Owner access required.")

    work_date_raw = (request.GET.get("work_date") or "").strip()
    org_raw = (request.GET.get("organization_id") or "").strip()
    work_date = None
    if work_date_raw:
        try:
            work_date = datetime.strptime(work_date_raw, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Invalid work date. Use YYYY-MM-DD.")
            return redirect("agent-attendance-tracker")

    organization_id = None
    if org_raw:
        try:
            organization_id = int(org_raw)
        except ValueError:
            organization_id = None

    roster = attendance_roster_for_owner(
        request.user,
        work_date=work_date,
        organization_id=organization_id,
    )
    return render(
        request,
        "core/agent_portal/attendance_tracker.html",
        {
            "roster": roster,
            "selected_org_id": organization_id,
            "is_attendance_tracker": True,
        },
    )
