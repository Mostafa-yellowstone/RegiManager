"""Application-wide request rate limits, grouped by how risky or expensive each route is."""

from __future__ import annotations

import hashlib
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

# Background polling from open tabs (notification bell, session heartbeat, live channels, chat long-poll).
# These get their own bucket and never count toward the global limit, so idle tabs cannot lock a user out of pages.
POLL_PATH = re.compile(
    r"^/(api/(portal/(notifications|notifications/wait|events|quote-distribution)|session-heartbeat|client/chat/wait)/"
    r"|dashboard/clients/\d+/chat/wait/)"
)

def _segment(words):
    """Match a whole path segment built around one of `words` (`import-dec`, `kintone_import`), never `important-docs`."""
    return re.compile(rf"(^|/)([^/]*[-_])?({words})([-_][^/]*)?(/|$)", re.IGNORECASE)


# (name, path regex, methods or None for all, limit for anonymous visitors, limit for signed-in users,
#  window seconds, keyed by user when signed in)
# Signed-in limits are safety nets against runaway scripts; normal staff work, including bulk actions
# across many tabs, must never reach them. Anonymous limits stay tight because they guard against abuse.
RATE_LIMIT_RULES = (
    ("reset", re.compile(r"^/auth/(password-reset|reset/[^/]+/[^/]+)/"), {"POST"}, 10, 10, 60, False),
    ("auth", re.compile(r"^/(auth/(login|member-signup)|admin/login|contact)/"), {"POST"}, 20, 20, 60, False),
    ("api_auth", re.compile(r"^/api/(auth|client/auth)/login/"), {"POST"}, 20, 20, 60, False),
    ("poll", POLL_PATH, {"GET"}, 300, 900, 60, True),
    ("public_sign", re.compile(r"^/sign/"), None, 60, 60, 60, False),
    ("public_intake", re.compile(r"^/intake/"), None, 60, 60, 60, False),
    ("export", re.compile(r"\.pdf$|" + _segment("pdf|export|print").pattern, re.IGNORECASE), {"GET"}, 60, 180, 60, True),
    ("import", _segment("import|ocr"), {"POST"}, 30, 60, 60, True),
    ("upload", _segment("upload"), {"POST"}, 200, 400, 60, True),
    ("write", re.compile(r"."), {"POST", "PUT", "PATCH", "DELETE"}, 120, 400, 60, True),
    ("global", re.compile(r"."), None, 600, 1500, 60, True),
)
STANDALONE_RULES = {"poll"}
# Never echo these back into an auto-resubmitting page.
NO_RESUBMIT_RULES = {"reset", "auth", "api_auth"}
RESUBMIT_MAX_BYTES = 64 * 1024

logger = logging.getLogger(__name__)

EXEMPT_PREFIXES = ("/static/", "/media/", "/favicon", "/robots.txt", "/healthz")
ADMIN_LOGIN_PATH = "/admin/login/"
TOKEN_IDENTITY_TTL = 300


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


def _token_identity(request):
    """
    Bucket key for a valid API token (staff or client app), or None.

    Mobile carriers put many phones behind one IP, so token traffic must not share an IP bucket.
    Unknown tokens fall back to the IP bucket, so inventing tokens cannot buy fresh limits.
    """
    header = request.META.get("HTTP_AUTHORIZATION") or ""
    parts = header.split()
    if len(parts) != 2 or parts[0] not in ("Token", "Bearer") or len(parts[1]) > 200:
        return None
    token = parts[1]
    cache_key = "rl:tok:" + hashlib.sha256(token.encode()).hexdigest()[:32]
    try:
        cached = cache.get(cache_key)
    except Exception:
        cached = None
    if cached is not None:
        return cached or None

    identity = ""
    try:
        from rest_framework.authtoken.models import Token

        user_id = Token.objects.filter(key=token, user__is_active=True).values_list("user_id", flat=True).first()
        if user_id:
            identity = f"u{user_id}"
        else:
            from .models import ClientAppSession

            session_id = (
                ClientAppSession.objects.filter(token=token, revoked_at__isnull=True)
                .values_list("id", flat=True)
                .first()
            )
            if session_id:
                identity = f"c{session_id}"
    except Exception:
        return None
    try:
        cache.set(cache_key, identity, TOKEN_IDENTITY_TTL)
    except Exception:
        pass
    return identity or None


def _log_block(key, rule, who, method, path, limit, window):
    try:
        first = cache.add(f"rl:logged:{key}", 1, timeout=window + 5)
    except Exception:
        first = True
    if first:
        logger.warning(
            "Rate limit '%s' (%s per %ss) blocked %s on %s %s", rule, limit, window, who, method, path[:200]
        )


def _limited_response(request, retry_after=60, rule=""):
    retry_after = max(1, int(retry_after))
    message = "The server is busy. Please wait a few seconds and try again."
    accept = request.META.get("HTTP_ACCEPT", "")
    wants_json = (
        request.path.startswith("/api/")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in accept
    )
    if wants_json:
        response = JsonResponse(
            {"detail": message, "error": message, "retry_after": retry_after}, status=429
        )
    elif "text/html" in accept:
        response = HttpResponse(
            _retry_page(request, retry_after, rule), status=429, content_type="text/html; charset=utf-8"
        )
    else:
        response = HttpResponse(message, status=429, content_type="text/plain; charset=utf-8")
    response["Retry-After"] = str(retry_after)
    response["Cache-Control"] = "no-store"
    return response


def _resubmittable_fields(request, rule):
    """
    Form fields to send again automatically, or None.

    A blocked request never reached the view, so sending it again is safe. Only plain
    signed-in forms qualify: no sign-in forms (they carry passwords) and no file uploads.
    """
    if request.method != "POST" or rule in NO_RESUBMIT_RULES:
        return None
    if not getattr(getattr(request, "user", None), "is_authenticated", False):
        return None
    if request.content_type != "application/x-www-form-urlencoded":
        return None
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > RESUBMIT_MAX_BYTES:
            return None
        return [(key, value) for key in request.POST for value in request.POST.getlist(key)]
    except Exception:
        return None


def _retry_page(request, retry_after, rule=""):
    seconds = escape(str(retry_after))
    fields = _resubmittable_fields(request, rule)
    if request.method == "GET":
        head_extra = f"<meta http-equiv='refresh' content='{seconds}'>"
        body = f"<p>This page will load by itself in <b id='s'>{seconds}</b> seconds.</p>"
        finish = "location.reload();"
    elif fields is not None:
        head_extra = ""
        inputs = "".join(
            f"<input type='hidden' name='{escape(key)}' value='{escape(value)}'>" for key, value in fields
        )
        body = (
            f"<p>Nothing was lost. Your form will be sent again by itself in <b id='s'>{seconds}</b> seconds.</p>"
            f"<form id='f' method='post' action='{escape(request.get_full_path())}'>{inputs}</form>"
        )
        finish = "HTMLFormElement.prototype.submit.call(document.getElementById('f'));"
    else:
        head_extra = ""
        body = (
            "<p>Nothing was saved yet. Go back and submit again in <b id='s'>"
            f"{seconds}</b> seconds; your entries are still in the form.</p>"
            "<p><button type='button' onclick='history.back()'>Go back</button></p>"
        )
        finish = ""
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
        "var t=setInterval(function(){if(n>1){n--;s.textContent=n;return;}clearInterval(t);"
        f"{finish}"
        "},1000);})();</script></body></html>"
    )


class RateLimitMiddleware:
    """
    Every request counts against the first matching specific group plus the global group
    (background polling only counts against its own group).

    Counters live in the shared Django cache (Redis in production) so limits hold across
    all gunicorn workers. Windows are aligned to the clock, so Retry-After is exact.
    A cache outage lets requests through rather than taking the site down.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(EXEMPT_PREFIXES):
            return self.get_response(request)

        if path == ADMIN_LOGIN_PATH and request.method == "POST":
            return self._admin_login(request)

        if rate_limiting_enabled():
            retry_after, rule = self._check(request, path)
            if retry_after:
                return _limited_response(request, retry_after, rule)
        return self.get_response(request)

    @classmethod
    def _allowed(cls, request, path):
        return cls._check(request, path)[0] == 0

    @staticmethod
    def _identity(request, per_user, ip, token_identity):
        user = getattr(request, "user", None)
        if per_user:
            if user is not None and getattr(user, "is_authenticated", False):
                return f"u{user.pk}"
            if token_identity:
                return token_identity
        if ip_is_identifiable(ip):
            return f"ip{ip}"
        return None

    @classmethod
    def _check(cls, request, path):
        """(seconds until the caller may retry, rule name), or (0, "") when the request is allowed."""
        method = request.method.upper()
        ip = client_ip(request)
        token_identity = _token_identity(request) if path.startswith("/api/") else None
        now = time.time()
        specific_checked = False
        for name, pattern, methods, anon_limit, user_limit, window, per_user in RATE_LIMIT_RULES:
            if methods is not None and method not in methods:
                continue
            if not pattern.search(path):
                continue
            if name != "global":
                if specific_checked:
                    continue
                specific_checked = True
            who = cls._identity(request, per_user, ip, token_identity)
            if who is not None:
                limit = anon_limit if who.startswith("ip") else user_limit
                bucket = int(now // window)
                key = f"mw:{name}:{who}:{bucket}"
                if not consume_rate_limit(key, limit=limit, window_seconds=window + 5):
                    _log_block(key, name, who, method, path, limit, window)
                    return max(1, int(window - (now % window)) + 1), name
            if name in STANDALONE_RULES:
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
