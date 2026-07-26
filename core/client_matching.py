"""Resolve existing client profiles from display names and identifiers."""

from __future__ import annotations

from .client_duplicates import (
    DuplicateClientError,
    find_clients_by_full_name,
    find_duplicate_commercial_client,
    normalize_name_part,
    parse_person_display_name,
    prefer_exact_middle_match,
)
from .models import Client


def split_display_name(display_name: str) -> tuple[str, str]:
    """Backward-compatible first/last split (middle folded into first)."""
    first, middle, last = parse_person_display_name(display_name)
    if middle:
        first = f"{first} {middle}".strip()
    return first, last


def find_client_by_display_name(organization, display_name) -> Client | None:
    """
    Find an existing client/business profile from a typed display name.

    Individual matches use first + last only (case-insensitive); middle name
    differences do not create a separate profile.
    """
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

    matches = list(
        find_clients_by_full_name(organization, first_name, middle_name, last_name)
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return prefer_exact_middle_match(matches, middle_name)
    return None


def resolve_client_for_display_name(
    organization,
    display_name,
    *,
    source: str = "insurance",
) -> Client:
    """
    Find or create a client from a typed display name.

    Reuses an existing first+last match (ignores case and middle-name drift)
    so DEC import and Add Policy cannot create duplicate people.

    Raises DuplicateClientError when multiple profiles share the same first+last
    with conflicting identities (e.g. different driver licenses).
    """
    name = normalize_name_part(display_name)
    if not name:
        raise DuplicateClientError("Client name is required.")

    first_name, middle_name, last_name = parse_person_display_name(name)
    if first_name and last_name:
        matches = list(
            find_clients_by_full_name(organization, first_name, middle_name, last_name)
        )
        if len(matches) > 1:
            # Ambiguous only when more than one distinct DL is present.
            dls = {
                (c.driver_license or "").strip().upper()
                for c in matches
                if (c.driver_license or "").strip()
            }
            if len(dls) > 1:
                label = " ".join(
                    p for p in (first_name, middle_name, last_name) if p
                ).strip()
                raise DuplicateClientError(
                    f"Multiple clients named “{label}” exist with different driver licenses. "
                    "Add or select the correct profile from the Clients page first."
                )
            preferred = prefer_exact_middle_match(matches, middle_name)
            if preferred:
                return preferred
        elif len(matches) == 1:
            return matches[0]

    existing = find_client_by_display_name(organization, name)
    if existing:
        return existing

    commercial = find_duplicate_commercial_client(organization, business_name=name)
    if commercial:
        return commercial

    if not first_name or not last_name:
        raise DuplicateClientError("Enter a valid client name (first and last name).")

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
