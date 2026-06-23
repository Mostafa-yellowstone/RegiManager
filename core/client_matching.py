"""Resolve existing client profiles from display names and identifiers."""

from __future__ import annotations

import re

from .models import Client


def split_display_name(display_name: str) -> tuple[str, str]:
    name = re.sub(r"\s+", " ", (display_name or "").strip())
    if not name:
        return "", ""
    parts = name.split(" ")
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return name, "."


def find_client_by_display_name(organization, display_name) -> Client | None:
    """Find an existing client/business profile from a typed display name."""
    name = re.sub(r"\s+", " ", (display_name or "").strip())
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

    first_name, last_name = split_display_name(name)
    if first_name and last_name:
        return qs.filter(
            is_commercial=False,
            first_name__iexact=first_name,
            last_name__iexact=last_name,
        ).first()
    return None


def get_or_create_client_from_display_name(
    organization,
    display_name,
    *,
    source: str = "insurance",
) -> Client:
    existing = find_client_by_display_name(organization, display_name)
    if existing:
        return existing

    first_name, last_name = split_display_name(display_name)
    return Client.objects.create(
        organization=organization,
        first_name=first_name,
        last_name=last_name,
        source=source,
    )
