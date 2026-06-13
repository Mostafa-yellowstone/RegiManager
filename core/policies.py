"""Central authorization helpers for web and API layers."""

from django.db.models import Q

from .models import OrganizationMembership


def active_memberships_qs(user):
    """Active PSB memberships for an authenticated user."""
    if not getattr(user, "is_authenticated", False):
        return OrganizationMembership.objects.none()
    return OrganizationMembership.objects.filter(
        user=user,
        is_active=True,
        organization__is_active=True,
    )


def user_organization_ids(user):
    return list(active_memberships_qs(user).values_list("organization_id", flat=True))


def filter_queryset_for_user(queryset, user, org_field="organization_id"):
    """Restrict a queryset to organizations the user actively belongs to."""
    org_ids = user_organization_ids(user)
    if not org_ids:
        return queryset.none()
    return queryset.filter(**{f"{org_field}__in": org_ids})


def user_is_owner(user, organization_id=None):
    qs = active_memberships_qs(user).filter(role=OrganizationMembership.Role.OWNER)
    if organization_id:
        qs = qs.filter(organization_id=organization_id)
    return qs.exists()


def safe_redirect_target(request, fallback="dashboard"):
    """Prevent open redirects via untrusted Referer headers."""
    from django.urls import reverse
    from django.utils.http import url_has_allowed_host_and_scheme

    referer = request.META.get("HTTP_REFERER")
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return referer
    return reverse(fallback)
