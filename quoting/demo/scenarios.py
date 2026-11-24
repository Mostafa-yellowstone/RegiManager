"""Sample applications for the demo. The people and VINs are not a real client."""

from __future__ import annotations

from datetime import date, timedelta


CARRIER_KEYS = ("progressive", "national_general", "nyaip")

SCENARIO_ORDER = ("clean", "mvr", "referral", "assigned", "lapse")

SCENARIO_LABELS = {
    "clean": "Clean voluntary",
    "mvr": "MVR needed",
    "referral": "Underwriting referral",
    "assigned": "Assigned Risk",
    "lapse": "No prior reason",
}


def _base(today: date) -> dict:
    effective = (today + timedelta(days=7)).isoformat()
    expiration = (today + timedelta(days=40)).isoformat()
    return {
        "effective_date": effective,
        "insured_first_name": "Maya",
        "insured_last_name": "Hassan",
        "insured_date_of_birth": "1988-04-12",
        "insured_phone": "718-555-0148",
        "insured_email": "maya.hassan.sample@example.com",
        "insured_street": "88-15 164th Street",
        "insured_city": "Jamaica",
        "insured_state": "NY",
        "insured_zip": "11432",
        "driver_1_first_name": "Maya",
        "driver_1_last_name": "Hassan",
        "driver_1_date_of_birth": "1988-04-12",
        "driver_1_license_number": "123456789",
        "driver_1_license_state": "NY",
        "driver_1_license_state_reason": "",
        "driver_1_relationship": "named_insured",
        "driver_1_years_licensed": "18",
        "driver_1_accidents": "0",
        "driver_1_violations": "0",
        "vehicle_1_year": "2021",
        "vehicle_1_make": "Honda",
        "vehicle_1_model": "Accord",
        "vehicle_1_vin": "1HGCM82633A004352",
        "vehicle_1_usage": "commute",
        "vehicle_1_ownership": "owned",
        "vehicle_1_lienholder": "",
        "vehicle_1_garaging_zip": "11432",
        "coverage_bi": "50/100",
        "coverage_pd": "50",
        "coverage_pip": "50000",
        "coverage_um": "50/100",
        "coverage_comp": "500",
        "coverage_coll": "500",
        "coverage_term": "6",
        "currently_insured": "yes",
        "prior_carrier": "GEICO",
        "prior_expiration": expiration,
        "prior_lapse_reason": "",
        "voluntary_market_declined": "",
        "declination_carrier": "",
        "mvr_pending": "",
        "carriers_submitted": "1",
        "carriers": list(CARRIER_KEYS),
    }


def clean(today: date) -> dict:
    return _base(today)


def mvr(today: date) -> dict:
    form = _base(today)
    form["mvr_pending"] = "yes"
    return form


def referral(today: date) -> dict:
    form = _base(today)
    form["driver_1_violations"] = "2"
    return form


def assigned(today: date) -> dict:
    form = _base(today)
    form["driver_1_violations"] = "2"
    form["currently_insured"] = ""
    form["prior_carrier"] = ""
    form["prior_expiration"] = ""
    form["prior_lapse_reason"] = "Prior policy cancelled for nonpayment"
    form["voluntary_market_declined"] = "yes"
    form["declination_carrier"] = "Progressive"
    return form


def lapse(today: date) -> dict:
    form = _base(today)
    form["currently_insured"] = ""
    form["prior_carrier"] = ""
    form["prior_expiration"] = ""
    form["prior_lapse_reason"] = ""
    return form


def business_use(today: date) -> dict:
    form = _base(today)
    form["vehicle_1_usage"] = "business"
    return form


def out_of_state(today: date) -> dict:
    form = _base(today)
    form["driver_1_license_state"] = "NJ"
    form["driver_1_license_state_reason"] = ""
    return form


BUILDERS = {
    "clean": clean,
    "mvr": mvr,
    "referral": referral,
    "assigned": assigned,
    "lapse": lapse,
}


def scenario_form(key: str, today: date) -> dict | None:
    builder = BUILDERS.get(key)
    if builder is None:
        return None
    return builder(today)
