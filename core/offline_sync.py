"""
Server side of the browser offline queue.

The service worker tags every write with an X-Idempotency-Key and replays it after an outage, so the
same key may arrive more than once. The first request that finishes below 400 wins; later copies get
an "already applied" answer instead of running the view again. Database outages become a retryable
503 so the browser keeps the change queued instead of treating it as a bug.
"""

import hashlib
import re
import sys

from django.conf import settings
from django.core.cache import cache
from django.core.signals import got_request_exception
from django.db.utils import InterfaceError, OperationalError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
IDEMPOTENCY_HEADER = "X-Idempotency-Key"
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
PENDING_TTL_SECONDS = 10 * 60
OUTAGE_RETRY_AFTER_SECONDS = 30
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{16,100}$")
_DB_OUTAGE_ATTR = "_regi_db_unavailable"
_PENDING = "pending"
_DONE = "done"


def offline_queue_enabled():
    return bool(getattr(settings, "OFFLINE_QUEUE_ENABLED", True))


def _wants_json(request):
    accept = request.META.get("HTTP_ACCEPT", "")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    if request.headers.get("X-Offline-Replay"):
        return True
    if "application/json" in accept and "text/html" not in accept:
        return True
    return request.path.startswith("/api/")


def _retryable(response, retry_after):
    response["X-Regi-Retryable"] = "1"
    response["X-Regi-Error-Page"] = "1"
    response["Retry-After"] = str(retry_after)
    response["Cache-Control"] = "no-store"
    return response


def _outage_response(request):
    message = "The server is temporarily unavailable. Your change was not lost; it will be retried."
    if _wants_json(request):
        response = JsonResponse({"ok": False, "retryable": True, "detail": message}, status=503)
    else:
        response = HttpResponse(
            "<!doctype html><meta charset='utf-8'><title>Temporarily unavailable</title>"
            "<body style='font-family:system-ui,sans-serif;max-width:560px;margin:15vh auto;padding:0 1rem'>"
            f"<h1>Temporarily unavailable</h1><p>{message}</p>"
            "<p><a href='javascript:history.back()'>Go back</a></p></body>",
            status=503,
        )
    return _retryable(response, OUTAGE_RETRY_AFTER_SECONDS)


def _is_db_outage(exc):
    return isinstance(exc, (OperationalError, InterfaceError))


def _mark_db_outage(sender=None, request=None, **kwargs):
    if request is not None and _is_db_outage(sys.exc_info()[1]):
        setattr(request, _DB_OUTAGE_ATTR, True)


got_request_exception.connect(_mark_db_outage, dispatch_uid="regi_offline_sync_db_outage")


def _cache_key(raw_key):
    return "idem:" + hashlib.sha256(raw_key.encode()).hexdigest()


class OfflineSyncMiddleware:
    """Outermost layer: idempotent replays plus database-outage -> retryable 503."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_key = (request.headers.get(IDEMPOTENCY_HEADER) or "").strip()
        if request.method not in UNSAFE_METHODS or not _KEY_PATTERN.match(raw_key):
            return self._process(request)

        cache_key = _cache_key(raw_key)
        try:
            claimed = cache.add(cache_key, _PENDING, timeout=PENDING_TTL_SECONDS)
            state = None if claimed else cache.get(cache_key)
        except Exception:
            claimed, state = True, None

        if not claimed and state == _DONE:
            response = JsonResponse({"ok": True, "duplicate": True, "detail": "This change was already saved."})
            response["X-Idempotent-Replay"] = "1"
            return response
        if not claimed and state == _PENDING:
            response = JsonResponse(
                {"ok": False, "retryable": True, "detail": "This change is still being saved."}, status=409
            )
            return _retryable(response, 5)

        response = self._process(request)
        try:
            if response.status_code < 400:
                cache.set(cache_key, _DONE, timeout=IDEMPOTENCY_TTL_SECONDS)
            else:
                cache.delete(cache_key)
        except Exception:
            pass
        return response

    def _process(self, request):
        response = self.get_response(request)
        if response.status_code >= 500 and getattr(request, _DB_OUTAGE_ATTR, False):
            return _outage_response(request)
        return response


class DatabaseOutageMarkerMiddleware:
    """Listed last so its process_exception sees view errors before FriendlyErrorMiddleware renders them."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if _is_db_outage(exception):
            setattr(request, _DB_OUTAGE_ATTR, True)
            return _outage_response(request)
        return None


@require_GET
@never_cache
def service_worker(request):
    response = render(
        request,
        "core/offline_sw.js",
        {"offline_queue_enabled": offline_queue_enabled()},
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/"
    return response
