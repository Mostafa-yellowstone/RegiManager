"""Shared access checks for the Spaces section."""

from .http import deny_access
from .models import OrganizationMembership, Space


def get_org_membership(user, organization):
    """Return active membership or deny; superusers return None."""
    if user.is_superuser:
        return None
    membership = OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
        organization__is_active=True,
    ).first()
    if not membership:
        deny_access("Access denied.")
    return membership


def require_spaces_page_access(membership):
    if not membership.can_view_spaces:
        deny_access("You do not have permission to view Spaces.")


def require_space_access(membership, space):
    require_spaces_page_access(membership)
    if not membership.accessible_spaces.filter(id=space.id).exists():
        deny_access("You do not have permission to access this space.")


def filter_accessible_spaces(membership, organization):
    return Space.objects.filter(
        organization=organization,
        id__in=membership.accessible_spaces.values_list("id", flat=True),
    )
