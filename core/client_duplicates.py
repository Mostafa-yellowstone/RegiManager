"""Duplicate client detection for add/edit flows and insurance policy linking."""

from __future__ import annotations

import re

from .models import Client


class DuplicateClientError(Exception):
    """Raised when a new client profile would duplicate an existing one."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def normalize_name_part(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_driver_license(value: str) -> str:
    return normalize_name_part(value).upper()


def parse_person_display_name(display_name: str) -> tuple[str, str, str]:
    """
    Parse a typed display name into first, middle, and last.

    Examples:
        "John Smith" -> John, "", Smith
        "John A Smith" -> John, A, Smith
        "Mary Jane Watson" -> Mary, Jane, Watson
    """
    name = normalize_name_part(display_name)
    if not name:
        return "", "", ""
    parts = name.split(" ")
    if len(parts) == 1:
        return parts[0], "", "."
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def _client_qs(organization):
    return Client.objects.filter(organization=organization)


def find_clients_by_driver_license(
    organization,
    driver_license: str,
    *,
    exclude_client_id: int | None = None,
):
    dl = normalize_driver_license(driver_license)
    if not dl:
        return Client.objects.none()
    qs = _client_qs(organization).filter(driver_license__iexact=dl, is_commercial=False)
    if exclude_client_id:
        qs = qs.exclude(pk=exclude_client_id)
    return qs


def find_clients_by_full_name(
    organization,
    first_name: str,
    middle_name: str,
    last_name: str,
    *,
    exclude_client_id: int | None = None,
):
    """
    Match individual clients by first + last name (case-insensitive).

    Middle name is ignored so "John Smith", "JOHN SMITH", and "John A Smith"
    all resolve to the same identity set. Prefer exact middle matches with
    prefer_exact_middle_match() when choosing among results.
    """
    first = normalize_name_part(first_name)
    last = normalize_name_part(last_name)
    if not first or not last:
        return Client.objects.none()
    qs = _client_qs(organization).filter(
        is_commercial=False,
        first_name__iexact=first,
        last_name__iexact=last,
    )
    if exclude_client_id:
        qs = qs.exclude(pk=exclude_client_id)
    return qs


def prefer_exact_middle_match(clients, middle_name: str = ""):
    """Prefer a client whose middle name matches (case-insensitive); else first."""
    clients = list(clients)
    if not clients:
        return None
    middle = normalize_name_part(middle_name)
    for client in clients:
        if normalize_name_part(client.middle_name).casefold() == middle.casefold():
            return client
    return clients[0]


def _name_identity_matches(existing: Client, *, driver_license: str = "") -> bool:
    """True when name match should count as the same person (DL rules)."""
    new_dl = normalize_driver_license(driver_license)
    existing_dl = normalize_driver_license(existing.driver_license)
    if new_dl and existing_dl and new_dl != existing_dl:
        return False
    return True


def find_duplicate_commercial_client(
    organization,
    *,
    business_name: str = "",
    business_ein: str = "",
    exclude_client_id: int | None = None,
) -> Client | None:
    qs = _client_qs(organization).filter(is_commercial=True)
    if exclude_client_id:
        qs = qs.exclude(pk=exclude_client_id)

    ein = normalize_name_part(business_ein)
    if ein:
        match = qs.filter(business_ein__iexact=ein).first()
        if match:
            return match

    name = normalize_name_part(business_name)
    if name:
        return qs.filter(business_name__iexact=name).first()
    return None


def find_duplicate_client(
    organization,
    *,
    first_name: str = "",
    middle_name: str = "",
    last_name: str = "",
    driver_license: str = "",
    exclude_client_id: int | None = None,
    is_commercial: bool = False,
    business_name: str = "",
    business_ein: str = "",
) -> Client | None:
    """
    Return an existing client that would duplicate the submitted identity.

    Individual rules (case-insensitive):
    - Same driver license in the PSB is always a duplicate.
    - Same first + last is a duplicate (middle name differences ignored)
      unless both profiles have different non-empty driver licenses
      (different people, same name).
    """
    if is_commercial:
        return find_duplicate_commercial_client(
            organization,
            business_name=business_name,
            business_ein=business_ein,
            exclude_client_id=exclude_client_id,
        )

    dl_match = find_clients_by_driver_license(
        organization,
        driver_license,
        exclude_client_id=exclude_client_id,
    ).first()
    if dl_match:
        return dl_match

    first = normalize_name_part(first_name)
    middle = normalize_name_part(middle_name)
    last = normalize_name_part(last_name)
    if not first or not last:
        return None

    candidates = [
        candidate
        for candidate in find_clients_by_full_name(
            organization,
            first,
            middle,
            last,
            exclude_client_id=exclude_client_id,
        )
        if _name_identity_matches(candidate, driver_license=driver_license)
    ]
    return prefer_exact_middle_match(candidates, middle)


def duplicate_client_message(client: Client) -> str:
    if client.is_commercial:
        label = client.business_name or client.name
        if client.business_ein:
            return f"A business named “{label}” (EIN {client.business_ein}) already exists in this PSB."
        return f"A business named “{label}” already exists in this PSB."

    full_name = client.full_display_name
    if client.driver_license:
        return (
            f"A client named “{full_name}” with driver license {client.driver_license} "
            f"already exists in this PSB."
        )
    return f"A client named “{full_name}” already exists in this PSB."


def validate_new_client_not_duplicate(
    organization,
    *,
    first_name: str = "",
    middle_name: str = "",
    last_name: str = "",
    driver_license: str = "",
    exclude_client_id: int | None = None,
    is_commercial: bool = False,
    business_name: str = "",
    business_ein: str = "",
) -> str | None:
    duplicate = find_duplicate_client(
        organization,
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        driver_license=driver_license,
        exclude_client_id=exclude_client_id,
        is_commercial=is_commercial,
        business_name=business_name,
        business_ein=business_ein,
    )
    if duplicate:
        return duplicate_client_message(duplicate)
    return None
