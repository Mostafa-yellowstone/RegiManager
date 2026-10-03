"""Lightweight cache-backed rate limiting (no extra dependencies)."""

import hashlib
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def consume_rate_limit(raw_key, *, limit, window_seconds):
    """
    Count one hit. Return True when the request is allowed.

    A cache outage must not take the page down, so any cache error allows
    the request through.
    """
    cache_key = "rl:" + hashlib.sha256(str(raw_key).encode()).hexdigest()[:32]
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


def rate_limit(*, key_prefix, limit, window_seconds=60, json_response=False):
    """
    Decorator: allow `limit` requests per `window_seconds` per IP (+ user if authenticated).
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user_part = str(request.user.pk) if getattr(request.user, "is_authenticated", False) else "anon"
            raw = f"{key_prefix}:{user_part}:{client_ip(request)}"
            if not consume_rate_limit(raw, limit=limit, window_seconds=window_seconds):
                message = "Too many requests. Please wait a moment and try again."
                if json_response:
                    return JsonResponse({"error": message}, status=429)
                return HttpResponse(message, status=429, content_type="text/plain")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
