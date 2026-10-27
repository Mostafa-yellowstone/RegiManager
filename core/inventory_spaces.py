"""Inventory spaces share one stock, sales, and invoice desk. Each space keeps its own products."""

from __future__ import annotations

from .models import OrganizationMembership, Space

INVENTORY_KIND = "inventory"
INVENTORY_KEYS = frozenset({"custom_inventory", "ezpass"})


def is_inventory_space(space) -> bool:
    if space is None:
        return False
    return getattr(space, "kind", "") == INVENTORY_KIND or getattr(space, "key", "") in INVENTORY_KEYS


def ensure_inventory_space(organization, *, key: str, label: str, description: str) -> Space:
    space, _created = Space.objects.get_or_create(
        organization=organization,
        key=key,
        defaults={"label": label, "description": description, "kind": INVENTORY_KIND},
    )
    if space.kind != INVENTORY_KIND:
        space.kind = INVENTORY_KIND
        space.save(update_fields=["kind"])
    return space


def grant_space_to_owners(organization, space) -> None:
    memberships = OrganizationMembership.objects.filter(
        organization=organization,
        is_active=True,
        role=OrganizationMembership.Role.OWNER,
    )
    for membership in memberships:
        membership.accessible_spaces.add(space)
