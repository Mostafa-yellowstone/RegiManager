"""Validation for auto and commercial auto quote requests.

validate_quote_request(data) returns a list of Issue. Severity "error" blocks
a run; "warning" lets it run but is shown to the agent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
# Carrier portals only quote where they are licensed; the engine refuses unknown states.
_VIN_MAP = dict(zip("ABCDEFGH", range(1, 9)))
_VIN_MAP.update(dict(zip("JKLMN", range(1, 6))))
_VIN_MAP.update({"P": 7, "R": 9})
_VIN_MAP.update(dict(zip("STUVWXYZ", [2, 3, 4, 5, 6, 7, 8, 9])))
_VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
_VIN_YEAR = {c: 1980 + i for i, c in enumerate("ABCDEFGHJKLMNPRSTVWXY")}
_VIN_YEAR.update({c: 2001 + i for i, c in enumerate("123456789")})

# Driver license number formats (regex on cleaned, upper-case value, no spaces/dashes).
# Only states with a well known fixed format are strict; others get a generic check.
DL_FORMATS = {
    "NY": r"\d{9}|[A-Z]\d{18}|\d{8}|[A-Z]{8}",
    "NJ": r"[A-Z]\d{14}",
    "FL": r"[A-Z]\d{12}",
    "CA": r"[A-Z]\d{7}",
    "TX": r"\d{8}",
    "PA": r"\d{8}",
    "IL": r"[A-Z]\d{11}",
    "OH": r"[A-Z]{2}\d{6}|\d{8}",
    "GA": r"\d{7,9}",
    "MA": r"S\d{8}|\d{9}",
    "MI": r"[A-Z]\d{12}",
    "VA": r"[A-Z]\d{8,11}|\d{9}",
    "MD": r"[A-Z]\d{12}",
    "CT": r"\d{9}",
    "WA": r"[A-Z*]{7}[A-Z0-9*]{5}",
}
STATE_MIN_LICENSE_AGE = 15
RELATIONSHIPS = {"self", "spouse", "child", "parent", "sibling", "other", "employee", "owner"}
COMMERCIAL_ENTITY = {"llc", "corporation", "sole_proprietor", "partnership", "nonprofit", "other"}
COMMERCIAL_VEHICLE_CLASSES = {
    "light_truck", "van", "pickup", "box_truck", "dump_truck", "tractor", "trailer",
    "bus", "limo", "taxi_tlc", "tow_truck", "other",
}
AUTO_COVERAGE = {"liability", "full"}
BODILY_INJURY_LIMITS = {"15/30", "25/50", "30/60", "50/100", "100/300", "250/500", "300/500", "500/500"}
COMMERCIAL_CSL = {100000, 300000, 500000, 750000, 1000000, 2000000}
DEDUCTIBLES = {0, 100, 250, 500, 1000, 1500, 2000, 2500, 5000}


@dataclass(frozen=True)
class Issue:
    field: str
    code: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code, "message": self.message, "severity": self.severity}


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)


def _clean(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def parse_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _clean(v)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def vin_check_digit(vin: str) -> str:
    total = 0
    for ch, w in zip(vin, _VIN_WEIGHTS):
        v = int(ch) if ch.isdigit() else _VIN_MAP[ch]
        total += v * w
    r = total % 11
    return "X" if r == 10 else str(r)


def validate_vin(vin: Any, vehicle_year: Any = None, today: date | None = None, field: str = "vin") -> list[Issue]:
    out: list[Issue] = []
    v = re.sub(r"[\s-]", "", str(vin or "")).upper()
    if not v:
        return [Issue(field, "vin_missing", "VIN is required.")]
    if len(v) != 17:
        return [Issue(field, "vin_length", f"VIN must be 17 characters, got {len(v)}.")]
    if re.search(r"[IOQ]", v):
        out.append(Issue(field, "vin_chars", "VIN cannot contain I, O or Q (likely OCR confusion with 1 or 0)."))
        return out
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", v):
        return [Issue(field, "vin_chars", "VIN has invalid characters.")]
    if len(set(v)) <= 2:
        out.append(Issue(field, "vin_repeated", "VIN looks fake (repeated characters)."))
    if vin_check_digit(v) != v[8]:
        # Check digit is only mandatory in North America (WMI starting 1-5), pre-1981 VINs differ.
        sev = "error" if v[0] in "12345" else "warning"
        out.append(Issue(field, "vin_check_digit", f"VIN check digit is wrong (expected {vin_check_digit(v)}, got {v[8]}). Re-read the title/registration.", sev))
    y = _VIN_YEAR.get(v[9])
    if y is not None and vehicle_year not in (None, ""):
        try:
            vy = int(vehicle_year)
            if vy not in (y, y + 30):
                out.append(Issue(field, "vin_year_mismatch", f"VIN year code says {y}, vehicle year entered is {vy}.", "warning"))
        except ValueError:
            pass
    return out


def validate_person(p: dict, prefix: str, today: date, state: str = "", require_license: bool = True) -> list[Issue]:
    out: list[Issue] = []
    f = lambda n: f"{prefix}.{n}"
    for k in ("first_name", "last_name"):
        val = _clean(p.get(k))
        if not val:
            out.append(Issue(f(k), "required", f"{k.replace('_', ' ').title()} is required."))
        elif not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{0,59}", val):
            out.append(Issue(f(k), "name_chars", f"{k.replace('_', ' ').title()} has invalid characters."))
    dob = parse_date(p.get("date_of_birth"))
    if dob is None:
        out.append(Issue(f("date_of_birth"), "dob_invalid", "Date of birth is missing or not a valid date."))
    else:
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if dob > today:
            out.append(Issue(f("date_of_birth"), "dob_future", "Date of birth is in the future."))
        elif age < 14:
            out.append(Issue(f("date_of_birth"), "age_too_young", f"Age {age} is too young to be a driver."))
        elif age > 100:
            out.append(Issue(f("date_of_birth"), "age_too_old", f"Age {age} looks wrong, check the license.", "warning"))
        elif age < 18:
            out.append(Issue(f("date_of_birth"), "age_permit", f"Age {age}: minor or permit driver, most carriers will decline.", "warning"))
        elif age < 25:
            out.append(Issue(f("date_of_birth"), "age_young", f"Age {age}: young driver, expect higher rates or declines.", "warning"))
    lic = re.sub(r"[\s-]", "", str(p.get("license_number") or "")).upper()
    lstate = _clean(p.get("license_state") or state).upper()
    excluded = bool(p.get("excluded"))
    if require_license and not excluded:
        if not lic:
            out.append(Issue(f("license_number"), "required", "Driver license number is required."))
        else:
            if lstate not in US_STATES:
                out.append(Issue(f("license_state"), "state_invalid", "License state is missing or invalid."))
            else:
                fmt = DL_FORMATS.get(lstate)
                if fmt and not re.fullmatch(fmt, lic):
                    out.append(Issue(f("license_number"), "dl_format", f"License number does not match the {lstate} format."))
                elif not fmt and not re.fullmatch(r"[A-Z0-9*]{5,20}", lic):
                    out.append(Issue(f("license_number"), "dl_format", "License number has invalid length or characters."))
    exp = parse_date(p.get("license_expiration"))
    if exp is not None and not excluded:
        if exp < today:
            out.append(Issue(f("license_expiration"), "dl_expired", "License is expired.", "warning" if (today - exp).days <= 365 else "error"))
    lyear = p.get("age_first_licensed")
    if lyear not in (None, ""):
        try:
            a = int(lyear)
            if dob and a < STATE_MIN_LICENSE_AGE:
                out.append(Issue(f("age_first_licensed"), "licensed_age_low", f"Age first licensed {a} is below {STATE_MIN_LICENSE_AGE}."))
            if dob:
                age = today.year - dob.year
                if a > age:
                    out.append(Issue(f("age_first_licensed"), "licensed_age_high", "Age first licensed is greater than current age."))
        except ValueError:
            out.append(Issue(f("age_first_licensed"), "licensed_age_invalid", "Age first licensed must be a number."))
    rel = _clean(p.get("relationship")).lower()
    if rel and rel not in RELATIONSHIPS:
        out.append(Issue(f("relationship"), "relationship_invalid", f"Relationship must be one of: {', '.join(sorted(RELATIONSHIPS))}."))
    for k, label in (("accidents", "accident"), ("violations", "violation"), ("claims", "claim")):
        items = p.get(k) or []
        if not isinstance(items, list):
            out.append(Issue(f(k), "list_invalid", f"{k} must be a list."))
            continue
        for i, it in enumerate(items):
            d = parse_date((it or {}).get("date"))
            if d is None:
                out.append(Issue(f"{prefix}.{k}[{i}].date", "date_invalid", f"Each {label} needs a valid date."))
            elif d > today:
                out.append(Issue(f"{prefix}.{k}[{i}].date", "date_future", f"{label.title()} date is in the future."))
            elif dob and d < dob:
                out.append(Issue(f"{prefix}.{k}[{i}].date", "date_before_birth", f"{label.title()} date is before date of birth."))
        if len(items) >= 3:
            out.append(Issue(f(k), "many_incidents", f"{len(items)} {k}: expect declines at standard carriers.", "warning"))
    return out


def validate_address(a: dict, prefix: str) -> list[Issue]:
    out: list[Issue] = []
    if not _clean(a.get("street")):
        out.append(Issue(f"{prefix}.street", "required", "Street address is required."))
    elif not re.search(r"\d", a["street"]) and not re.match(r"(?i)\s*p\.?o\.? box", a["street"]):
        out.append(Issue(f"{prefix}.street", "street_no_number", "Street address has no number.", "warning"))
    if _clean(a.get("street")).lower().startswith(("po box", "p.o. box", "p o box")):
        out.append(Issue(f"{prefix}.street", "po_box", "PO Box cannot be a garaging address.", "error" if prefix.startswith("garaging") else "warning"))
    if not _clean(a.get("city")):
        out.append(Issue(f"{prefix}.city", "required", "City is required."))
    st = _clean(a.get("state")).upper()
    if st not in US_STATES:
        out.append(Issue(f"{prefix}.state", "state_invalid", "State must be a valid 2 letter US state."))
    z = _clean(a.get("zip"))
    if not re.fullmatch(r"\d{5}(-\d{4})?", z):
        out.append(Issue(f"{prefix}.zip", "zip_invalid", "ZIP must be 5 digits (or ZIP+4)."))
    elif z in ("00000", "99999", "12345"):
        out.append(Issue(f"{prefix}.zip", "zip_fake", "ZIP looks like a placeholder."))
    return out


def validate_vehicle(v: dict, idx: int, today: date, commercial: bool) -> list[Issue]:
    out: list[Issue] = []
    prefix = f"vehicles[{idx}]"
    out += validate_vin(v.get("vin"), v.get("year"), today, f"{prefix}.vin")
    try:
        yr = int(v.get("year"))
        if yr < 1981 or yr > today.year + 2:
            out.append(Issue(f"{prefix}.year", "year_range", f"Vehicle year {yr} is outside 1981 to {today.year + 2}.", "error" if yr > today.year + 2 else "warning"))
        elif today.year - yr >= 25:
            out.append(Issue(f"{prefix}.year", "classic", "Vehicle is 25+ years old: may need classic or liability only.", "warning"))
    except (TypeError, ValueError):
        out.append(Issue(f"{prefix}.year", "year_invalid", "Vehicle year is required and must be a number."))
    for k in ("make", "model"):
        if not _clean(v.get(k)):
            out.append(Issue(f"{prefix}.{k}", "required", f"Vehicle {k} is required."))
    odo = v.get("odometer")
    if odo not in (None, ""):
        try:
            if int(odo) < 0 or int(odo) > 999999:
                out.append(Issue(f"{prefix}.odometer", "odometer_range", "Odometer is out of range."))
        except ValueError:
            out.append(Issue(f"{prefix}.odometer", "odometer_invalid", "Odometer must be a number."))
    own = _clean(v.get("ownership")).lower()
    if own not in ("owned", "financed", "leased"):
        out.append(Issue(f"{prefix}.ownership", "ownership_invalid", "Ownership must be owned, financed or leased."))
    if own in ("financed", "leased") and not _clean(v.get("lienholder")):
        out.append(Issue(f"{prefix}.lienholder", "lienholder_required", "Lienholder is required for financed or leased vehicles."))
    ded = v.get("deductible_comp")
    for k in ("deductible_comp", "deductible_collision"):
        d = v.get(k)
        if d not in (None, "") and int(d) not in DEDUCTIBLES:
            out.append(Issue(f"{prefix}.{k}", "deductible_invalid", f"Deductible must be one of {sorted(DEDUCTIBLES)}."))
    if own in ("financed", "leased") and v.get("coverage") == "liability":
        out.append(Issue(f"{prefix}.coverage", "lien_needs_full", "Lienholders require comp and collision, liability-only will be declined.", "warning"))
    if commercial:
        vc = _clean(v.get("vehicle_class")).lower()
        if vc not in COMMERCIAL_VEHICLE_CLASSES:
            out.append(Issue(f"{prefix}.vehicle_class", "class_invalid", "Commercial vehicle class is required."))
        gvw = v.get("gvw")
        try:
            g = int(gvw)
            if g < 1000 or g > 80000:
                out.append(Issue(f"{prefix}.gvw", "gvw_range", "GVW must be between 1,000 and 80,000 lbs."))
        except (TypeError, ValueError):
            out.append(Issue(f"{prefix}.gvw", "gvw_required", "GVW (lbs) is required for commercial vehicles."))
        radius = v.get("radius_miles")
        try:
            r = int(radius)
            if r < 1 or r > 3000:
                out.append(Issue(f"{prefix}.radius_miles", "radius_range", "Radius of operation is out of range."))
            elif r > 200:
                out.append(Issue(f"{prefix}.radius_miles", "long_haul", "Radius over 200 miles: needs long-haul carriers.", "warning"))
        except (TypeError, ValueError):
            out.append(Issue(f"{prefix}.radius_miles", "radius_required", "Radius of operation is required."))
    return out


def validate_policy(data: dict, today: date, commercial: bool) -> list[Issue]:
    out: list[Issue] = []
    eff = parse_date(data.get("effective_date"))
    if eff is None:
        out.append(Issue("effective_date", "date_invalid", "Effective date is required."))
    else:
        if eff < today:
            out.append(Issue("effective_date", "date_past", "Effective date is in the past."))
        elif (eff - today).days > 90:
            out.append(Issue("effective_date", "date_far", "Effective date is more than 90 days away: carriers will not quote.", "warning"))
    prior = data.get("prior_insurance") or {}
    if prior.get("has_prior"):
        pe = parse_date(prior.get("expiration_date"))
        if pe is None:
            out.append(Issue("prior_insurance.expiration_date", "date_invalid", "Prior policy expiration date is required."))
        elif eff and pe < eff and (eff - pe).days > 30:
            out.append(Issue("prior_insurance.expiration_date", "lapse", f"Coverage lapse of {(eff - pe).days} days: surcharge or declines.", "warning"))
        if not _clean(prior.get("carrier")):
            out.append(Issue("prior_insurance.carrier", "required", "Prior carrier name is required when there is prior insurance."))
        try:
            if int(prior.get("months_with_carrier", 0)) < 0:
                raise ValueError
        except ValueError:
            out.append(Issue("prior_insurance.months_with_carrier", "months_invalid", "Months with prior carrier must be 0 or more."))
    else:
        out.append(Issue("prior_insurance", "no_prior", "No prior insurance: non-standard carriers only, higher rates.", "warning"))
    lim = _clean(data.get("bodily_injury_limit"))
    if commercial:
        try:
            if int(data.get("csl_limit")) not in COMMERCIAL_CSL:
                out.append(Issue("csl_limit", "csl_invalid", f"Combined single limit must be one of {sorted(COMMERCIAL_CSL)}."))
        except (TypeError, ValueError):
            out.append(Issue("csl_limit", "csl_required", "Combined single limit is required."))
    else:
        if lim not in BODILY_INJURY_LIMITS:
            out.append(Issue("bodily_injury_limit", "limit_invalid", f"Bodily injury limit must be one of {sorted(BODILY_INJURY_LIMITS)}."))
    return out


def validate_business(b: dict) -> list[Issue]:
    out: list[Issue] = []
    if not _clean(b.get("legal_name")):
        out.append(Issue("business.legal_name", "required", "Legal business name is required."))
    if _clean(b.get("entity_type")).lower() not in COMMERCIAL_ENTITY:
        out.append(Issue("business.entity_type", "entity_invalid", f"Entity type must be one of {sorted(COMMERCIAL_ENTITY)}."))
    fein = re.sub(r"\D", "", str(b.get("fein") or ""))
    if b.get("fein") and (len(fein) != 9 or fein[:2] in ("00", "07", "08", "09", "17", "18", "19", "28", "29", "49", "69", "70", "78", "79", "89", "96", "97")):
        out.append(Issue("business.fein", "fein_invalid", "FEIN must be 9 digits with a valid IRS prefix."))
    elif _clean(b.get("entity_type")).lower() in ("llc", "corporation", "partnership") and not fein:
        out.append(Issue("business.fein", "fein_required", "FEIN is required for this entity type.", "warning"))
    dot = _clean(b.get("usdot"))
    if dot and not re.fullmatch(r"\d{5,8}", dot):
        out.append(Issue("business.usdot", "usdot_invalid", "USDOT number must be 5 to 8 digits."))
    yrs = b.get("years_in_business")
    try:
        y = int(yrs)
        if y < 0 or y > 200:
            raise ValueError
        if y < 1:
            out.append(Issue("business.years_in_business", "new_venture", "New venture (<1 year): fewer carriers will quote.", "warning"))
    except (TypeError, ValueError):
        out.append(Issue("business.years_in_business", "years_invalid", "Years in business is required."))
    if not _clean(b.get("operation_type")):
        out.append(Issue("business.operation_type", "required", "Type of operation (what the business hauls or does) is required."))
    return out


def validate_contact(c: dict) -> list[Issue]:
    out: list[Issue] = []
    email = _clean(c.get("email"))
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email):
        out.append(Issue("contact.email", "email_invalid", "Email is not valid."))
    phone = re.sub(r"\D", "", str(c.get("phone") or ""))
    if phone.startswith("1") and len(phone) == 11:
        phone = phone[1:]
    if not phone:
        out.append(Issue("contact.phone", "required", "Phone is required."))
    elif len(phone) != 10 or phone[0] in "01" or phone[3] in "01":
        out.append(Issue("contact.phone", "phone_invalid", "Phone must be a valid 10 digit US number."))
    elif phone[3:6] == "555" and phone[6:8] == "01":
        out.append(Issue("contact.phone", "phone_fake", "Phone looks fake."))
    return out


def validate_quote_request(data: dict, today: date | None = None) -> list[Issue]:
    """Validate a whole request. line_of_business is 'auto' or 'commercial_auto'."""
    today = today or date.today()
    out: list[Issue] = []
    lob = _clean(data.get("line_of_business")).lower()
    if lob not in ("auto", "commercial_auto"):
        return [Issue("line_of_business", "lob_invalid", "Line must be 'auto' or 'commercial_auto'. Other lines are not supported.")]
    commercial = lob == "commercial_auto"
    out += validate_contact(data.get("contact") or {})
    out += validate_address(data.get("garaging_address") or {}, "garaging_address")
    state = _clean((data.get("garaging_address") or {}).get("state")).upper()
    mailing = data.get("mailing_address")
    if mailing:
        out += validate_address(mailing, "mailing_address")
    if commercial:
        out += validate_business(data.get("business") or {})
    drivers = data.get("drivers") or []
    if not drivers:
        out.append(Issue("drivers", "required", "At least one driver is required."))
    seen: set[tuple] = set()
    seen_lic: set[str] = set()
    for i, d in enumerate(drivers):
        out += validate_person(d, f"drivers[{i}]", today, state)
        key = (_clean(d.get("first_name")).lower(), _clean(d.get("last_name")).lower(), str(d.get("date_of_birth")))
        if key in seen:
            out.append(Issue(f"drivers[{i}]", "duplicate_driver", "Duplicate driver (same name and date of birth)."))
        seen.add(key)
        lic = re.sub(r"[\s-]", "", str(d.get("license_number") or "")).upper()
        if lic:
            if lic in seen_lic:
                out.append(Issue(f"drivers[{i}].license_number", "duplicate_license", "Same license number used for two drivers."))
            seen_lic.add(lic)
    if drivers and not any(_clean(d.get("relationship")).lower() in ("self", "owner", "") for d in drivers):
        out.append(Issue("drivers", "no_named_insured", "No driver is marked as the named insured (self/owner).", "warning"))
    vehicles = data.get("vehicles") or []
    if not vehicles:
        out.append(Issue("vehicles", "required", "At least one vehicle is required."))
    vins: set[str] = set()
    for i, v in enumerate(vehicles):
        out += validate_vehicle(v, i, today, commercial)
        vin = re.sub(r"[\s-]", "", str(v.get("vin") or "")).upper()
        if vin and vin in vins:
            out.append(Issue(f"vehicles[{i}].vin", "duplicate_vin", "Same VIN entered for two vehicles."))
        vins.add(vin)
        if not commercial and _clean(v.get("use")).lower() in ("business", "delivery", "rideshare"):
            out.append(Issue(f"vehicles[{i}].use", "use_mismatch", "Business/delivery/rideshare use: consider commercial auto.", "warning"))
    if drivers and vehicles and len(drivers) < len(vehicles) and not commercial:
        out.append(Issue("drivers", "fewer_drivers", "Fewer drivers than vehicles: carriers may require all household drivers.", "warning"))
    out += validate_policy(data, today, commercial)
    return out
