"""Branded HTTP error pages for RegiManager."""

import logging

from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)

ERROR_META = {
    400: {
        "title": "Bad Request",
        "headline": "We couldn't process that request.",
        "summary": "The server received data it couldn't understand. This is usually a form or link issue, not a system failure.",
        "solutions": [
            "Go back and submit the form again without refreshing during save.",
            "Clear any unusual characters from required fields (VIN, phone, amounts).",
            "If you used the browser back button, reopen the page from the Dashboard.",
        ],
        "icon": "⚠️",
    },
    403: {
        "title": "Access Denied",
        "headline": "You don't have permission for this area.",
        "summary": "Your account is signed in, but this action or page isn't enabled for your role.",
        "solutions": [
            "Return to the Dashboard and open the section your owner assigned to you.",
            "Ask your PSB owner to enable the permission (reports, banking, insurance, etc.).",
            "If you were signed out on another device, sign in again and retry once.",
        ],
        "icon": "🔒",
    },
    404: {
        "title": "Page Not Found",
        "headline": "This page doesn't exist or was moved.",
        "summary": "The link may be outdated, mistyped, or the record may have been removed.",
        "solutions": [
            "Use the top navigation to return to Dashboard, Clients, or Services.",
            "Search for the client or receipt from the Services list instead of using an old bookmark.",
            "Contact your administrator if a menu item you rely on suddenly disappears.",
        ],
        "icon": "👻",
    },
    500: {
        "title": "Server Error",
        "headline": "Something went wrong on our side.",
        "summary": "An unexpected error occurred while loading this page. Your data is usually safe — the request just didn't finish.",
        "solutions": [
            "Wait a few seconds and refresh the page.",
            "Try again from the Dashboard instead of a saved browser tab.",
            "If this keeps happening, note the time and tell your administrator so we can check server logs.",
        ],
        "icon": "🛠️",
    },
    502: {
        "title": "Bad Gateway",
        "headline": "The server is temporarily unreachable.",
        "summary": "RegiManager couldn't get a timely response from the application server. This is often a brief hosting or network issue.",
        "solutions": [
            "Wait 30–60 seconds and refresh.",
            "Check your internet connection or VPN.",
            "If the problem persists, the site may be restarting — try again in a few minutes or contact support.",
        ],
        "icon": "🌐",
    },
    503: {
        "title": "Service Unavailable",
        "headline": "We're briefly unavailable for maintenance.",
        "summary": "The system may be updating or under heavy load. Please try again shortly.",
        "solutions": [
            "Refresh after a minute.",
            "Avoid submitting the same form repeatedly until the page loads normally.",
            "Contact your administrator if downtime lasts more than a few minutes.",
        ],
        "icon": "⏳",
    },
}


def _wants_json(request):
    accept = request.META.get("HTTP_ACCEPT", "")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    if "application/json" in accept and "text/html" not in accept:
        return True
    return request.path.startswith("/api/")


def error_context(request, status_code, extra=None):
    meta = ERROR_META.get(status_code, ERROR_META[500])
    ctx = {
        "status_code": status_code,
        "error_title": meta["title"],
        "error_headline": meta["headline"],
        "error_summary": meta["summary"],
        "error_solutions": meta["solutions"],
        "error_icon": meta["icon"],
        "is_authenticated": getattr(request.user, "is_authenticated", False) and request.user.is_authenticated,
    }
    if extra:
        ctx.update(extra)
    return ctx


def render_error_page(request, status_code, extra=None):
    response = render(
        request,
        "errors/error_page.html",
        error_context(request, status_code, extra),
        status=status_code,
    )
    response["X-Regi-Error-Page"] = "1"
    return response


def custom_page_not_found(request, exception=None):
    if _wants_json(request):
        return JsonResponse(
            {"status": "error", "code": 404, "message": "Page not found."},
            status=404,
        )
    return render_error_page(request, 404)


def custom_permission_denied(request, exception=None):
    if _wants_json(request):
        return JsonResponse(
            {"status": "error", "code": 403, "message": "Access denied."},
            status=403,
        )
    return render_error_page(request, 403)


def custom_server_error(request):
    if _wants_json(request):
        return JsonResponse(
            {"status": "error", "code": 500, "message": "Internal server error."},
            status=500,
        )
    return render_error_page(request, 500)


def custom_bad_gateway(request):
    return render_error_page(request, 502)


def custom_service_unavailable(request):
    return render_error_page(request, 503)


def log_server_exception(request, exc):
    logger.exception(
        "Unhandled exception for %s %s",
        request.method,
        request.get_full_path(),
        exc_info=exc,
    )
