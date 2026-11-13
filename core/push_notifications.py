"""Expo push delivery for Pulse, so alerts reach the phone even when the app is closed."""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
ACTIVITY_CHANNEL_ID = "pulse-activity"
_BATCH_SIZE = 100


def _active_tokens(user_ids, organization_id):
    from django.db.models import Q

    from .models import MobilePushDevice

    return list(
        MobilePushDevice.objects.filter(user_id__in=list(user_ids), is_active=True)
        .filter(Q(organization_id=organization_id) | Q(organization__isnull=True))
        .values_list("token", flat=True)
        .distinct()
    )


def _deactivate(tokens):
    from .models import MobilePushDevice

    if tokens:
        MobilePushDevice.objects.filter(token__in=tokens).update(is_active=False)


def _deliver(messages):
    import requests

    dead = []
    for start in range(0, len(messages), _BATCH_SIZE):
        batch = messages[start : start + _BATCH_SIZE]
        try:
            response = requests.post(
                EXPO_PUSH_URL,
                json=batch,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=10,
            )
            tickets = (response.json() or {}).get("data") or []
        except Exception:
            logger.exception("Expo push request failed")
            continue
        for message, ticket in zip(batch, tickets):
            details = ticket.get("details") or {}
            if ticket.get("status") == "error" and details.get("error") == "DeviceNotRegistered":
                dead.append(message["to"])
    try:
        _deactivate(dead)
    except Exception:
        logger.exception("Could not deactivate unregistered push tokens")


def send_push(user_ids, *, organization_id, title: str, body: str, data: dict | None = None) -> int:
    """Queue a push to every active Pulse device of these users. Returns devices targeted."""
    if not getattr(settings, "PUSH_NOTIFICATIONS_ENABLED", True):
        return 0
    tokens = _active_tokens(set(user_ids), organization_id)
    if not tokens:
        return 0
    messages = [
        {
            "to": token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
            "priority": "high",
            "channelId": ACTIVITY_CHANNEL_ID,
        }
        for token in tokens
    ]
    transaction.on_commit(lambda: threading.Thread(target=_deliver, args=(messages,), daemon=True).start())
    return len(tokens)
