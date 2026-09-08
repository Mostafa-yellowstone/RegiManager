"""Insurance Space finance permission helpers (banking, companies, commission)."""

from __future__ import annotations

from .models import OrganizationMembership
from .role_permissions import is_owner_or_manager_role


def membership_for_org(user, organization):
  if user.is_superuser:
      return None
  return OrganizationMembership.objects.filter(
      user=user,
      organization=organization,
      is_active=True,
      organization__is_active=True,
  ).first()


def is_org_owner(user, organization, membership=None) -> bool:
  if user.is_superuser:
      return True
  membership = membership or membership_for_org(user, organization)
  return bool(membership and membership.role == OrganizationMembership.Role.OWNER)


def can_edit_added_org_record(user, organization, added_by_id, *, membership=None) -> bool:
  """Owner/manager (and superuser) may edit; otherwise only the user who added it."""
  if getattr(user, "is_superuser", False):
      return True
  membership = membership or membership_for_org(user, organization)
  if membership is None:
      return False
  if is_owner_or_manager_role(membership.role):
      return True
  return bool(added_by_id and added_by_id == user.id)


def can_edit_insurance_policy(user, policy, *, membership=None) -> bool:
  membership = membership or membership_for_org(user, policy.organization)
  if can_edit_added_org_record(
      user,
      policy.organization,
      getattr(policy, "added_by_id", None),
      membership=membership,
  ):
      return True
  return bool(membership and membership.can_view_banking)


def can_manage_insurance_finance(user, organization, *, membership=None, is_owner=None) -> bool:
  """
  Banking tab, companies tab, commission fields, and daily-payment clear toggles.
  Owners and superusers always have access.
  """
  if user.is_superuser:
      return True
  membership = membership or membership_for_org(user, organization)
  if membership is None:
      return False
  if is_owner is None:
      is_owner = membership.role == OrganizationMembership.Role.OWNER
  if is_owner:
      return True
  return bool(membership.can_view_banking)
