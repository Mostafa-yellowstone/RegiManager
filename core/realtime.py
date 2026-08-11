"""Realtime fan-out for portal notifications and Quote Pipeline boards.

Uses Redis Pub/Sub when available (CELERY_BROKER_URL / REDIS_CACHE_URL).
Falls back to an in-process bus for local DEBUG without Redis.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

_USER_CHANNEL = "rm:user:{user_id}:events"
_ORG_QUOTE_CHANNEL = "rm:org:{org_id}:quote_pipeline"

_local_lock = threading.Lock()
_local_subs: dict[str, list[Callable[[dict], None]]] = defaultdict(list)


def _redis_url() -> str:
    return (
        os.getenv("REDIS_CACHE_URL")
        or os.getenv("CELERY_BROKER_URL")
        or "redis://127.0.0.1:6379/0"
    )


def _get_redis():
    try:
        import redis

        client = redis.Redis.from_url(_redis_url(), decode_responses=True)
        client.ping()
        return client
    except Exception as exc:
        logger.debug("Realtime Redis unavailable: %s", exc)
        return None


def user_channel(user_id: int) -> str:
    return _USER_CHANNEL.format(user_id=int(user_id))


def org_quote_channel(org_id: int) -> str:
    return _ORG_QUOTE_CHANNEL.format(org_id=int(org_id))


def _encode(event_type: str, payload: dict[str, Any]) -> str:
    body = {"type": event_type, "payload": payload or {}, "ts": int(time.time())}
    return json.dumps(body, default=str)


def _decode(raw: str) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("type"):
        return None
    return data


def publish(channel: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
    message = _encode(event_type, payload or {})
    client = _get_redis()
    if client is not None:
        try:
            client.publish(channel, message)
            return
        except Exception:
            logger.exception("Failed publishing realtime event to Redis")

    with _local_lock:
        listeners = list(_local_subs.get(channel, []))
    for cb in listeners:
        try:
            cb(_decode(message) or {})
        except Exception:
            logger.exception("Local realtime listener failed")


def publish_user_event(user_id: int, event_type: str, payload: dict[str, Any] | None = None) -> None:
    if not user_id:
        return
    publish(user_channel(user_id), event_type, payload)


def publish_org_quote_event(org_id: int, event_type: str, payload: dict[str, Any] | None = None) -> None:
    if not org_id:
        return
    publish(org_quote_channel(org_id), event_type, payload)


def iter_events(channels: list[str], *, heartbeat_seconds: float = 15.0) -> Iterator[dict[str, Any] | None]:
    """Yield event dicts, or None for heartbeats. Stops when generator is closed."""
    channels = [c for c in channels if c]
    if not channels:
        while True:
            yield None
            time.sleep(heartbeat_seconds)

    client = _get_redis()
    if client is not None:
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        try:
            pubsub.subscribe(*channels)
            deadline = time.monotonic() + heartbeat_seconds
            while True:
                remaining = max(0.05, deadline - time.monotonic())
                msg = pubsub.get_message(timeout=remaining)
                if msg and msg.get("type") == "message":
                    data = _decode(msg.get("data") or "")
                    if data:
                        yield data
                        deadline = time.monotonic() + heartbeat_seconds
                        continue
                if time.monotonic() >= deadline:
                    yield None
                    deadline = time.monotonic() + heartbeat_seconds
        finally:
            try:
                pubsub.close()
            except Exception:
                pass
        return

    queue: list[dict[str, Any]] = []
    q_lock = threading.Lock()
    wake = threading.Event()

    def _on_event(data: dict[str, Any]):
        with q_lock:
            queue.append(data)
        wake.set()

    with _local_lock:
        for ch in channels:
            _local_subs[ch].append(_on_event)

    try:
        while True:
            woke = wake.wait(timeout=heartbeat_seconds)
            wake.clear()
            batch: list[dict[str, Any]] = []
            with q_lock:
                if queue:
                    batch, queue = queue, []
            if batch:
                for item in batch:
                    yield item
            elif not woke:
                yield None
    finally:
        with _local_lock:
            for ch in channels:
                try:
                    _local_subs[ch].remove(_on_event)
                except ValueError:
                    pass
