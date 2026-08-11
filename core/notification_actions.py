"""Safe portal notification action URLs and open routing helpers."""

from __future__ import annotations

from urllib.parse import urlparse

from django.urls import reverse


def is_safe_action_url(url: str) -> bool:
    """Allow only same-origin relative paths (no scheme, no // host)."""
    if not url or not isinstance(url, str):
        return False
    value = url.strip()
    if not value.startswith("/") or value.startswith("//"):
        return False
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return False
    return True


def task_board_action_url(*, task_id: int | None = None) -> str:
    base = reverse("agent-portal-tasks-board")
    if task_id:
        return f"{base}?task={int(task_id)}"
    return base


def quote_pipeline_action_url(*, space_id: int, lead_id: int | None = None) -> str:
    url = f"/dashboard/inventory/{int(space_id)}/?tab=quote-pipeline"
    if lead_id:
        url += f"&lead={int(lead_id)}"
    return url
