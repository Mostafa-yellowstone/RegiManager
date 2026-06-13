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


def rate_limit(*, key_prefix, limit, window_seconds=60, json_response=False):
    """
    Decorator: allow `limit` requests per `window_seconds` per IP (+ user if authenticated).
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user_part = str(request.user.pk) if getattr(request.user, "is_authenticated", False) else "anon"
            raw = f"{key_prefix}:{user_part}:{client_ip(request)}"
            cache_key = "rl:" + hashlib.sha256(raw.encode()).hexdigest()[:32]
            count = cache.get(cache_key, 0)
            if count >= limit:
                message = "Too many requests. Please wait a moment and try again."
                if json_response:
                    return JsonResponse({"error": message}, status=429)
                return HttpResponse(message, status=429, content_type="text/plain")
            cache.set(cache_key, count + 1, timeout=window_seconds)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
