"""Application-wide request rate limits, grouped by how risky or expensive each route is."""

from __future__ import annotations

import re
import sys

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from rest_framework.throttling import AnonRateThrottle

from .ratelimit import (
    LOCKOUT_MESSAGE,
    clear_login_failures,
    client_ip,
    consume_rate_limit,
    ip_is_identifiable,
    login_locked,
    record_login_failure,
)

# (name, path regex, methods or None for all, limit, window seconds, keyed by user when signed in)
RATE_LIMIT_RULES = (
    ("auth", re.compile(r"^/(auth/(login|member-signup)|admin/login|contact)/"), {"POST"}, 10, 60, False),
    ("api_auth", re.compile(r"^/api/(auth|client/auth)/login/"), {"POST"}, 20, 60, False),
    ("public_sign", re.compile(r"^/sign/"), None, 30, 60, False),
    ("public_intake", re.compile(r"^/intake/"), None, 30, 60, False),
    ("export", re.compile(r"(\.pdf$|/pdf/?$|/export|/print|report)", re.IGNORECASE), {"GET"}, 40, 60, True),
    ("upload", re.compile(r"(upload|import|ocr)", re.IGNORECASE), {"POST"}, 30, 60, True),
    ("write", re.compile(r"."), {"POST", "PUT", "PATCH", "DELETE"}, 120, 60, True),
    ("global", re.compile(r"."), None, 600, 60, True),
)

EXEMPT_PREFIXES = ("/static/", "/media/", "/favicon", "/robots.txt", "/healthz")
ADMIN_LOGIN_PATH = "/admin/login/"


def rate_limiting_enabled() -> bool:
    configured = getattr(settings, "RATE_LIMIT_ENABLED", None)
    if configured is not None:
        return bool(configured)
    return "test" not in sys.argv


class LoginRateThrottle(AnonRateThrottle):
    """Tight per-IP limit for sign-in endpoints (rate from REST_FRAMEWORK DEFAULT_THROTTLE_RATES[scope])."""

    scope = "login"

    def allow_request(self, request, view):
        if not rate_limiting_enabled():
            return True
        return super().allow_request(request, view)


def _limited_response(request):
    message = "Too many requests. Please wait a minute and try again."
    wants_json = (
        request.path.startswith("/api/")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.META.get("HTTP_ACCEPT", "")
    )
    if wants_json:
        response = JsonResponse({"detail": message, "error": message}, status=429)
    else:
        response = HttpResponse(message, status=429, content_type="text/plain; charset=utf-8")
    response["Retry-After"] = "60"
    return response


class RateLimitMiddleware:
    """
    Every request counts against the first matching specific group plus the global group.

    Counters live in the shared Django cache (Redis in production) so limits hold across
    all gunicorn workers. A cache outage lets requests through rather than taking the site down.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(EXEMPT_PREFIXES):
            return self.get_response(request)

        if path == ADMIN_LOGIN_PATH and request.method == "POST":
            return self._admin_login(request)

        if rate_limiting_enabled() and not self._allowed(request, path):
            return _limited_response(request)
        return self.get_response(request)

    @staticmethod
    def _allowed(request, path):
        method = request.method.upper()
        user = getattr(request, "user", None)
        user_id = user.pk if user is not None and getattr(user, "is_authenticated", False) else None
        ip = client_ip(request)
        specific_checked = False
        for name, pattern, methods, limit, window, per_user in RATE_LIMIT_RULES:
            if methods is not None and method not in methods:
                continue
            if not pattern.search(path):
                continue
            if name != "global":
                if specific_checked:
                    continue
                specific_checked = True
            if per_user and user_id:
                who = f"u{user_id}"
            elif ip_is_identifiable(ip):
                who = f"ip{ip}"
            else:
                continue
            if not consume_rate_limit(f"mw:{name}:{who}", limit=limit, window_seconds=window):
                return False
        return True

    def _admin_login(self, request):
        username = (request.POST.get("username") or "").strip()
        if login_locked("admin", username, request):
            return HttpResponse(LOCKOUT_MESSAGE, status=429, content_type="text/plain; charset=utf-8")
        if rate_limiting_enabled() and not self._allowed(request, request.path):
            return _limited_response(request)
        response = self.get_response(request)
        if response.status_code == 302:
            clear_login_failures("admin", username, request)
        elif response.status_code == 200:
            record_login_failure("admin", username, request)
        return response
