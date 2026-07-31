import logging

from django.conf import settings
from django.contrib.auth import logout
from django.contrib import messages

from .error_handlers import log_server_exception, render_error_page
from .models import UserSession

logger = logging.getLogger(__name__)

PLAIN_ERROR_MARKERS = (
    b"Access denied.",
    b"Forbidden",
    b"Not Found",
    b"Internal Server Error",
    b"Bad Gateway",
    b"Service Unavailable",
)

# Django technical 404/500 pages — must never be shown to browsers in production.
DEBUG_LEAK_MARKERS = (
    b"Page not found (404)",
    b"Django tried these URL patterns",
    b"urlpatterns",
    b"URLconf",
    b"Request Method:",
    b"Exception Type:",
    b"Traceback ",
)


class FriendlyErrorMiddleware:
    """
    Replace plain-text/HTML error responses with branded error pages for browser requests.
    Catches unhandled exceptions in production and renders a safe 500 screen.
    """

    TRANSFORM_STATUSES = {400, 403, 404, 500, 502, 503}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except Exception as exc:
            from django.core.exceptions import PermissionDenied
            from django.core.handlers.exception import response_for_exception
            from django.http import Http404

            if isinstance(exc, (PermissionDenied, Http404)):
                return response_for_exception(request, exc)
            handled = self.process_exception(request, exc)
            if handled is not None:
                return handled
            raise

        if response.get("X-Regi-Error-Page"):
            return response
        if response.status_code not in self.TRANSFORM_STATUSES:
            return response
        if self._wants_json(request):
            return response
        if not self._should_replace(response):
            return response
        return render_error_page(request, response.status_code)

    def process_exception(self, request, exception):
        from django.core.exceptions import PermissionDenied
        from django.core.handlers.exception import response_for_exception
        from django.http import Http404

        if isinstance(exception, (PermissionDenied, Http404)):
            return response_for_exception(request, exception)
        if settings.DEBUG:
            return None
        log_server_exception(request, exception)
        if self._wants_json(request):
            from django.http import JsonResponse

            return JsonResponse(
                {"status": "error", "code": 500, "message": "Internal server error."},
                status=500,
            )
        return render_error_page(request, 500)

    @staticmethod
    def _wants_json(request):
        accept = request.META.get("HTTP_ACCEPT", "")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return True
        if "application/json" in accept and "text/html" not in accept:
            return True
        return request.path.startswith("/api/")

    @staticmethod
    def _should_replace(response):
        content = response.content or b""
        if any(marker in content for marker in DEBUG_LEAK_MARKERS):
            return True
        if response.status_code == 404:
            # Never expose Django's debug URL listing for mistyped paths.
            return True
        if len(content) < 4096:
            return True
        return any(marker in content[:500] for marker in PLAIN_ERROR_MARKERS)


class SingleSessionMiddleware:
    """
    Enterprise Security Middleware:
    Ensures only one device/session can be active per user at a time.

    Uses the database-backed UserSession model (not LocMemCache) so it
    works correctly on multi-worker production servers (gunicorn).

    Flow:
      1. User logs in → user_logged_in signal stores session key in
         UserSession AND deletes the old session from the Session table.
      2. On every request, this middleware checks whether the current
         session key matches the one stored in UserSession.
      3. If it doesn't match, the user was displaced by a login on
         another device → log them out with a clear message.
      4. If no UserSession record exists (first request after a cold
         start, or a race condition), we simply skip the check — the
         login signal will create the record on next login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            session_key = request.session.session_key
            if session_key:
                try:
                    active = UserSession.objects.get(user=request.user)
                    if active.session_key != session_key:
                        # Another device logged in — this session is stale.
                        logout(request)
                        messages.warning(
                            request,
                            "You were signed out because your account was accessed "
                            "from another device or browser. Please sign in again."
                        )
                except UserSession.DoesNotExist:
                    # No record yet (edge case) — don't block the user.
                    pass

        response = self.get_response(request)
        return response


class PortalTimezoneMiddleware:
    """Activate the user's local timezone for dates/times shown in the portal."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.utils import timezone

        from .models import Organization, OrganizationMembership
        from .timezone_utils import is_valid_timezone, resolve_portal_timezone_name

        # Open NY attendance for any active agent on first authenticated hit today.
        # Covers agents already signed in (website/app) who never re-login.
        self._ensure_agent_attendance(request)

        tz_name = None
        session_tz = request.session.get("portal_timezone")
        if session_tz and is_valid_timezone(session_tz):
            tz_name = session_tz.strip()
        else:
            organization = None
            active_org_id = request.session.get("active_org_id")
            if active_org_id and getattr(request, "user", None) and request.user.is_authenticated:
                organization = Organization.objects.filter(
                    pk=active_org_id,
                    is_active=True,
                ).only("state").first()
            elif getattr(request, "user", None) and request.user.is_authenticated:
                membership = (
                    OrganizationMembership.objects.filter(
                        user=request.user,
                        is_active=True,
                        organization__is_active=True,
                    )
                    .select_related("organization")
                    .first()
                )
                organization = membership.organization if membership else None
            tz_name = resolve_portal_timezone_name(organization=organization)

        if tz_name and is_valid_timezone(tz_name):
            timezone.activate(tz_name)
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()

    @staticmethod
    def _ensure_agent_attendance(request):
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return
        if getattr(user, "is_superuser", False):
            return
        # Once per NY work-date per session (website). Token API uses CompanionMeView.
        session = getattr(request, "session", None)
        try:
            from .agent_portal_services import (
                current_work_date,
                portal_now,
                shift_open_at,
                start_attendance_on_login,
            )

            now = portal_now()
            work_date = current_work_date(now)
            # Before 9 AM New York: do not mark the day done — retry after shift opens.
            if now < shift_open_at(work_date):
                return
            work_key = f"attendance_opened_{work_date.isoformat()}"
            if session is not None and session.get(work_key):
                return
            start_attendance_on_login(user)
            if session is not None:
                session[work_key] = True
        except Exception:
            logger.exception("Failed to open agent attendance for user_id=%s", getattr(user, "id", None))
