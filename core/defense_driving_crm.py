"""Defense Driving Course CRM helpers — packages, profit splits, dashboard stats."""

from decimal import Decimal

from django.db.models import Count, Q, Sum

from .models import DefenseDrivingEnrollment, DefenseDrivingPackage

DEFAULT_PACKAGES = (
    ("6-Hour Classroom", Decimal("50.00"), Decimal("30.00"), 10),
    ("Point Reduction", Decimal("75.00"), Decimal("45.00"), 20),
    ("Online Course", Decimal("35.00"), Decimal("20.00"), 30),
)


def ensure_default_packages(organization):
    """Seed common course packages for an org if none exist yet."""
    existing = DefenseDrivingPackage.objects.filter(organization=organization).exists()
    if existing:
        return list(
            DefenseDrivingPackage.objects.filter(organization=organization).order_by(
                "sort_order", "name"
            )
        )
    created = []
    for name, price, provider_take, sort_order in DEFAULT_PACKAGES:
        pkg, _ = DefenseDrivingPackage.objects.get_or_create(
            organization=organization,
            name=name,
            defaults={
                "price": price,
                "provider_take": provider_take,
                "is_active": True,
                "sort_order": sort_order,
            },
        )
        created.append(pkg)
    return created


def split_profits_for_package(package):
    """Return (provider_profit, psb_profit) from package defaults."""
    price = Decimal(str(package.price or 0))
    provider = Decimal(str(package.provider_take or 0))
    if provider > price:
        provider = price
    return provider, price - provider


def get_client_defense_driving_enrollments(client):
    """Return DDC enrollments for this client (direct + same-person SSN/DL)."""
    base_qs = DefenseDrivingEnrollment.objects.filter(
        organization=client.organization,
    ).select_related("package", "added_by", "client")

    filters = Q(client=client)

    ssn = (client.ssn or "").strip()
    if ssn:
        filters |= Q(client__ssn=ssn)

    driver_license = (client.driver_license or "").strip()
    if driver_license:
        filters |= Q(client__driver_license=driver_license)

    return list(base_qs.filter(filters).order_by("-created_at").distinct())


def pick_active_enrollment(enrollments):
    if not enrollments:
        return None
    return next(
        (
            e
            for e in enrollments
            if e.status == DefenseDrivingEnrollment.StatusChoices.ACTIVE
        ),
        enrollments[0],
    )


def enrich_enrollment(enrollment):
    enrollment.channel_label = enrollment.get_channel_display()
    enrollment.status_label = enrollment.get_status_display()
    enrollment.package_label = enrollment.package.name if enrollment.package_id else ""
    if enrollment.added_by:
        enrollment.added_by_name = (
            enrollment.added_by.get_full_name().strip()
            or enrollment.added_by.username
        )
    else:
        enrollment.added_by_name = ""
    return enrollment


def defense_driving_dashboard_stats(space):
    qs = DefenseDrivingEnrollment.objects.filter(space=space)
    active_qs = qs.filter(status=DefenseDrivingEnrollment.StatusChoices.ACTIVE)
    totals = active_qs.aggregate(
        provider_total=Sum("provider_profit"),
        psb_total=Sum("psb_profit"),
    )
    by_status = {
        row["status"]: row["count"]
        for row in qs.values("status").annotate(count=Count("id"))
    }
    by_package = list(
        active_qs.values("package__name", "package_id")
        .annotate(count=Count("id"))
        .order_by("package__sort_order", "package__name")
    )
    client_count = qs.values("client_id").distinct().count()
    return {
        "total_enrollments": qs.count(),
        "active_enrollments": active_qs.count(),
        "completed_enrollments": by_status.get(
            DefenseDrivingEnrollment.StatusChoices.COMPLETED, 0
        ),
        "pending_enrollments": by_status.get(
            DefenseDrivingEnrollment.StatusChoices.PENDING, 0
        ),
        "cancelled_enrollments": by_status.get(
            DefenseDrivingEnrollment.StatusChoices.CANCELLED, 0
        ),
        "client_count": client_count,
        "provider_revenue": totals["provider_total"] or Decimal("0"),
        "psb_revenue": totals["psb_total"] or Decimal("0"),
        "by_package": by_package,
        "insurance_channel_count": qs.filter(
            channel=DefenseDrivingEnrollment.ChannelChoices.INSURANCE_CLIENT
        ).count(),
        "direct_channel_count": qs.filter(
            channel=DefenseDrivingEnrollment.ChannelChoices.DIRECT
        ).count(),
    }
