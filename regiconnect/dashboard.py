"""Dashboard aggregates for Connectivity Center (real rows only)."""

from __future__ import annotations

from django.utils import timezone

from core.models import Vehicle

from .catalog import ensure_builtin_connectors
from .models import (
    Appointment,
    BindTransaction,
    CanonicalQuote,
    Connection,
    ConnectorJob,
    DeadLetterItem,
    DocumentExchange,
    MarketProfile,
    ProducerCode,
    Submission,
)


def space_context(organization) -> dict:
    ensure_builtin_connectors()
    today = timezone.localdate()
    connections = list(
        Connection.objects.filter(organization=organization)
        .select_related("market__company", "connector")
        .order_by("-updated_at")[:50]
    )
    submissions = list(
        Submission.objects.filter(organization=organization)
        .select_related("market__company", "connection")
        .prefetch_related("quotes")
        .order_by("-created_at")[:50]
    )
    jobs = ConnectorJob.objects.filter(organization=organization)
    vehicle_map = {}
    for vehicle in Vehicle.objects.filter(client__organization=organization).only(
        "id", "client_id", "year", "make", "model", "vin"
    )[:800]:
        vehicle_map.setdefault(str(vehicle.client_id), []).append(
            {
                "id": vehicle.id,
                "label": f"{vehicle.year or ''} {vehicle.make} {vehicle.model} · {vehicle.vin}".strip(),
            }
        )
    return {
        "regiconnect_markets": list(
            MarketProfile.objects.filter(organization=organization)
            .select_related("company")
            .order_by("company__name")[:50]
        ),
        "regiconnect_appointments": list(
            Appointment.objects.filter(organization=organization)
            .select_related("market__company")
            .order_by("-id")[:50]
        ),
        "regiconnect_producer_codes": list(
            ProducerCode.objects.filter(organization=organization)
            .select_related("market__company")
            .order_by("-id")[:50]
        ),
        "regiconnect_connections": connections,
        "regiconnect_submissions": submissions,
        "regiconnect_stats": {
            "active_markets": MarketProfile.objects.filter(
                organization=organization, status=MarketProfile.Status.ACTIVE
            ).count(),
            "active_connections": Connection.objects.filter(
                organization=organization, status=Connection.Status.ACTIVE
            ).count(),
            "failed_connections": Connection.objects.filter(
                organization=organization, status=Connection.Status.FAILED
            ).count(),
            "submissions_today": Submission.objects.filter(
                organization=organization, created_at__date=today
            ).count(),
            "quotes_today": CanonicalQuote.objects.filter(
                organization=organization, created_at__date=today
            ).count(),
            "binds_today": BindTransaction.objects.filter(
                organization=organization, created_at__date=today
            ).count(),
            "documents_today": DocumentExchange.objects.filter(
                organization=organization, created_at__date=today
            ).count(),
            "pending_jobs": jobs.filter(
                status__in=[ConnectorJob.Status.QUEUED, ConnectorJob.Status.RETRYING]
            ).count(),
            "failed_jobs": jobs.filter(status=ConnectorJob.Status.FAILED).count(),
            "dlq_open": DeadLetterItem.objects.filter(
                organization=organization, status=DeadLetterItem.Status.OPEN
            ).count(),
        },
        "regiconnect_jobs": list(jobs.select_related("connection__connector").order_by("-created_at")[:40]),
        "regiconnect_client_vehicles": vehicle_map,
        "regiconnect_disclaimer": (
            "RegiConnect provides connectivity infrastructure. Actual carrier access requires "
            "appointment, contract, and authorization from the market. This is not free access "
            "to every carrier."
        ),
    }
