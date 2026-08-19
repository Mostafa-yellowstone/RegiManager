"""RBAC helpers — membership flags, not dotted permission strings."""

from __future__ import annotations

from core.insurance_permissions import is_org_owner, membership_for_org
from core.models import OrganizationMembership
from core.space_access import require_space_access


def can_view_regiconnect(user, organization, membership=None) -> bool:
    if user.is_superuser:
        return True
    membership = membership or membership_for_org(user, organization)
    if membership is None:
        return False
    if is_org_owner(user, organization, membership):
        return True
    return bool(membership.can_view_regiconnect)


def can_manage_regiconnect(user, organization, membership=None) -> bool:
    if user.is_superuser:
        return True
    membership = membership or membership_for_org(user, organization)
    if membership is None:
        return False
    if is_org_owner(user, organization, membership):
        return True
    return bool(membership.can_manage_regiconnect)


def require_insurance_space(request, organization):
    if request.user.is_superuser:
        return None
    membership = membership_for_org(request.user, organization)
    if membership is None:
        from core.http import deny_access

        deny_access("Access denied.")
    from core.models import Space

    space = Space.objects.filter(organization=organization, key="insurance").first()
    if space is not None:
        require_space_access(membership, space)
    return membership
