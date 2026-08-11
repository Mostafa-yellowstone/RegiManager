"""Portal realtime SSE + notification/pipeline snapshot APIs."""

from __future__ import annotations

import json
import time

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .access import organizations_for_user
from .insurance_quote_permissions import can_view_quote_pipeline, membership_for_org
from .insurance_quote_pipeline_views import build_quote_pipeline_context
from .models import Notification, Organization
from .realtime import iter_events, org_quote_channel, user_channel


def _serialize_notification(n: Notification) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "message": n.message or "",
        "level": n.level,
        "event_type": n.event_type or "",
        "action_url": n.action_url or "",
        "open_url": reverse("open-notification", args=[n.id]),
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else "",
        "created_label": n.created_at.strftime("%b %d, %H:%M") if n.created_at else "",
    }


@login_required
@require_GET
def portal_notifications_snapshot(request):
    qs = Notification.objects.filter(user=request.user).order_by("-created_at")[:20]
    unread = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse(
        {
            "notifications": [_serialize_notification(n) for n in qs],
            "unread_count": unread,
        }
    )


@login_required
@require_GET
def portal_quote_pipeline_snapshot(request):
    org_id = request.GET.get("org") or request.session.get("active_org_id")
    orgs = organizations_for_user(request)
    org = orgs.filter(id=org_id).first() if org_id else orgs.first()
    if org is None:
        return JsonResponse({"error": "organization_required"}, status=400)
    membership = membership_for_org(request.user, org)
    if not can_view_quote_pipeline(request.user, org, membership=membership):
        return JsonResponse({"error": "forbidden"}, status=403)

    ctx = build_quote_pipeline_context(request, org, membership)
    html = render(
        request,
        "core/partials/insurance_quote_pipeline_live.html",
        ctx,
    ).content.decode("utf-8")
    return JsonResponse({"html": html, "org_id": org.id})


@login_required
@require_GET
def portal_events_stream(request):
    """Server-Sent Events stream for the authenticated portal user."""
    channels = [user_channel(request.user.id)]
    org_id = (request.GET.get("org") or "").strip()
    if org_id.isdigit():
        org = Organization.objects.filter(id=int(org_id)).first()
        if org is not None:
            membership = membership_for_org(request.user, org)
            if can_view_quote_pipeline(request.user, org, membership=membership):
                channels.append(org_quote_channel(org.id))

    def event_stream():
        yield f": connected {int(time.time())}\n\n"
        for item in iter_events(channels, heartbeat_seconds=15.0):
            if item is None:
                yield f": ping {int(time.time())}\n\n"
                continue
            event_type = item.get("type") or "message"
            payload = item.get("payload") or {}
            data = json.dumps(
                {"type": event_type, "payload": payload, "ts": item.get("ts")},
                default=str,
            )
            yield f"event: {event_type}\ndata: {data}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["X-Accel-Buffering"] = "no"
    return response
