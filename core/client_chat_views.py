"""Staff-facing client chat endpoints (CRM messenger on client profile)."""

from __future__ import annotations

import time

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from .access import has_active_org_access
from .client_chat import (
    list_chat_messages,
    mark_read_by_staff,
    post_staff_message,
    serialize_chat_message,
    unread_for_staff,
)
from .http import deny_access
from .models import Client, ClientChatMessage
from .realtime import wait_user_wake


@login_required
@require_GET
def client_chat_messages(request, client_id: int):
    client = get_object_or_404(Client, id=client_id)
    if not has_active_org_access(request.user, client.organization_id):
        deny_access("Access denied.")
    after_raw = (request.GET.get("after_id") or "").strip()
    after_id = int(after_raw) if after_raw.isdigit() else 0
    mark_read_by_staff(client)
    rows = list_chat_messages(client, after_id=after_id, limit=200)
    return JsonResponse(
        {
            "count": len(rows),
            "unread_count": unread_for_staff(client),
            "results": [serialize_chat_message(m) for m in rows],
        }
    )


@login_required
@require_http_methods(["POST"])
def client_chat_send(request, client_id: int):
    client = get_object_or_404(Client, id=client_id)
    if not has_active_org_access(request.user, client.organization_id):
        deny_access("Access denied.")
    body = (request.POST.get("body") or request.POST.get("message") or "").strip()
    if not body and request.content_type and "json" in request.content_type:
        try:
            import json

            data = json.loads(request.body.decode("utf-8") or "{}")
            body = (data.get("body") or data.get("message") or "").strip()
        except Exception:
            body = ""
    try:
        msg = post_staff_message(client, request.user, body)
    except ValueError as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)
    return JsonResponse({"status": "ok", "message": serialize_chat_message(msg)})


@login_required
@require_GET
def client_chat_wait(request, client_id: int):
    client = get_object_or_404(Client, id=client_id)
    if not has_active_org_access(request.user, client.organization_id):
        deny_access("Access denied.")
    after_raw = (request.GET.get("after_id") or "").strip()
    after_id = int(after_raw) if after_raw.isdigit() else 0
    mark_read = (request.GET.get("mark_read") or "").strip() in ("1", "true", "yes")
    try:
        timeout = int(request.GET.get("timeout") or 12)
    except (TypeError, ValueError):
        timeout = 12
    timeout = max(3, min(timeout, 20))

    def _fresh(after: int):
        qs = list(
            ClientChatMessage.objects.filter(client=client, id__gt=after)
            .select_related("staff_user", "client")
            .order_by("id")[:40]
        )
        return [serialize_chat_message(m) for m in qs]

    items = _fresh(after_id)
    if items:
        if mark_read:
            mark_read_by_staff(client)
        return JsonResponse(
            {
                "has_new": True,
                "results": items,
                "newest_id": items[-1]["id"],
                "unread_count": unread_for_staff(client),
            }
        )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # Short sleeps so DB is checked often even without Redis wake signals.
        wait_user_wake(request.user.id, timeout=min(1.2, max(0.2, deadline - time.monotonic())))
        items = _fresh(after_id)
        if items:
            if mark_read:
                mark_read_by_staff(client)
            return JsonResponse(
                {
                    "has_new": True,
                    "results": items,
                    "newest_id": items[-1]["id"],
                    "unread_count": unread_for_staff(client),
                }
            )
    return JsonResponse(
        {
            "has_new": False,
            "results": [],
            "newest_id": after_id,
            "unread_count": unread_for_staff(client),
        }
    )
