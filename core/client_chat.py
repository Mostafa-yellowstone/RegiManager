"""Client ↔ staff realtime chat helpers."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.urls import reverse

from .models import Client, ClientChatMessage, Notification, OrganizationMembership
from .realtime import publish_client_event, publish_user_event


def serialize_chat_message(msg: ClientChatMessage) -> dict:
    sender_name = ""
    if msg.sender_role == ClientChatMessage.SenderRole.STAFF and msg.staff_user_id:
        u = msg.staff_user
        sender_name = (u.get_full_name() or u.username or "Agent").strip()
    elif msg.sender_role == ClientChatMessage.SenderRole.CLIENT:
        sender_name = msg.client.full_display_name or msg.client.name or "Client"
    return {
        "id": msg.id,
        "client_id": msg.client_id,
        "sender_role": msg.sender_role,
        "sender_name": sender_name,
        "body": msg.body,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "is_read_by_staff": bool(msg.is_read_by_staff),
        "is_read_by_client": bool(msg.is_read_by_client),
    }


def list_chat_messages(client: Client, *, after_id: int = 0, limit: int = 100):
    qs = ClientChatMessage.objects.filter(client=client).select_related("staff_user", "client")
    if after_id:
        qs = qs.filter(id__gt=after_id).order_by("id")
    else:
        qs = qs.order_by("-id")[:limit]
        rows = list(qs)
        rows.reverse()
        return rows
    return list(qs[:limit])


def post_client_message(client: Client, body: str) -> ClientChatMessage:
    text = (body or "").strip()
    if not text:
        raise ValueError("Message cannot be empty.")
    if len(text) > 4000:
        text = text[:4000]
    msg = ClientChatMessage.objects.create(
        organization_id=client.organization_id,
        client=client,
        sender_role=ClientChatMessage.SenderRole.CLIENT,
        body=text,
        is_read_by_client=True,
        is_read_by_staff=False,
    )
    payload = serialize_chat_message(msg)
    publish_client_event(client.id, "chat.message", payload)
    _notify_org_staff(client, msg, payload)
    return msg


def post_staff_message(client: Client, staff_user: User, body: str) -> ClientChatMessage:
    text = (body or "").strip()
    if not text:
        raise ValueError("Message cannot be empty.")
    if len(text) > 4000:
        text = text[:4000]
    msg = ClientChatMessage.objects.create(
        organization_id=client.organization_id,
        client=client,
        sender_role=ClientChatMessage.SenderRole.STAFF,
        staff_user=staff_user,
        body=text,
        is_read_by_staff=True,
        is_read_by_client=False,
    )
    payload = serialize_chat_message(msg)
    # Fast path: wake the client app only. Other staff UIs poll the DB on their wait loop.
    publish_client_event(client.id, "chat.message", payload)
    return msg


def mark_read_by_staff(client: Client) -> int:
    return ClientChatMessage.objects.filter(
        client=client,
        sender_role=ClientChatMessage.SenderRole.CLIENT,
        is_read_by_staff=False,
    ).update(is_read_by_staff=True)


def mark_read_by_client(client: Client) -> int:
    return ClientChatMessage.objects.filter(
        client=client,
        sender_role=ClientChatMessage.SenderRole.STAFF,
        is_read_by_client=False,
    ).update(is_read_by_client=True)


def unread_for_staff(client: Client) -> int:
    return ClientChatMessage.objects.filter(
        client=client,
        sender_role=ClientChatMessage.SenderRole.CLIENT,
        is_read_by_staff=False,
    ).count()


def unread_for_client(client: Client) -> int:
    return ClientChatMessage.objects.filter(
        client=client,
        sender_role=ClientChatMessage.SenderRole.STAFF,
        is_read_by_client=False,
    ).count()


def _org_staff_user_ids(organization_id: int) -> list[int]:
    return list(
        OrganizationMembership.objects.filter(
            organization_id=organization_id,
            is_active=True,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )


def _notify_org_staff(client: Client, msg: ClientChatMessage, payload: dict) -> None:
    preview = (msg.body or "")[:140]
    title = f"Message from {client.full_display_name or client.name}"
    action_url = reverse("client-detail", args=[client.id]) + "#client-chat"
    staff_ids = _org_staff_user_ids(client.organization_id)[:40]
    if not staff_ids:
        return
    notifications = [
        Notification(
            user_id=uid,
            organization_id=client.organization_id,
            client=client,
            event_type="client_chat",
            title=title,
            message=preview,
            action_url=action_url,
            level=Notification.Level.INFO,
        )
        for uid in staff_ids
    ]
    created = Notification.objects.bulk_create(notifications)
    # Re-fetch ids if bulk_create didn't populate them on this DB backend
    if created and created[0].id is None:
        created = list(
            Notification.objects.filter(
                client=client,
                event_type="client_chat",
                title=title,
            ).order_by("-id")[: len(staff_ids)]
        )
        created.reverse()
    for notif in created:
        publish_user_event(
            notif.user_id,
            "notification",
            {
                "id": notif.id,
                "title": notif.title,
                "message": notif.message,
                "level": notif.level,
                "event_type": notif.event_type,
                "action_url": notif.action_url,
                "open_url": reverse("open-notification", args=[notif.id]),
                "is_read": False,
                "created_at": notif.created_at.isoformat() if notif.created_at else "",
                "created_label": notif.created_at.strftime("%b %d, %H:%M") if notif.created_at else "",
                "chat": payload,
            },
        )
