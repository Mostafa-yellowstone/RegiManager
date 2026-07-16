"""Resolve existing client profiles from display names and identifiers."""

from __future__ import annotations

import re

from .client_duplicates import (
    DuplicateClientError,
    find_clients_by_full_name,
    find_duplicate_commercial_client,
    normalize_name_part,
    parse_person_display_name,
)
from .models import Client


def split_display_name(display_name: str) -> tuple[str, str]:
    """Backward-compatible first/last split (middle folded into first)."""
    first, middle, last = parse_person_display_name(display_name)
    if middle:
        first = f"{first} {middle}".strip()
    return first, last


def find_client_by_display_name(organization, display_name) -> Client | None:
    """Find an existing client/business profile from a typed display name."""
    name = normalize_name_part(display_name)
    if not name or not organization:
        return None

    qs = Client.objects.filter(organization=organization)

    commercial = qs.filter(is_commercial=True, business_name__iexact=name).first()
    if commercial:
        return commercial

    commercial = qs.filter(
        is_commercial=True,
        first_name__iexact="Commercial",
        last_name__iexact=name,
    ).first()
    if commercial:
        return commercial

    first_name, middle_name, last_name = parse_person_display_name(name)
    if not first_name or not last_name:
        return None

    matches = find_clients_by_full_name(organization, first_name, middle_name, last_name)
    if matches.count() == 1:
        return matches.first()
    return None


def resolve_client_for_display_name(
    organization,
    display_name,
    *,
    source: str = "insurance",
) -> Client:
    """
    Find or create a client from a typed display name.

    Raises DuplicateClientError when multiple profiles match the same name.
    """
    name = normalize_name_part(display_name)
    if not name:
        raise DuplicateClientError("Client name is required.")

    existing = find_client_by_display_name(organization, name)
    if existing:
        return existing

    commercial = find_duplicate_commercial_client(organization, business_name=name)
    if commercial:
        return commercial

    first_name, middle_name, last_name = parse_person_display_name(name)
    if not first_name or not last_name:
        raise DuplicateClientError("Enter a valid client name (first and last name).")

    matches = find_clients_by_full_name(organization, first_name, middle_name, last_name)
    if matches.count() > 1:
        label = " ".join(p for p in (first_name, middle_name, last_name) if p).strip()
        raise DuplicateClientError(
            f"Multiple clients named “{label}” exist with different driver licenses. "
            "Add or select the correct profile from the Clients page first."
        )

    return Client.objects.create(
        organization=organization,
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        source=source,
    )


def get_or_create_client_from_display_name(
    organization,
    display_name,
    *,
    source: str = "insurance",
) -> Client:
    return resolve_client_for_display_name(organization, display_name, source=source)
