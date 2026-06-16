"""Shared client search helpers for dashboard AJAX and clients list."""

from __future__ import annotations

import re

from django.db.models import Q

_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]")
_DIGITS_RE = re.compile(r"\D")


def normalize_alnum(value: str) -> str:
    return _NON_ALNUM_RE.sub("", (value or "").upper())


def normalize_phone_digits(value: str) -> str:
    digits = _DIGITS_RE.sub("", value or "")
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def query_looks_like_phone(query: str, q_digits: str | None = None) -> bool:
    q = (query or "").strip()
    q_digits = q_digits if q_digits is not None else normalize_phone_digits(q)
    if re.search(r"[()\-\s.+]", q):
        return len(q_digits) >= 10
    return len(q_digits) in (10, 11)


def query_looks_like_driver_license(query: str, q_norm: str | None = None) -> bool:
    q_norm = q_norm if q_norm is not None else normalize_alnum(query)
    if len(q_norm) < 4:
        return False
    q_digits = normalize_phone_digits(query)
    if q_norm.isdigit() and len(q_digits) >= 10 and not re.search(r"[A-Za-z]", query or ""):
        return False
    return True


def build_client_name_search_q(query: str) -> Q:
    """Match clients by individual name parts or combined full-name queries."""
    q = (query or "").strip()
    if not q:
        return Q()

    # Skip broad name matching for digit-heavy queries (driver license / phone lookups).
    q_norm = normalize_alnum(q)
    if len(q_norm) >= 6 and sum(ch.isdigit() for ch in q_norm) >= len(q_norm) * 0.7:
        return Q()

    name_q = (
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(middle_name__icontains=q)
        | Q(business_name__icontains=q)
    )

    if "," in q:
        pieces = [p.strip() for p in q.split(",", 1)]
        if len(pieces) == 2 and pieces[0] and pieces[1]:
            name_q |= Q(last_name__icontains=pieces[0], first_name__icontains=pieces[1])

    tokens = [t for t in q.replace(",", " ").split() if t]
    if len(tokens) >= 2:
        first_token = tokens[0]
        remaining = " ".join(tokens[1:])
        name_q |= Q(first_name__icontains=first_token, last_name__icontains=remaining)
        name_q |= Q(last_name__icontains=first_token, first_name__icontains=remaining)

        if len(tokens) >= 3:
            name_q |= Q(
                first_name__icontains=tokens[0],
                middle_name__icontains=tokens[1],
                last_name__icontains=" ".join(tokens[2:]),
            )

    return name_q


def build_driver_license_search_q(query: str) -> Q:
    q = (query or "").strip()
    if not q:
        return Q()

    combined = Q(driver_license__icontains=q)
    q_norm = normalize_alnum(q)
    if q_norm and q_norm != q.upper():
        combined |= Q(driver_license__icontains=q_norm)
    return combined


def build_phone_search_q(query: str) -> Q:
    q = (query or "").strip()
    if not q:
        return Q()

    q_digits = normalize_phone_digits(q)
    if not query_looks_like_phone(q, q_digits):
        return Q()

    combined = Q(phone_number__icontains=q)
    if len(q_digits) >= 10:
        combined |= Q(phone_number__icontains=q_digits[-10:])
    return combined


def build_full_client_search_q(query: str) -> Q:
    """Name, driver license, phone, plate, and business identifiers."""
    q = (query or "").strip()
    if not q:
        return Q()

    combined = build_client_name_search_q(q)
    combined |= build_driver_license_search_q(q)
    combined |= build_phone_search_q(q)
    combined |= Q(email__icontains=q)
    combined |= Q(city__icontains=q)
    combined |= Q(business_name__icontains=q)
    combined |= Q(business_ein__icontains=q)
    combined |= Q(vehicles__plate_number__icontains=q)
    return combined


def _driver_license_score(client_dl: str, query: str, q_norm: str) -> int:
    stored_norm = normalize_alnum(client_dl)
    if not stored_norm or not q_norm:
        return 0
    if stored_norm == q_norm:
        return 1000
    if stored_norm.startswith(q_norm) or q_norm.startswith(stored_norm):
        return 800
    raw = (client_dl or "").strip()
    if raw and query in raw:
        return 600
    return 0


def _phone_score(client_phone: str, query: str, q_digits: str) -> int:
    if not query_looks_like_phone(query, q_digits):
        return 0
    stored = normalize_phone_digits(client_phone)
    if not stored or len(q_digits) < 10:
        return 0
    if stored == q_digits:
        return 900
    if stored.endswith(q_digits[-10:]) or q_digits.endswith(stored[-10:]):
        return 850
    return 0


def _plate_score(plate_numbers: list[str], query: str, q_norm: str) -> int:
    for plate in plate_numbers:
        if not plate:
            continue
        plate_norm = normalize_alnum(plate)
        if q_norm and plate_norm == q_norm:
            return 700
        if query.lower() in plate.lower():
            return 500
    return 0


def client_matches_name_query(client, query: str) -> bool:
    name_q = build_client_name_search_q(query)
    if not name_q:
        return False
    from .models import Client

    return Client.objects.filter(pk=client.pk).filter(name_q).exists()


def _name_score(client, query: str) -> int:
    if not client_matches_name_query(client, query):
        return 0

    q_lower = query.strip().lower()
    full = (client.full_display_name or client.name or "").lower()
    if full == q_lower:
        return 450
    if q_lower in full or full in q_lower:
        return 350
    return 300


def score_client_match(client, query: str, plate_numbers: list[str] | None = None) -> int:
    q = (query or "").strip()
    if not q:
        return 0

    q_norm = normalize_alnum(q)
    q_digits = normalize_phone_digits(q)
    plate_numbers = plate_numbers if plate_numbers is not None else []

    scores = [
        _driver_license_score(client.driver_license, q, q_norm),
        _phone_score(client.phone_number, q, q_digits),
        _plate_score(plate_numbers, q, q_norm),
        _name_score(client, q),
    ]
    ein = (client.business_ein or "").strip()
    if ein and q.lower() in ein.lower():
        scores.append(750)
    email = (client.email or "").strip()
    if email and q.lower() in email.lower():
        scores.append(200)
    return max(scores)


def find_exact_driver_license_client(organizations, query: str):
    """Return a single client when the normalized driver license is an exact match."""
    q_norm = normalize_alnum(query)
    if len(q_norm) < 4:
        return None

    from .models import Client

    for client in (
        Client.objects.filter(organization__in=organizations)
        .exclude(driver_license="")
        .only("id", "driver_license")
        .iterator()
    ):
        if normalize_alnum(client.driver_license) == q_norm:
            return client.id
    return None


def search_clients_ranked(organizations, query: str, *, limit: int = 8) -> list:
    """
    Return Client instances ordered by best match for dashboard / portal search.
  Uses conservative DB filters, then ranks in Python to avoid phone/DL cross-matches.
    """
    q = (query or "").strip()
    if len(q) < 2:
        return []

    from .models import Client

    limit = min(max(limit, 1), 20)
    exact_dl_id = find_exact_driver_license_client(organizations, q)

    candidate_ids = list(
        Client.objects.filter(organization__in=organizations)
        .filter(build_full_client_search_q(q))
        .values_list("id", flat=True)
        .distinct()[: max(limit * 4, 24)]
    )

    if exact_dl_id and exact_dl_id not in candidate_ids:
        candidate_ids.insert(0, exact_dl_id)

    if not candidate_ids:
        return []

    clients = {
        c.id: c
        for c in Client.objects.filter(id__in=candidate_ids)
        .select_related("organization")
        .prefetch_related("vehicles")
    }
    plates_by_client = {
        cid: [v.plate_number for v in clients[cid].vehicles.all() if v.plate_number]
        for cid in candidate_ids
        if cid in clients
    }

    ranked = []
    for cid in candidate_ids:
        client = clients.get(cid)
        if not client:
            continue
        score = score_client_match(client, q, plates_by_client.get(cid, []))
        if score <= 0 and cid != exact_dl_id:
            continue
        if cid == exact_dl_id:
            score = max(score, 1000)
        ranked.append((score, cid))

    ranked.sort(key=lambda row: (-row[0], -row[1]))
    ordered_ids = [cid for _, cid in ranked[:limit]]
    return [clients[cid] for cid in ordered_ids if cid in clients]


def serialize_client_search_result(client) -> dict:
    plate = client.vehicles.values_list("plate_number", flat=True).first() or ""
    display_name = client.full_display_name or client.name
    return {
        "name": display_name,
        "full_name": display_name,
        "first_name": client.first_name,
        "last_name": client.last_name,
        "identifier": client.driver_license or client.business_ein or "",
        "plate": plate,
        "url": f"/dashboard/clients/{client.id}/",
        "is_commercial": client.is_commercial,
        "business_name": client.business_name or "",
    }
