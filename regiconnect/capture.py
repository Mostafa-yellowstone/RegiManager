"""Save OCR/VIN results onto existing Client and Vehicle rows."""

from __future__ import annotations

from datetime import datetime

from django.db import IntegrityError
from django.utils.crypto import get_random_string

from core.models import Client, Vehicle
from core.vin_validation import normalize_vin, validate_vin


def parse_date(value):
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m%d%Y"):
        try:
            return datetime.strptime(raw[:10] if fmt != "%m%d%Y" else raw[:8], fmt).date()
        except ValueError:
            continue
    return None


def _fill(instance, field, value):
    if value in (None, ""):
        return False
    current = getattr(instance, field)
    if current in (None, ""):
        setattr(instance, field, value)
        return True
    return False


def upsert_client_from_scan(*, organization, data: dict, overwrite: bool = False) -> tuple[Client, bool]:
    first = (data.get("first_name") or "").strip()
    last = (data.get("last_name") or "").strip()
    license_no = (data.get("driver_license") or "").replace(" ", "").strip()
    if not first and not last and not license_no:
        raise ValueError("Scan did not include a name or driver license.")

    pk = str(data.get("client_id") or data.get("id") or "").strip()
    client = None
    created = False
    if pk.isdigit():
        client = Client.objects.filter(organization=organization, id=int(pk)).first()
    if client is None and license_no:
        client = Client.objects.filter(organization=organization, driver_license=license_no).first()
    if client is None:
        client = Client(
            organization=organization,
            first_name=first or "Unknown",
            last_name=last or "Driver",
            source="walk-in",
        )
        created = True

    updates = []
    mapping = {
        "first_name": first,
        "last_name": last,
        "middle_name": (data.get("middle_name") or "").strip(),
        "driver_license": license_no,
        "gender": (data.get("gender") or "").strip().lower() or None,
        "building_no": (data.get("building_no") or "").strip(),
        "street_address": (data.get("street_address") or "").strip(),
        "apartment": (data.get("apartment") or "").strip(),
        "city": (data.get("city") or "").strip(),
        "state": (data.get("state") or "").strip().upper()[:2],
        "zip_code": (data.get("zip_code") or "").strip(),
        "county": (data.get("county") or "").strip(),
        "phone_number": (data.get("phone_number") or "").strip(),
        "email": (data.get("email") or "").strip() or None,
    }
    valid_genders = {choice[0] for choice in Client.GENDER_CHOICES}
    if mapping.get("gender") not in valid_genders:
        mapping["gender"] = None

    if created:
        for field, value in mapping.items():
            if value not in (None, ""):
                setattr(client, field, value)
        dob = parse_date(data.get("dob"))
        if dob:
            client.dob = dob
        client.save()
        return client, True

    for field, value in mapping.items():
        if field in {"first_name", "last_name"} and getattr(client, field) in {"Unknown", "Driver"} and value:
            setattr(client, field, value)
            updates.append(field)
            continue
        if overwrite and value not in (None, ""):
            if getattr(client, field) != value:
                setattr(client, field, value)
                updates.append(field)
            continue
        if _fill(client, field, value):
            updates.append(field)
    dob = parse_date(data.get("dob"))
    if dob and (overwrite or not client.dob):
        if client.dob != dob:
            client.dob = dob
            updates.append("dob")
    if updates:
        client.save(update_fields=list(dict.fromkeys(updates)))
    return client, False


def upsert_vehicle_from_scan(*, client: Client, data: dict) -> tuple[Vehicle, bool]:
    vin = normalize_vin(data.get("vin") or "")
    if not vin:
        raise ValueError("VIN is required.")
    ok, message = validate_vin(vin, legacy=False, manual_type=False)
    if not ok:
        raise ValueError(message)

    existing = Vehicle.objects.filter(client=client, vin=vin).first()
    year = data.get("year")
    try:
        year_int = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        year_int = None
    fields = {
        "make": (data.get("make") or "").strip(),
        "model": (data.get("model") or "").strip(),
        "plate_number": (data.get("plate_number") or "").strip(),
        "color": (data.get("color") or "").strip(),
        "weight": (data.get("weight") or "").strip(),
        "cylinders": (data.get("cylinders") or "").strip(),
    }
    if existing:
        updates = []
        if year_int and not existing.year:
            existing.year = year_int
            updates.append("year")
        for field, value in fields.items():
            if _fill(existing, field, value):
                updates.append(field)
        if updates:
            existing.save(update_fields=updates)
        return existing, False

    vehicle = Vehicle(
        client=client,
        vin=vin,
        year=year_int,
        vehicle_number=f"VEH-{get_random_string(6, allowed_chars='0123456789')}",
        **{k: v for k, v in fields.items() if v},
    )
    try:
        vehicle.save()
    except IntegrityError as exc:
        raise ValueError("This client already has that VIN.") from exc
    return vehicle, True
