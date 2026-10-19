"""Lightweight cache-backed rate limiting and login lockout (no extra dependencies)."""

import hashlib
import ipaddress
import logging
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

logger = logging.getLogger(__name__)


def _is_proxy_address(value):
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private


def client_ip(request):
    """
    The visitor's address as seen by our own reverse proxy.

    Only the right-most X-Forwarded-For entries are added by proxies we run; anything to
    their left is whatever the visitor sent, so it must never be used for rate limiting.
    """
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    proxies = int(getattr(settings, "TRUSTED_PROXY_COUNT", 1) or 0)
    if proxies <= 0 or not _is_proxy_address(remote):
        return remote or "unknown"
    forwarded = [part.strip() for part in (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",") if part.strip()]
    if len(forwarded) >= proxies:
        return forwarded[-proxies]
    real_ip = (request.META.get("HTTP_X_REAL_IP") or "").strip()
    return real_ip or remote or "unknown"


def ip_is_identifiable(ip):
    """False when we only see our own proxy, so an IP bucket would be shared by every visitor."""
    return bool(ip) and ip != "unknown" and not _is_proxy_address(ip)


def _cache_key(prefix, raw_key):
    return f"{prefix}:" + hashlib.sha256(str(raw_key).encode()).hexdigest()[:32]


def consume_rate_limit(raw_key, *, limit, window_seconds):
    """
    Count one hit. Return True when the request is allowed.

    A cache outage must not take the page down, so any cache error allows
    the request through.
    """
    cache_key = _cache_key("rl", raw_key)
    try:
        if cache.add(cache_key, 1, timeout=window_seconds):
            return True
        try:
            count = cache.incr(cache_key)
        except ValueError:
            cache.add(cache_key, 1, timeout=window_seconds)
            return True
    except Exception:
        return True
    try:
        return int(count) <= int(limit)
    except (TypeError, ValueError):
        return True


def _too_many(json_response):
    message = "Please wait a minute, then try again."
    if json_response:
        response = JsonResponse({"error": message, "detail": message}, status=429)
    else:
        response = HttpResponse(message, status=429, content_type="text/plain")
    response["Retry-After"] = "60"
    return response


def rate_limit(*, key_prefix, limit, window_seconds=60, json_response=False, methods=None):
    """
    Decorator: allow `limit` requests per `window_seconds` per IP (+ user if authenticated).

    `methods` limits counting to those HTTP methods (e.g. {"POST"}); default counts every request.
    """
    counted = {m.upper() for m in methods} if methods else None

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if counted is None or request.method.upper() in counted:
                signed_in = getattr(request.user, "is_authenticated", False)
                ip = client_ip(request)
                if signed_in or ip_is_identifiable(ip):
                    user_part = str(request.user.pk) if signed_in else "anon"
                    raw = f"{key_prefix}:{user_part}:{ip}"
                    if not consume_rate_limit(raw, limit=limit, window_seconds=window_seconds):
                        return _too_many(json_response)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


LOCKOUT_MAX_FAILURES = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60


def _lockout_settings():
    return (
        int(getattr(settings, "LOGIN_LOCKOUT_MAX_FAILURES", LOCKOUT_MAX_FAILURES)),
        int(getattr(settings, "LOGIN_LOCKOUT_WINDOW_SECONDS", LOCKOUT_WINDOW_SECONDS)),
    )


def _lockout_keys(scope, identifier, request):
    ident = (identifier or "").strip().lower()
    keys = []
    if ident:
        keys.append(_cache_key("lock", f"{scope}:id:{ident}"))
    ip = client_ip(request)
    if ip_is_identifiable(ip) or getattr(settings, "DEBUG", False):
        keys.append(_cache_key("lock", f"{scope}:ip:{ip}"))
    return keys


def login_locked(scope, identifier, request):
    """True when this account or this IP has failed too many times recently."""
    max_failures, _window = _lockout_settings()
    try:
        values = cache.get_many(_lockout_keys(scope, identifier, request))
    except Exception:
        return False
    return any(int(v or 0) >= max_failures for v in values.values())


def record_login_failure(scope, identifier, request):
    _max, window = _lockout_settings()
    for key in _lockout_keys(scope, identifier, request):
        try:
            if not cache.add(key, 1, timeout=window):
                cache.incr(key)
        except Exception:
            pass
    logger.warning(
        "Failed %s login for %r from %s",
        scope,
        (identifier or "")[:80],
        client_ip(request),
    )


def clear_login_failures(scope, identifier, request):
    """Reset the account counter only; the IP counter keeps running so one valid login can't wipe it."""
    ident = (identifier or "").strip().lower()
    if not ident:
        return
    try:
        cache.delete(_cache_key("lock", f"{scope}:id:{ident}"))
    except Exception:
        pass


LOCKOUT_MESSAGE = "For your account's safety, sign-in is paused for 15 minutes after several wrong passwords."
