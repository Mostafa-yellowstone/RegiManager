"""Permissions for Email Marketing workspaces."""

from __future__ import annotations

from .models import OrganizationMembership


def can_manage_email_marketing(user, organization, membership=None, is_owner=None) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if membership is None:
        membership = OrganizationMembership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
            organization__is_active=True,
        ).first()
    if not membership:
        return False
    if is_owner is None:
        is_owner = membership.role == OrganizationMembership.Role.OWNER
    return is_owner or membership.can_manage_email_marketing
