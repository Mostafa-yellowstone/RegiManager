"""Agent portal views: home, photo, tasks, spaces picker."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import organizations_for_user
from .agent_portal_forms import AgentProfilePhotoForm, AgentTaskAssignForm
from .agent_portal_models import AgentTask
from .agent_portal_services import (
    accessible_space_cards,
    can_manage_agent_tasks,
    cairo_now,
    current_work_date,
    ensure_attendance_open,
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
    # Prefer an insurance-capable membership for portal context.
    insurance = qs.filter(can_deal_with_insurance=True).first()
    if insurance:
        return insurance
    return qs.first()


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
    if membership is None:
        messages.error(request, "Your account is currently disabled for all PSBs. Contact an owner.")
        return redirect("login")

    # Insurance agents use this as home; owners/other agents may still open it.
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
    can_manage = can_manage_agent_tasks(membership)
    assign_form = AgentTaskAssignForm(organization=membership.organization) if can_manage else None

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
            "can_manage_tasks": can_manage,
            "assign_form": assign_form,
            "is_agent_portal_home": True,
        },
    )


@login_required
@require_POST
def agent_portal_upload_photo(request):
    membership = _resolve_portal_membership(request)
    if membership is None:
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
    # Checkbox posts: if "done" omitted, treat as toggle from current state when toggle=1
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
                "total": progress["total"],
            }
        )
    return redirect_back(request, "agent-portal-home")


@login_required
def agent_portal_manage_tasks(request):
    membership = _resolve_portal_membership(request)
    if membership is None or not can_manage_agent_tasks(membership):
        deny_access("You do not have permission to assign agent tasks.")

    org = membership.organization
    if request.method == "POST":
        form = AgentTaskAssignForm(request.POST, organization=org)
        if form.is_valid():
            task = form.save(commit=False)
            task.organization = org
            task.created_by = request.user
            task.save()
            messages.success(request, f"Task assigned to {task.assigned_to.user.get_full_name() or task.assigned_to.user.username}.")
            return redirect("agent-portal-manage-tasks")
    else:
        form = AgentTaskAssignForm(organization=org)

    tasks = (
        AgentTask.objects.filter(organization=org)
        .select_related("assigned_to__user", "created_by")
        .order_by("is_done", "-created_at")[:200]
    )
    return render(
        request,
        "core/agent_portal/manage_tasks.html",
        {
            "membership": membership,
            "organization": org,
            "form": form,
            "tasks": tasks,
            "can_manage_tasks": True,
        },
    )


@login_required
@require_POST
def agent_portal_create_task(request):
    """Inline create from agent home for lead agents / owners."""
    membership = _resolve_portal_membership(request)
    if membership is None or not can_manage_agent_tasks(membership):
        deny_access("You do not have permission to assign agent tasks.")
    form = AgentTaskAssignForm(request.POST, organization=membership.organization)
    if form.is_valid():
        task = form.save(commit=False)
        task.organization = membership.organization
        task.created_by = request.user
        task.save()
        messages.success(request, "Task assigned.")
    else:
        messages.error(request, "Could not create task. Check the title and assignee.")
    return redirect("agent-portal-home")
