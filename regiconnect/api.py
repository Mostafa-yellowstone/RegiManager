"""Org-scoped JSON API — Token + Session, X-Organization-Id."""

from __future__ import annotations

from rest_framework.response import Response

from core.owner_api import OwnerAPIBase

from .dashboard import space_context
from .models import Connection, RatingRequest, Submission
from .permissions import can_view_regiconnect
from .rater import rating_results


class ConnectivityDashboardView(OwnerAPIBase):
    def get(self, request):
        org, membership, *_ = self.resolve_context(request)
        if not can_view_regiconnect(request.user, org, membership):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("RegiConnect view access is required.")
        ctx = space_context(org)
        return Response({"organization_id": org.id, "stats": ctx["regiconnect_stats"]})


class SubmissionListView(OwnerAPIBase):
    def get(self, request):
        org, membership, *_ = self.resolve_context(request)
        if not can_view_regiconnect(request.user, org, membership):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("RegiConnect view access is required.")
        rows = (
            Submission.objects.filter(organization=org)
            .order_by("-created_at")
            .values("id", "status", "external_reference", "correlation_id", "created_at")[:100]
        )
        return Response({"results": list(rows)})


class ConnectionListView(OwnerAPIBase):
    def get(self, request):
        org, membership, *_ = self.resolve_context(request)
        if not can_view_regiconnect(request.user, org, membership):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("RegiConnect view access is required.")
        rows = []
        for conn in Connection.objects.filter(organization=org).select_related("market__company", "connector"):
            rows.append(
                {
                    "id": conn.id,
                    "market": conn.market.company.name,
                    "connector": conn.connector.slug,
                    "environment": conn.environment,
                    "status": conn.status,
                    "last_success_at": conn.last_success_at,
                    "last_failure_at": conn.last_failure_at,
                }
            )
        return Response({"results": rows})


class RaterRequestView(OwnerAPIBase):
    def get(self, request, request_id):
        org, membership, *_ = self.resolve_context(request)
        if not can_view_regiconnect(request.user, org, membership):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("RegiConnect view access is required.")
        row = RatingRequest.objects.filter(organization=org, pk=request_id).first()
        if row is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(rating_results(row))
