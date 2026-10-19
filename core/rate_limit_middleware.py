"""
Request limits for the few public forms strangers can abuse (sign-in, password reset, sign-up, contact).

Signed-in staff, app tokens, pages, APIs, uploads, exports and background polling are never limited:
the site must not turn a real user away. Password guessing is still stopped here and by the
per-account lockout in core.ratelimit.
"""

from __future__ import annotations

import logging
import re
import sys
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils.html import escape
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

# (name, path regex, limit per IP, window seconds); POST only, anonymous visitors only.
RATE_LIMIT_RULES = (
    ("reset", re.compile(r"^/auth/(password-reset|reset/[^/]+/[^/]+)/"), 10, 60),
    ("auth", re.compile(r"^/(auth/(login|member-signup)|admin/login|contact)/"), 20, 60),
    ("api_auth", re.compile(r"^/api/(auth|client/auth)/login/"), 20, 60),
)

logger = logging.getLogger(__name__)

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


def _log_block(key, rule, ip, path, limit, window):
    try:
        first = cache.add(f"rl:logged:{key}", 1, timeout=window + 5)
    except Exception:
        first = True
    if first:
        logger.warning("Rate limit '%s' (%s per %ss) paused %s on POST %s", rule, limit, window, ip, path[:200])


def _limited_response(request, retry_after=60, rule=""):
    retry_after = max(1, int(retry_after))
    message = f"Please wait {retry_after} seconds, then try again."
    accept = request.META.get("HTTP_ACCEPT", "")
    wants_json = (
        request.path.startswith("/api/")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in accept
    )
    if wants_json:
        response = JsonResponse({"detail": message, "error": message, "retry_after": retry_after}, status=429)
    elif "text/html" in accept:
        response = HttpResponse(_wait_page(request, retry_after), status=429, content_type="text/html; charset=utf-8")
    else:
        response = HttpResponse(message, status=429, content_type="text/plain; charset=utf-8")
    response["Retry-After"] = str(retry_after)
    response["Cache-Control"] = "no-store"
    return response


def _wait_page(request, retry_after):
    seconds = escape(str(retry_after))
    if request.method == "GET":
        head_extra = f"<meta http-equiv='refresh' content='{seconds}'>"
        body = f"<p>This page will load by itself in <b id='s'>{seconds}</b> seconds.</p>"
    else:
        head_extra = ""
        body = (
            f"<p>For your account's safety, please wait <b id='s'>{seconds}</b> seconds, then go back and try again.</p>"
            "<p><button type='button' onclick='history.back()'>Go back</button></p>"
        )
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"{head_extra}"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>One moment</title>"
        "<style>body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f8fafc;color:#0f172a;"
        "display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}"
        ".card{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:2rem 2.25rem;max-width:420px;"
        "text-align:center;box-shadow:0 10px 30px rgba(15,23,42,.06)}h1{font-size:1.25rem;margin:0 0 .5rem}"
        "p{color:#475569;line-height:1.5;margin:0 0 .75rem}button{font:inherit;font-weight:600;border:0;"
        "border-radius:10px;padding:.6rem 1.2rem;background:#2563eb;color:#fff;cursor:pointer}</style></head>"
        "<body><div class='card'><h1>One moment, please</h1>"
        f"{body}"
        "</div><script>(function(){var s=document.getElementById('s'),n=parseInt(s.textContent,10);"
        "var t=setInterval(function(){if(n>1){n--;s.textContent=n;return;}clearInterval(t);},1000);})();"
        "</script></body></html>"
    )


class RateLimitMiddleware:
    """
    Per-IP limits on public sign-in style forms only.

    Counters live in the shared Django cache (Redis in production) so limits hold across
    all gunicorn workers. A cache outage lets every request through.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path == ADMIN_LOGIN_PATH:
            return self._admin_login(request)
        if request.method == "POST" and rate_limiting_enabled():
            retry_after, rule = self._check(request, request.path)
            if retry_after:
                return _limited_response(request, retry_after, rule)
        return self.get_response(request)

    @classmethod
    def _allowed(cls, request, path):
        return cls._check(request, path)[0] == 0

    @staticmethod
    def _check(request, path):
        """(seconds until the caller may retry, rule name), or (0, "") when the request is allowed."""
        if request.method.upper() != "POST":
            return 0, ""
        if getattr(getattr(request, "user", None), "is_authenticated", False):
            return 0, ""
        ip = client_ip(request)
        if not ip_is_identifiable(ip):
            return 0, ""
        now = time.time()
        for name, pattern, limit, window in RATE_LIMIT_RULES:
            if not pattern.search(path):
                continue
            key = f"mw:{name}:ip{ip}:{int(now // window)}"
            if not consume_rate_limit(key, limit=limit, window_seconds=window + 5):
                _log_block(key, name, ip, path, limit, window)
                return max(1, int(window - (now % window)) + 1), name
            break
        return 0, ""

    def _admin_login(self, request):
        username = (request.POST.get("username") or "").strip()
        if login_locked("admin", username, request):
            return HttpResponse(LOCKOUT_MESSAGE, status=429, content_type="text/plain; charset=utf-8")
        if rate_limiting_enabled():
            retry_after, rule = self._check(request, request.path)
            if retry_after:
                return _limited_response(request, retry_after, rule)
        response = self.get_response(request)
        if response.status_code == 302:
            clear_login_failures("admin", username, request)
        elif response.status_code == 200:
            record_login_failure("admin", username, request)
        return response
