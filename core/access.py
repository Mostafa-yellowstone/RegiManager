"""Organization-scoped access helpers shared across view modules."""

from .models import Organization, OrganizationMembership


def has_active_org_access(user, organization_id):
    if not getattr(user, "is_authenticated", False):
        return False
    return OrganizationMembership.objects.filter(
        user=user,
        organization_id=organization_id,
        is_active=True,
        organization__is_active=True,
    ).exists()


def has_active_owner_access(user, organization_id):
    if not getattr(user, "is_authenticated", False):
        return False
    return OrganizationMembership.objects.filter(
        user=user,
        organization_id=organization_id,
        role=OrganizationMembership.Role.OWNER,
        is_active=True,
        organization__is_active=True,
    ).exists()


def organizations_for_user(request):
    """Organizations visible to the user, respecting the session location filter."""
    from .site_news import organizations_for_request

    return organizations_for_request(request)
