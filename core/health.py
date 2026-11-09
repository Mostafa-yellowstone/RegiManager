"""Liveness / readiness probe for nginx, uptime monitors and deploy scripts."""

import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@never_cache
@require_GET
def healthz(request):
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        logger.exception("Health check: database unavailable")
        checks["database"] = "down"
    try:
        cache.set("healthz", "1", 10)
        checks["cache"] = "ok" if cache.get("healthz") == "1" else "down"
    except Exception:
        logger.warning("Health check: cache unavailable", exc_info=True)
        checks["cache"] = "down"
    healthy = checks["database"] == "ok"
    return JsonResponse({"status": "ok" if healthy else "down", "checks": checks}, status=200 if healthy else 503)
