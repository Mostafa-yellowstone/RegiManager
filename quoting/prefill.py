"""Copy a quote lead into the desk. Fields the lead does not have stay blank."""

from __future__ import annotations

from datetime import timedelta

from quoting.demo.scenarios import CARRIER_KEYS
from quoting.intake import ny_today


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [part for part in (full_name or "").split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _date(value) -> str:
    if not value:
        return ""
    return value.isoformat()


def form_from_lead(lead) -> dict:
    first, last = _split_name(getattr(lead, "client_name", ""))
    street = (getattr(lead, "street_address", "") or "").strip()
    apartment = (getattr(lead, "apartment", "") or "").strip()
    if apartment:
        street = f"{street}, {apartment}".strip(", ")
    coverage = (getattr(lead, "coverage_type", "") or "").strip()
    if coverage == "liability":
        comp, coll = "none", "none"
    else:
        comp, coll = "", ""
    vehicle_year = getattr(lead, "vehicle_year", "") or ""
    vehicle_make = getattr(lead, "vehicle_make", "") or ""
    vehicle_model = getattr(lead, "vehicle_model", "") or ""
    vehicle_vin = (getattr(lead, "vin", "") or "").upper()
    has_vehicle = any((vehicle_year, vehicle_make, vehicle_model, vehicle_vin))
    garaging_zip = (getattr(lead, "zip_code", "") or "") if has_vehicle else ""
    form = {
        "effective_date": (ny_today() + timedelta(days=7)).isoformat(),
        "insured_first_name": first,
        "insured_last_name": last,
        "insured_date_of_birth": _date(getattr(lead, "date_of_birth", None)),
        "insured_phone": getattr(lead, "phone", "") or "",
        "insured_email": getattr(lead, "email", "") or "",
        "insured_street": street,
        "insured_city": getattr(lead, "city", "") or "",
        "insured_state": (getattr(lead, "state", "") or "NY").upper(),
        "insured_zip": getattr(lead, "zip_code", "") or "",
        "driver_1_first_name": first,
        "driver_1_last_name": last,
        "driver_1_date_of_birth": _date(getattr(lead, "date_of_birth", None)),
        "driver_1_license_number": getattr(lead, "dl_number", "") or "",
        "driver_1_license_state": "",
        "driver_1_license_state_reason": "",
        "driver_1_relationship": "named_insured",
        "driver_1_years_licensed": "",
        "driver_1_accidents": "" if getattr(lead, "has_accident", False) else "0",
        "driver_1_violations": "",
        "vehicle_1_year": vehicle_year,
        "vehicle_1_make": vehicle_make,
        "vehicle_1_model": vehicle_model,
        "vehicle_1_vin": vehicle_vin,
        "vehicle_1_usage": "",
        "vehicle_1_ownership": "",
        "vehicle_1_lienholder": "",
        "vehicle_1_garaging_zip": garaging_zip,
        "coverage_bi": "",
        "coverage_pd": "",
        "coverage_pip": "",
        "coverage_um": "",
        "coverage_comp": comp,
        "coverage_coll": coll,
        "coverage_term": "6",
        "currently_insured": "yes" if getattr(lead, "has_prior", False) else "",
        "prior_carrier": "",
        "prior_expiration": "",
        "prior_lapse_reason": "",
        "voluntary_market_declined": "",
        "declination_carrier": "",
        "mvr_pending": "",
        "carriers_submitted": "1",
        "carriers": list(CARRIER_KEYS),
    }
    for offset, driver in enumerate(getattr(lead, "additional_drivers", []).all() if hasattr(getattr(lead, "additional_drivers", None), "all") else [], start=2):
        if offset > 6:
            break
        driver_first, driver_last = _split_name(getattr(driver, "full_name", ""))
        prefix = f"driver_{offset}"
        form[f"{prefix}_first_name"] = driver_first
        form[f"{prefix}_last_name"] = driver_last
        form[f"{prefix}_date_of_birth"] = _date(getattr(driver, "date_of_birth", None))
        form[f"{prefix}_license_number"] = getattr(driver, "dl_number", "") or ""
        form[f"{prefix}_license_state"] = ""
        form[f"{prefix}_relationship"] = ""
        form[f"{prefix}_years_licensed"] = ""
        form[f"{prefix}_accidents"] = ""
        form[f"{prefix}_violations"] = ""
    for offset, vehicle in enumerate(getattr(lead, "additional_vehicles", []).all() if hasattr(getattr(lead, "additional_vehicles", None), "all") else [], start=2):
        if offset > 4:
            break
        prefix = f"vehicle_{offset}"
        form[f"{prefix}_year"] = getattr(vehicle, "year", "") or ""
        form[f"{prefix}_make"] = getattr(vehicle, "make", "") or ""
        form[f"{prefix}_model"] = getattr(vehicle, "model", "") or ""
        form[f"{prefix}_vin"] = (getattr(vehicle, "vin", "") or "").upper()
        form[f"{prefix}_usage"] = ""
        form[f"{prefix}_ownership"] = ""
        form[f"{prefix}_garaging_zip"] = getattr(lead, "zip_code", "") or ""
    return form
