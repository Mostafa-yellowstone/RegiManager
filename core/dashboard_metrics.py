"""Dashboard aggregation helpers."""

from django.db.models import Count, Q

from .models import CustomServiceType, ServiceRecord


def build_service_cards(scope_qs, organizations, today, month_start, year_start):
    """Single-query per-metric service card stats instead of N×4 count queries."""
    custom_types = CustomServiceType.objects.filter(organization__in=organizations)
    all_service_keys = list(ServiceRecord.SERVICE_TYPES)
    for ct in custom_types:
        all_service_keys.append((ct.key, ct.label))

    built_in_service_keys = {key for key, _ in ServiceRecord.SERVICE_TYPES}
    service_stats_rows = {
        row["service_type"]: row
        for row in scope_qs.values("service_type").annotate(
            daily_count=Count("id", filter=Q(created_at__date=today)),
            monthly_count=Count("id", filter=Q(created_at__date__gte=month_start)),
            yearly_count=Count("id", filter=Q(created_at__date__gte=year_start)),
            total_count=Count("id"),
        )
    }

    service_cards = []
    for service_key, service_label in all_service_keys:
        stats = service_stats_rows.get(service_key, {})
        service_cards.append(
            {
                "key": service_key,
                "label": service_label,
                "daily_count": stats.get("daily_count", 0),
                "monthly_count": stats.get("monthly_count", 0),
                "yearly_count": stats.get("yearly_count", 0),
                "total_count": stats.get("total_count", 0),
                "is_custom": service_key not in built_in_service_keys,
            }
        )
    return service_cards
