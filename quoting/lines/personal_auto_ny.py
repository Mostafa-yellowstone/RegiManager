"""Intake rules for New York personal auto.

Limits follow the coverages New York requires for a private passenger auto:
liability of at least 25/50/10, basic no-fault PIP of $50,000, and uninsured
motorist of at least 25/50. The agent picks the limit. Blank answers stay blank.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from quoting.engine.types import Application, Issue

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
BI_LIMITS = ("25/50", "50/100", "100/300", "250/500")
PD_LIMITS = ("10", "25", "50", "100")
PIP_LIMITS = ("50000", "100000")
DEDUCTIBLES = (100, 250, 500, 1000)
RELATIONSHIPS = ("named_insured", "spouse", "child", "parent", "other")
USAGES = ("pleasure", "commute", "business")
OWNERSHIP = ("owned", "financed", "leased")
TERM_MONTHS = (6, 12)
MAX_DRIVERS = 6
MAX_VEHICLES = 4
MAX_EFFECTIVE_DAYS = 60


def _age(dob: date, on: date) -> int:
    years = on.year - dob.year
    if (on.month, on.day) < (dob.month, dob.day):
        years -= 1
    return years


def _split_limit(raw: str) -> tuple[int, int] | None:
    parts = raw.split("/")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1])


def validate(application: Application, *, today: date) -> tuple[Issue, ...]:
    issues: list[Issue] = []
    invalid = set(application.invalid_fields)

    def bad(field: str, message: str) -> None:
        issues.append(Issue(field, message))

    if "effective_date" in invalid:
        bad("effective_date", "Effective date must be YYYY-MM-DD.")
    elif application.effective_date is None:
        bad("effective_date", "Effective date is required.")
    else:
        if application.effective_date < today:
            bad("effective_date", "Effective date must be today or later.")
        elif application.effective_date > today + timedelta(days=MAX_EFFECTIVE_DAYS):
            bad(
                "effective_date",
                "Effective date is more than 60 days out. v1 quotes an effective date inside that window.",
            )

    insured = application.named_insured
    if "insured_date_of_birth" in invalid:
        bad("insured_date_of_birth", "Named insured date of birth must be YYYY-MM-DD.")
    if not insured.first_name:
        bad("insured_first_name", "Named insured first name is required.")
    if not insured.last_name:
        bad("insured_last_name", "Named insured last name is required.")
    if "insured_date_of_birth" not in invalid:
        if insured.date_of_birth is None:
            bad("insured_date_of_birth", "Named insured date of birth is required.")
        elif insured.date_of_birth > today:
            bad("insured_date_of_birth", "Named insured date of birth is in the future.")
        elif _age(insured.date_of_birth, today) < 18:
            bad("insured_date_of_birth", "Named insured must be 18 or older.")
    digits = re.sub(r"\D", "", insured.phone)
    if len(digits) < 10:
        bad("insured_phone", "A phone number with at least 10 digits is required.")
    if insured.email and ("@" not in insured.email or " " in insured.email):
        bad("insured_email", "Email must look like a single address, or be left blank.")
    if not insured.street:
        bad("insured_street", "Garaging street address is required.")
    if not insured.city:
        bad("insured_city", "City is required.")
    if insured.state != "NY":
        bad("insured_state", "v1 quotes New York personal auto. The garaging state has to be NY.")
    if not re.fullmatch(r"\d{5}", insured.zip_code or ""):
        bad("insured_zip", "ZIP code must be 5 digits.")

    if not application.drivers:
        bad("drivers", "At least one driver is required.")
    elif len(application.drivers) > MAX_DRIVERS:
        bad("drivers", f"v1 quotes up to {MAX_DRIVERS} drivers.")
    named = 0
    for driver in application.drivers:
        prefix = f"driver_{driver.index}"
        if not driver.first_name:
            bad(f"{prefix}_first_name", f"{driver.display_name}: first name is required.")
        if not driver.last_name:
            bad(f"{prefix}_last_name", f"{driver.display_name}: last name is required.")
        dob_field = f"{prefix}_date_of_birth"
        if dob_field in invalid:
            bad(dob_field, f"{driver.display_name}: date of birth must be YYYY-MM-DD.")
        elif driver.date_of_birth is None:
            bad(dob_field, f"{driver.display_name}: date of birth is required.")
        elif driver.date_of_birth > today:
            bad(dob_field, f"{driver.display_name}: date of birth is in the future.")
        elif _age(driver.date_of_birth, today) < 16:
            bad(dob_field, f"{driver.display_name}: driver must be 16 or older.")
        if len(driver.license_number.strip()) < 4:
            bad(f"{prefix}_license_number", f"{driver.display_name}: license number is required.")
        if not re.fullmatch(r"[A-Z]{2}", driver.license_state or ""):
            bad(f"{prefix}_license_state", f"{driver.display_name}: license state must be a 2-letter code.")
        if driver.relationship not in RELATIONSHIPS:
            bad(f"{prefix}_relationship", f"{driver.display_name}: choose how this driver is related.")
        if driver.relationship == "named_insured":
            named += 1
        years_field = f"{prefix}_years_licensed"
        if years_field in invalid:
            bad(years_field, f"{driver.display_name}: years licensed must be a whole number.")
        elif driver.years_licensed is None:
            bad(years_field, f"{driver.display_name}: years licensed is required. Use 0 for a new driver.")
        elif not 0 <= driver.years_licensed <= 80:
            bad(years_field, f"{driver.display_name}: years licensed must be from 0 to 80.")
        for attr, label in (("accidents", "accidents"), ("violations", "violations")):
            field_name = f"{prefix}_{attr}"
            value = getattr(driver, attr)
            if field_name in invalid:
                bad(field_name, f"{driver.display_name}: {label} in the last 3 years must be a whole number.")
            elif value is None:
                bad(field_name, f"{driver.display_name}: enter {label} in the last 3 years, including 0.")
            elif value < 0 or value > 20:
                bad(field_name, f"{driver.display_name}: {label} must be from 0 to 20.")
    if application.drivers and named != 1:
        bad("drivers", "Mark exactly one driver as the named insured.")

    if not application.vehicles:
        bad("vehicles", "At least one vehicle is required.")
    elif len(application.vehicles) > MAX_VEHICLES:
        bad("vehicles", f"v1 quotes up to {MAX_VEHICLES} vehicles.")
    for vehicle in application.vehicles:
        prefix = f"vehicle_{vehicle.index}"
        label = vehicle.display_name
        year_field = f"{prefix}_year"
        if year_field in invalid:
            bad(year_field, f"{label}: model year must be a 4-digit year.")
        elif vehicle.year is None:
            bad(year_field, f"{label}: model year is required.")
        elif not 1981 <= vehicle.year <= today.year + 1:
            bad(year_field, f"{label}: model year must be from 1981 through {today.year + 1}.")
        if not vehicle.make:
            bad(f"{prefix}_make", f"{label}: make is required.")
        if not vehicle.model:
            bad(f"{prefix}_model", f"{label}: model is required.")
        if f"{prefix}_vin" in invalid:
            bad(f"{prefix}_vin", f"{label}: VIN must be 17 characters and cannot contain I, O, or Q.")
        elif not VIN_RE.fullmatch(vehicle.vin or ""):
            bad(f"{prefix}_vin", f"{label}: a 17-character VIN is required. Letters I, O, and Q are not used.")
        if vehicle.usage not in USAGES:
            bad(f"{prefix}_usage", f"{label}: choose pleasure, commute, or business use.")
        if vehicle.ownership not in OWNERSHIP:
            bad(f"{prefix}_ownership", f"{label}: choose owned, financed, or leased.")
        elif vehicle.ownership in ("financed", "leased") and not vehicle.lienholder:
            bad(f"{prefix}_lienholder", f"{label}: lienholder is required when the vehicle is {vehicle.ownership}.")
        if not re.fullmatch(r"\d{5}", vehicle.garaging_zip or ""):
            bad(f"{prefix}_garaging_zip", f"{label}: garaging ZIP must be 5 digits.")

    coverage = application.coverage
    if coverage.bodily_injury not in BI_LIMITS:
        bad("coverage_bi", "Choose a bodily injury limit of 25/50, 50/100, 100/300, or 250/500.")
    if coverage.property_damage not in PD_LIMITS:
        bad("coverage_pd", "Choose a property damage limit of 10, 25, 50, or 100.")
    if coverage.pip not in PIP_LIMITS:
        bad("coverage_pip", "Choose basic PIP of 50,000 or optional PIP of 100,000.")
    um = _split_limit(coverage.uninsured_motorist)
    if coverage.uninsured_motorist not in BI_LIMITS or um is None:
        bad("coverage_um", "Choose an uninsured motorist limit of 25/50, 50/100, 100/300, or 250/500.")
    elif um[0] < 25 or um[1] < 50:
        bad("coverage_um", "New York uninsured motorist coverage has to be at least 25/50.")
    comp = coverage.comprehensive_deductible
    coll = coverage.collision_deductible
    comp_bad = "coverage_comp" in invalid
    coll_bad = "coverage_coll" in invalid
    if comp_bad:
        bad("coverage_comp", "Comprehensive deductible must be 100, 250, 500, 1000, or blank.")
    if coll_bad:
        bad("coverage_coll", "Collision deductible must be 100, 250, 500, 1000, or blank.")
    if not comp_bad and comp is not None and comp not in DEDUCTIBLES:
        bad("coverage_comp", "Comprehensive deductible must be 100, 250, 500, or 1000.")
    if not coll_bad and coll is not None and coll not in DEDUCTIBLES:
        bad("coverage_coll", "Collision deductible must be 100, 250, 500, or 1000.")
    if not comp_bad and not coll_bad and (comp is None) != (coll is None):
        bad(
            "coverage_comp",
            "Choose both comprehensive and collision deductibles, or leave both blank for liability only.",
        )
    if "coverage_term" in invalid or coverage.term_months not in TERM_MONTHS:
        bad("coverage_term", "Policy term must be 6 or 12 months.")

    prior = application.prior
    if prior.currently_insured:
        if not prior.carrier:
            bad("prior_carrier", "Current carrier is required while the applicant is insured.")
        if "prior_expiration" in invalid:
            bad("prior_expiration", "Current policy expiration must be YYYY-MM-DD.")
        elif prior.expiration is None:
            bad("prior_expiration", "Current policy expiration is required while the applicant is insured.")

    return tuple(issues)
