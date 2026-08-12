"""Permissions for the Fundamental Quote Pipeline."""

from __future__ import annotations

from .models import OrganizationMembership
from .role_permissions import Role, normalize_role


def membership_for_org(user, organization) -> OrganizationMembership | None:
    if getattr(user, "is_superuser", False):
        return None
    return (
        OrganizationMembership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
            organization__is_active=True,
        )
        .select_related("organization", "user")
        .first()
    )


def is_owner_or_manager(membership: OrganizationMembership | None, *, user=None) -> bool:
    if user is not None and getattr(user, "is_superuser", False):
        return True
    if membership is None:
        return False
    from .role_permissions import is_owner_or_manager_role

    return is_owner_or_manager_role(membership.role)


def can_create_quote_leads(user, organization, *, membership=None) -> bool:
    """Anyone who deals with insurance, plus Owner/Manager for ops."""
    if getattr(user, "is_superuser", False):
        return True
    membership = membership or membership_for_org(user, organization)
    if membership is None or not membership.is_active:
        return False
    if is_owner_or_manager(membership):
        return True
    return bool(membership.can_deal_with_insurance)


def can_manage_quote_distribution(user, organization, *, membership=None) -> bool:
    """Manual assign, config, and off-day calendar — Owner/Manager only."""
    if getattr(user, "is_superuser", False):
        return True
    membership = membership or membership_for_org(user, organization)
    return is_owner_or_manager(membership, user=user)


def can_assign_quote_leads(user, organization, *, membership=None) -> bool:
    """Owner/Manager Assign UI — same gate as distribution management."""
    return can_manage_quote_distribution(user, organization, membership=membership)


def can_receive_quote_distribution(membership: OrganizationMembership | None) -> bool:
    """Auto-distribution pool: insurance agents only (not owner/manager/accountant)."""
    if membership is None or not membership.is_active:
        return False
    if not membership.can_deal_with_insurance:
        return False
    role = normalize_role(membership.role)
    return role == Role.INSURANCE_AGENT


def can_view_quote_pipeline(user, organization, *, membership=None) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    membership = membership or membership_for_org(user, organization)
    if membership is None:
        return False
    if is_owner_or_manager(membership):
        return True
    return bool(membership.can_deal_with_insurance)


def can_update_assigned_lead(user, lead, *, membership=None) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    membership = membership or membership_for_org(user, lead.organization)
    if membership is None:
        return False
    if is_owner_or_manager(membership):
        return True
    return bool(lead.assigned_to_id and lead.assigned_to_id == membership.id)


def can_edit_quote_lead(user, lead, *, membership=None) -> bool:
    """Edit lead fields — Owner/Manager, assignee, or creator."""
    if getattr(user, "is_superuser", False):
        return True
    membership = membership or membership_for_org(user, lead.organization)
    if membership is None:
        return False
    if is_owner_or_manager(membership):
        return True
    if lead.assigned_to_id and lead.assigned_to_id == membership.id:
        return True
    return bool(lead.created_by_id and lead.created_by_id == user.id)


def can_delete_quote_lead(user, lead, *, membership=None) -> bool:
    """Hard delete — Owner/Manager only."""
    return can_manage_quote_distribution(user, lead.organization, membership=membership)


def can_view_quote_lead_documents(user, lead, *, membership=None) -> bool:
    """Docs are visible to owners/managers and the agent currently assigned to the lead."""
    if getattr(user, "is_superuser", False):
        return True
    membership = membership or membership_for_org(user, lead.organization)
    if membership is None:
        return False
    if is_owner_or_manager(membership, user=user):
        return True
    return bool(lead.assigned_to_id and lead.assigned_to_id == membership.id)
