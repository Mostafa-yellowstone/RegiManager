"""Insurance Space finance permission helpers (banking, companies, commission)."""

from __future__ import annotations

from .models import OrganizationMembership


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
