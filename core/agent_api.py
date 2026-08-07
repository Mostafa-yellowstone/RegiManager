"""Companion API — agent portal, owner team audit, attendance, tasks, timeline."""

from __future__ import annotations

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .agent_portal_models import AgentActivityEvent, AgentAttendanceSession, AgentTask
from .agent_portal_services import (
    activity_for_user,
    agent_workboard_payload,
    can_access_agent_portal,
    can_manage_agent_tasks,
    cairo_now,
    current_work_date,
    ensure_attendance_open,
    owner_can_review_agent,
    portal_now,
    shift_close_at,
    shift_open_at,
    task_progress_for_membership,
    today_activity_for_user,
    PORTAL_TZ,
)
from .models import OrganizationMembership, ServiceRecord, Notification
from .owner_api import ORG_HEADER, OwnerAPIBase


def _absolute_media_url(request, file_field) -> str | None:
    if not file_field:
        return None
    try:
        return request.build_absolute_uri(file_field.url)
    except Exception:
        return None


def _portal_iso(dt) -> str | None:
    """Serialize datetimes in America/New_York for companion clients."""
    if dt is None:
        return None
    return dt.astimezone(PORTAL_TZ).isoformat()


def _serialize_user_brief(user) -> dict:
    if user is None:
        return {}
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.get_full_name() or user.username,
        "email": user.email or "",
    }


def _serialize_task(task: AgentTask) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description or "",
        "status": task.status,
        "status_label": task.get_status_display(),
        "is_done": task.is_done,
        "completion_note": task.completion_note or "",
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "completed_at": _portal_iso(task.completed_at),
        "created_at": _portal_iso(task.created_at),
        "created_by": _serialize_user_brief(task.created_by),
        "assigned_to_id": task.assigned_to_id,
    }


def _serialize_task_progress(progress: dict) -> dict:
    tasks = progress.get("tasks") or []
    return {
        "total": progress.get("total", 0),
        "done": progress.get("done", 0),
        "open": progress.get("open", 0),
        "todo": progress.get("todo", 0),
        "in_progress": progress.get("in_progress", 0),
        "waiting": progress.get("waiting", 0),
        "percent": progress.get("percent", 0),
        "tasks": [_serialize_task(t) for t in tasks],
        "open_tasks": [_serialize_task(t) for t in progress.get("open_tasks", [])],
        "done_tasks": [_serialize_task(t) for t in progress.get("done_tasks", [])],
        "todo_tasks": [_serialize_task(t) for t in progress.get("todo_tasks", [])],
        "in_progress_tasks": [
            _serialize_task(t) for t in progress.get("in_progress_tasks", [])
        ],
        "waiting_tasks": [_serialize_task(t) for t in progress.get("waiting_tasks", [])],
        "stages": [
            {
                "key": stage["key"],
                "label": stage["label"],
                "count": stage["count"],
                "tasks": [_serialize_task(t) for t in stage.get("tasks", [])],
            }
            for stage in progress.get("stages", [])
        ],
    }


def _serialize_activity(event: AgentActivityEvent) -> dict:
    return {
        "id": event.id,
        "domain": event.domain,
        "event_type": event.event_type,
        "title": event.title,
        "detail": event.detail or "",
        "object_id": event.object_id,
        "created_at": _portal_iso(event.created_at),
    }


def _serialize_attendance(session: AgentAttendanceSession | None, *, work_date=None) -> dict | None:
    if session is None:
        return None
    wd = work_date or session.work_date
    open_at = shift_open_at(wd)
    close_at = shift_close_at(wd)
    return {
        "work_date": session.work_date.isoformat(),
        "opened_at": _portal_iso(session.opened_at),
        "closed_at": _portal_iso(session.closed_at),
        "is_open": session.is_open,
        "shift_open_at": _portal_iso(open_at),
        "shift_close_at": _portal_iso(close_at),
    }


def _agent_membership_queryset(organization):
    """Every active non-owner agent in the PSB (DMV, insurance, or both)."""
    return (
        OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
        )
        .exclude(role=OrganizationMembership.Role.OWNER)
        .select_related("user", "organization")
        .order_by("user__first_name", "user__last_name", "user__username")
    )


def _serialize_agent_summary(request, membership: OrganizationMembership) -> dict:
    user = membership.user
    progress = task_progress_for_membership(membership)
    work_date = current_work_date(portal_now())
    # Prefer today's session; never fall back to an older day (that looked like a false check-in).
    session = AgentAttendanceSession.objects.filter(
        membership=membership,
        work_date=work_date,
    ).first()
    today_events = today_activity_for_user(user, membership.organization)
    records = ServiceRecord.objects.filter(
        organization=membership.organization,
        handled_by=user,
        deleted_at__isnull=True,
    ).exclude(status="refund")
    totals = records.aggregate(
        total_records=Count("id"),
        total_revenue=Sum("service_fee"),
    )
    photo_url = _absolute_media_url(request, membership.profile_photo)
    return {
        "membership_id": membership.id,
        "user_id": user.id,
        "username": user.username,
        "full_name": user.get_full_name() or user.username,
        "email": user.email or "",
        "role": membership.role,
        "is_active": membership.is_active,
        "can_deal_with_insurance": membership.can_deal_with_insurance,
        "profile_photo_url": photo_url,
        "task_progress": {
            "total": progress["total"],
            "done": progress["done"],
            "open": progress["open"],
            "percent": progress["percent"],
        },
        "attendance": _serialize_attendance(session, work_date=work_date),
        "activity_today_count": len(today_events),
        "service_records_total": totals["total_records"] or 0,
        "service_revenue_total": str(totals["total_revenue"] or 0),
    }


class OwnerAgentsListView(OwnerAPIBase):
    """Owner roster with live task + attendance snapshot for all PSB agents."""

    def get(self, request):
        organization, membership, _orgs, _records, _today = self.resolve_context(
            request, require_owner=True
        )
        close_stale = True
        if close_stale:
            from .agent_portal_services import close_stale_attendance_sessions

            close_stale_attendance_sessions()
        # insurance_only is accepted for backwards compatibility but defaults off —
        # attendance/team is for the whole PSB.
        insurance_only = request.query_params.get("insurance_only", "").lower() in {
            "1",
            "true",
            "yes",
        }
        qs = _agent_membership_queryset(organization)
        if insurance_only:
            qs = qs.filter(can_deal_with_insurance=True)
        agents = [_serialize_agent_summary(request, m) for m in qs]
        return Response(
            {
                "organization": {
                    "id": organization.id,
                    "name": organization.name,
                },
                "work_date": current_work_date(cairo_now()).isoformat(),
                "cairo_now": portal_now().isoformat(),
                "local_now": portal_now().isoformat(),
                "agents": agents,
                "agent_count": len(agents),
            }
        )


class OwnerAgentWorkboardView(OwnerAPIBase):
    """Full workboard for one agent — tasks, timeline, attendance."""

    def get(self, request, membership_id: int):
        organization, viewer, _orgs, _records, _today = self.resolve_context(
            request, require_owner=True
        )
        agent = (
            OrganizationMembership.objects.filter(
                id=membership_id,
                organization=organization,
                is_active=True,
            )
            .select_related("user", "organization")
            .first()
        )
        if not agent:
            raise NotFound("Agent not found.")
        if not owner_can_review_agent(viewer, agent):
            raise PermissionDenied("You cannot review this agent.")

        workboard = agent_workboard_payload(agent, activity_limit=120)
        progress = workboard["progress"]
        attendance_session = workboard.get("attendance")
        if attendance_session is None:
            attendance_session = (
                AgentAttendanceSession.objects.filter(membership=agent)
                .order_by("-work_date")
                .first()
            )

        history = list(
            AgentAttendanceSession.objects.filter(membership=agent)
            .order_by("-work_date")[:14]
        )

        return Response(
            {
                "agent": _serialize_agent_summary(request, agent),
                "work_date": workboard["work_date"].isoformat(),
                "cairo_now": portal_now().isoformat(),
                "local_now": portal_now().isoformat(),
                "task_progress": _serialize_task_progress(progress),
                "today_activity": [
                    _serialize_activity(e) for e in workboard["today_activity"]
                ],
                "recent_activity": [
                    _serialize_activity(e) for e in workboard["recent_activity"]
                ],
                "attendance": _serialize_attendance(
                    attendance_session, work_date=workboard["work_date"]
                ),
                "attendance_history": [
                    _serialize_attendance(s) for s in history if s
                ],
            }
        )


class OwnerAgentCreateTaskView(OwnerAPIBase):
    def post(self, request, membership_id: int):
        organization, viewer, _orgs, _records, _today = self.resolve_context(
            request, require_owner=True
        )
        if not can_manage_agent_tasks(viewer):
            raise PermissionDenied("You cannot assign tasks.")

        agent = OrganizationMembership.objects.filter(
            id=membership_id,
            organization=organization,
            is_active=True,
        ).first()
        if not agent:
            raise NotFound("Agent not found.")

        title = (request.data.get("title") or "").strip()
        if not title:
            return Response(
                {"detail": "title is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        description = (request.data.get("description") or "").strip()
        due_date_raw = (request.data.get("due_date") or "").strip() or None
        due_date = None
        if due_date_raw:
            try:
                due_date = timezone.datetime.strptime(due_date_raw, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"detail": "due_date must be YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        task = AgentTask.objects.create(
            organization=organization,
            assigned_to=agent,
            created_by=request.user,
            title=title[:200],
            description=description,
            due_date=due_date,
        )
        Notification.objects.create(
            user=agent.user,
            organization=organization,
            event_type="agent_task_assigned",
            level=Notification.Level.INFO,
            title="New task assigned",
            message=title[:200],
        )
        return Response({"task": _serialize_task(task)}, status=status.HTTP_201_CREATED)


class MemberAPIBase(OwnerAPIBase):
    """Resolve org context for any active PSB agent (insurance or DMV)."""

    def resolve_active_member(self, request):
        organization, membership, _orgs, _records, _today = self.resolve_context(request)
        if membership.role == OrganizationMembership.Role.OWNER:
            raise PermissionDenied("This endpoint is for PSB agents, not owners.")
        if not membership.is_active:
            raise PermissionDenied("Inactive membership.")
        return organization, membership


class AgentAPIBase(OwnerAPIBase):
    """Resolve org + require insurance-agent portal access."""

    def resolve_agent_membership(self, request):
        organization, membership, _orgs, _records, _today = self.resolve_context(request)
        if not can_access_agent_portal(membership):
            raise PermissionDenied("Agent portal access required.")
        return organization, membership


class AgentPortalHomeView(AgentAPIBase):
    def get(self, request):
        organization, membership = self.resolve_agent_membership(request)
        session = ensure_attendance_open(membership)
        progress = task_progress_for_membership(membership)
        today_events = today_activity_for_user(membership.user, organization)
        work_date = current_work_date(cairo_now())

        return Response(
            {
                "membership_id": membership.id,
                "organization": {
                    "id": organization.id,
                    "name": organization.name,
                },
                "profile_photo_url": _absolute_media_url(request, membership.profile_photo),
                "work_date": work_date.isoformat(),
                "cairo_now": portal_now().isoformat(),
                "local_now": portal_now().isoformat(),
                "attendance": _serialize_attendance(session, work_date=work_date),
                "task_progress": _serialize_task_progress(progress),
                "today_activity": [_serialize_activity(e) for e in today_events],
            }
        )


class AgentTasksView(AgentAPIBase):
    def get(self, request):
        _organization, membership = self.resolve_agent_membership(request)
        status_filter = (request.query_params.get("status") or "all").lower()
        progress = task_progress_for_membership(membership)
        if status_filter == "open":
            progress = {
                **progress,
                "tasks": progress["open_tasks"],
            }
        elif status_filter == "done":
            progress = {
                **progress,
                "tasks": progress["done_tasks"],
            }
        return Response(_serialize_task_progress(progress))


class AgentToggleTaskView(AgentAPIBase):
    def post(self, request, task_id: int):
        _organization, membership = self.resolve_agent_membership(request)
        task = AgentTask.objects.filter(
            id=task_id,
            assigned_to=membership,
        ).first()
        if not task:
            raise NotFound("Task not found.")

        status_raw = (request.data.get("status") or "").strip().lower()
        note = request.data.get("completion_note")
        if note is None:
            note = request.data.get("note")

        note_required = {
            AgentTask.Status.IN_PROGRESS,
            AgentTask.Status.WAITING,
            AgentTask.Status.DONE,
        }

        if status_raw:
            if status_raw in note_required and not (note or "").strip():
                return Response(
                    {
                        "detail": "completion_note is required for in_progress, waiting, and done."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                task.set_status(
                    status_raw,
                    note=(note if note is not None else None),
                )
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            done = request.data.get("is_done")
            if done is None:
                done = request.data.get("done")
            if done is None:
                target_done = not task.is_done
            else:
                target_done = bool(done)
            if target_done and not (note or "").strip():
                return Response(
                    {"detail": "completion_note is required when marking done."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            task.mark_done(done=target_done, note=note if note is not None else None)

        progress = task_progress_for_membership(membership)
        return Response(
            {
                "ok": True,
                "task": _serialize_task(task),
                "progress": {
                    "total": progress["total"],
                    "done": progress["done"],
                    "open": progress["open"],
                    "todo": progress.get("todo", 0),
                    "in_progress": progress.get("in_progress", 0),
                    "waiting": progress.get("waiting", 0),
                    "percent": progress["percent"],
                },
            }
        )


class AgentActivityView(AgentAPIBase):
    def get(self, request):
        organization, membership = self.resolve_agent_membership(request)
        scope = (request.query_params.get("scope") or "today").lower()
        limit = min(int(request.query_params.get("limit") or 80), 200)
        if scope == "recent":
            from datetime import timedelta

            local_now = cairo_now()
            start = (local_now - timedelta(days=14)).date()
            events = activity_for_user(
                membership.user,
                organization,
                start=start,
                end=local_now.date(),
                limit=limit,
            )
        else:
            events = today_activity_for_user(membership.user, organization)
        return Response({"events": [_serialize_activity(e) for e in events]})


class AgentAttendanceView(MemberAPIBase):
    def get(self, request):
        _organization, membership = self.resolve_active_member(request)
        session = ensure_attendance_open(membership)
        history = list(
            AgentAttendanceSession.objects.filter(membership=membership)
            .order_by("-work_date")[:30]
        )
        work_date = current_work_date(cairo_now())
        return Response(
            {
                "work_date": work_date.isoformat(),
                "cairo_now": portal_now().isoformat(),
                "local_now": portal_now().isoformat(),
                "current": _serialize_attendance(session, work_date=work_date),
                "history": [_serialize_attendance(s) for s in history if s],
            }
        )


class MobilePushDeviceRegisterView(APIView):
    """Register FCM/APNs token for background work alerts."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .models import MobilePushDevice

        token = (request.data.get("token") or "").strip()
        platform = (request.data.get("platform") or "android").strip().lower()
        if not token:
            return Response(
                {"detail": "token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        org_header = request.META.get(ORG_HEADER)
        organization_id = int(org_header) if org_header and str(org_header).isdigit() else None

        device, _created = MobilePushDevice.objects.update_or_create(
            user=request.user,
            token=token,
            defaults={
                "platform": platform,
                "organization_id": organization_id,
                "is_active": True,
            },
        )
        return Response(
            {
                "id": device.id,
                "platform": device.platform,
                "registered": True,
            }
        )
