"""Agent portal views: home, photo, tasks, owner review."""

from __future__ import annotations

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .access import organizations_for_user
from .agent_portal_forms import AgentProfilePhotoForm, AgentTaskAssignForm
from .agent_portal_models import AgentTask
from .agent_portal_services import (
    accessible_space_cards,
    agent_workboard_payload,
    attendance_roster_for_owner,
    can_access_agent_portal,
    can_manage_agent_tasks,
    cairo_now,
    current_work_date,
    ensure_attendance_open,
    owner_can_review_agent,
    shift_close_at,
    task_progress_for_membership,
    today_activity_for_user,
    uses_agent_portal_home,
)
from .http import deny_access
from .models import OrganizationMembership
from .policies import redirect_back


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
        messages.info(request, "The agent portal is only available to insurance agents.")
        return redirect("dashboard")

    attendance = ensure_attendance_open(membership)
    progress = task_progress_for_membership(membership)
    activity = today_activity_for_user(
        request.user,
        membership.organization,
    )
    spaces = accessible_space_cards(membership)
    local_now = cairo_now()
    work_date = current_work_date(local_now)
    close_at = shift_close_at(work_date)

    photo_form = AgentProfilePhotoForm(instance=membership)

    return render(
        request,
        "core/agent_portal/home.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "attendance": attendance,
            "work_date": work_date,
            "close_at": close_at,
            "cairo_now": local_now,
            "task_progress": progress,
            "activity_events": activity,
            "space_cards": spaces,
            "photo_form": photo_form,
            "can_manage_tasks": False,
            "assign_form": None,
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
        AgentTask,
        id=task_id,
        organization=membership.organization,
    )
    is_assignee = task.assigned_to_id == membership.id
    is_manager = can_manage_agent_tasks(membership)
    if not (is_assignee or is_manager):
        deny_access("You cannot update this task.")

    done = request.POST.get("done", "").lower() in {"1", "true", "on", "yes"}
    if request.POST.get("toggle") == "1":
        done = not task.is_done
    task.mark_done(done=done)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        progress = task_progress_for_membership(task.assigned_to)
        return JsonResponse(
            {
                "ok": True,
                "task_id": task.id,
                "is_done": task.is_done,
                "percent": progress["percent"],
                "done": progress["done"],
                "open": progress["open"],
                "total": progress["total"],
            }
        )
    return redirect_back(request, "agent-portal-home")


@login_required
def agent_portal_manage_tasks(request):
    """Deprecated entry — owners assign from each insurance agent's portal review."""
    messages.info(
        request,
        "Assign tasks from an insurance agent’s Audit / portal review on the dashboard.",
    )
    return redirect("dashboard")


@login_required
@require_POST
def agent_portal_create_task(request):
    """Owners assign a task to a specific insurance agent (from portal review)."""
    membership = _resolve_portal_membership(request)
    if membership is None or not can_manage_agent_tasks(membership):
        deny_access("You do not have permission to assign agent tasks.")

    agent_id = request.POST.get("assigned_membership_id") or request.POST.get("assigned_to")
    agent = get_object_or_404(
        OrganizationMembership,
        id=agent_id,
        organization=membership.organization,
        can_deal_with_insurance=True,
        is_active=True,
    )
    if membership.role != OrganizationMembership.Role.OWNER and not membership.can_assign_agent_tasks:
        deny_access("You do not have permission to assign agent tasks.")

    form = AgentTaskAssignForm(
        request.POST,
        organization=membership.organization,
        fixed_assignee=agent,
    )
    fallback = reverse("agent-portal-owner-review", args=[agent.id])
    if form.is_valid():
        task = form.save(commit=False)
        task.organization = membership.organization
        task.assigned_to = agent
        task.created_by = request.user
        task.save()
        messages.success(request, "Task assigned.")
    else:
        messages.error(request, "Could not create task. Check the title.")
    return redirect_back(request, fallback)


@login_required
def agent_portal_tasks_board(request):
    """ClickUp-style personal tasks board for insurance agents."""
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
    if status_filter not in {"all", "open", "done"}:
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
            "can_manage_tasks": False,
            "is_agent_tasks_board": True,
        },
    )


@login_required
def agent_portal_owner_review(request, membership_id):
    """
    Owner view of an insurance agent's portal workboard (tasks, progress, timeline).
    Reached from the dashboard Audit icon when the agent deals with insurance.
    """
    agent = get_object_or_404(
        OrganizationMembership.objects.select_related("organization", "user"),
        id=membership_id,
    )
    viewer = _viewer_owner_membership(request, agent.organization)
    if not owner_can_review_agent(viewer, agent):
        if not agent.can_deal_with_insurance:
            return redirect("agent-audit", membership_id=agent.id)
        deny_access("Owner access required to review this agent portal.")

    workboard = agent_workboard_payload(agent)
    assign_form = AgentTaskAssignForm(
        organization=agent.organization,
        fixed_assignee=agent,
    )
    local_now = cairo_now()

    return render(
        request,
        "core/agent_portal/owner_review.html",
        {
            "viewer": viewer,
            "agent_membership": agent,
            "organization": agent.organization,
            "portal_workboard": workboard,
            "assign_form": assign_form,
            "cairo_now": local_now,
            "is_owner_portal_review": True,
        },
    )


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
