"""Build a carrier-facing canonical payload from existing CRM rows.

Connectors map this dict to a market schema only when an official spec exists.
"""

from __future__ import annotations


def _iso(value) -> str:
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _int(value, default=0, maximum=99) -> int:
    try:
        number = int(str(value).strip() or default)
    except (TypeError, ValueError):
        return default
    return max(0, min(number, maximum))


def _bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def driver_from_client(client) -> dict:
    if client is None:
        return {}
    return {
        "client_id": client.id,
        "first_name": client.first_name or "",
        "middle_name": client.middle_name or "",
        "last_name": client.last_name or "",
        "name": client.name,
        "driver_license": client.driver_license or "",
        "dob": _iso(client.dob),
        "gender": client.gender or "",
        "phone": client.phone_number or "",
        "email": getattr(client, "email", None) or "",
        "address": {
            "building_no": client.building_no or "",
            "street": client.street_address or "",
            "apartment": client.apartment or "",
            "city": client.city or "",
            "state": (client.state or "").upper(),
            "zip_code": client.zip_code or "",
            "county": client.county or "",
        },
    }


def vehicle_from_row(vehicle) -> dict:
    if vehicle is None:
        return {}
    return {
        "vehicle_id": vehicle.id,
        "vin": (vehicle.vin or "").upper(),
        "year": vehicle.year,
        "make": vehicle.make or "",
        "model": vehicle.model or "",
        "plate_number": vehicle.plate_number or "",
        "vehicle_type": vehicle.vehicle_type or "",
        "body_type": vehicle.body_type or "",
        "ownership": "",
    }


def additional_drivers_from_lead(quote_lead) -> list[dict]:
    if quote_lead is None:
        return []
    rows = []
    for driver in quote_lead.additional_drivers.all():
        rows.append(
            {
                "name": driver.full_name or "",
                "driver_license": driver.dl_number or "",
                "dob": _iso(driver.date_of_birth),
            }
        )
    return rows


def build_canonical_payload(
    *,
    client=None,
    vehicle=None,
    quote_lead=None,
    extra=None,
    state="",
    line_of_business="",
) -> dict:
    extra = extra or {}
    driver = driver_from_client(client)
    veh = vehicle_from_row(vehicle)
    extra_drivers = list(extra.get("additional_drivers") or [])
    extra_drivers.extend(additional_drivers_from_lead(quote_lead))

    coverage_type = extra.get("coverage_type") or ""
    if not coverage_type and quote_lead is not None:
        coverage_type = quote_lead.coverage_type or ""
    if veh:
        veh["ownership"] = extra.get("vehicle_ownership") or (
            quote_lead.vehicle_ownership if quote_lead else ""
        )

    lead_state = quote_lead.state if quote_lead else ""
    lead_lob = getattr(quote_lead, "insurance_type", "") if quote_lead else ""
    resolved_state = (state or driver.get("address", {}).get("state") or lead_state or extra.get("state") or "").upper()
    zip_code = driver.get("address", {}).get("zip_code") or extra.get("zip_code") or (
        quote_lead.zip_code if quote_lead else ""
    )

    return {
        "client_id": client.id if client else None,
        "name": extra.get("name") or driver.get("name") or (quote_lead.client_name if quote_lead else "") or "",
        "state": resolved_state,
        "zip_code": zip_code or "",
        "line_of_business": line_of_business or extra.get("line_of_business") or lead_lob or "",
        "driver": driver,
        "vehicle": veh,
        "additional_drivers": extra_drivers,
        "additional_vehicles": list(extra.get("additional_vehicles") or []),
        "coverage": {"type": coverage_type or "liability"},
        "risk": {
            "has_prior": _bool(extra.get("has_prior"), quote_lead.has_prior if quote_lead else False),
            "has_accident": _bool(extra.get("has_accident"), quote_lead.has_accident if quote_lead else False),
            "is_experienced": _bool(
                extra.get("is_experienced"), quote_lead.is_experienced if quote_lead else False
            ),
            "mvr_status": extra.get("mvr_status") or "not_requested",
            "mvr_points": _int(extra.get("mvr_points")),
            "mvr_date": extra.get("mvr_date") or "",
            "mvr_notes": extra.get("mvr_notes") or "",
        },
        "scenario": extra.get("scenario") or "",
    }
