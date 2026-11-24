"""Build an application from the quoting form. Blank stays blank."""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from quoting.engine.types import (
    Application,
    Coverage,
    Driver,
    NamedInsured,
    PriorInsurance,
    Vehicle,
)

NY = ZoneInfo("America/New_York")
_TRUE = {"1", "true", "yes", "on"}


def ny_today() -> date:
    return datetime.now(NY).date()


def _text(data, key: str) -> str:
    if hasattr(data, "getlist"):
        values = data.getlist(key)
        raw = values[-1] if values else ""
    else:
        raw = data.get(key, "")
        if isinstance(raw, (list, tuple)):
            raw = raw[-1] if raw else ""
    return str(raw or "").strip()


def _all(data, key: str) -> list[str]:
    if hasattr(data, "getlist"):
        return [str(value).strip() for value in data.getlist(key) if str(value).strip()]
    raw = data.get(key, [])
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    return [str(value).strip() for value in raw if str(value).strip()]


def _flag(data, key: str) -> bool:
    return _text(data, key).lower() in _TRUE


def _date(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _int(raw: str) -> int | None:
    if raw == "":
        return None
    if not re.fullmatch(r"-?\d+", raw):
        return None
    return int(raw)


def _zip(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) in (5, 9):
        return digits[:5]
    return raw.strip()


def _deductible(raw: str) -> int | None:
    if raw == "" or raw.lower() == "none":
        return None
    return _int(raw)


def _occupied(data, prefix: str, fields: tuple[str, ...]) -> bool:
    return any(_text(data, f"{prefix}_{field}") for field in fields)


def parse_form(data, *, line: str = "personal_auto", jurisdiction: str = "NY") -> tuple[Application, tuple[str, ...]]:
    """Return the application and the fields whose values were not usable."""

    invalid: list[str] = []

    def take_date(key: str) -> date | None:
        raw = _text(data, key)
        if not raw:
            return None
        parsed = _date(raw)
        if parsed is None:
            invalid.append(key)
        return parsed

    def take_int(key: str) -> int | None:
        raw = _text(data, key)
        if raw == "":
            return None
        parsed = _int(raw)
        if parsed is None:
            invalid.append(key)
        return parsed

    insured = NamedInsured(
        first_name=_text(data, "insured_first_name"),
        last_name=_text(data, "insured_last_name"),
        date_of_birth=take_date("insured_date_of_birth"),
        phone=_text(data, "insured_phone"),
        email=_text(data, "insured_email"),
        street=_text(data, "insured_street"),
        city=_text(data, "insured_city"),
        state=_text(data, "insured_state").upper(),
        zip_code=_zip(_text(data, "insured_zip")),
    )

    drivers = []
    driver_fields = (
        "first_name",
        "last_name",
        "date_of_birth",
        "license_number",
        "license_state",
        "license_state_reason",
        "relationship",
        "years_licensed",
        "accidents",
        "violations",
    )
    for index in range(1, 7):
        prefix = f"driver_{index}"
        if not _occupied(data, prefix, driver_fields) and not _flag(data, f"{prefix}_mvr_required"):
            continue
        drivers.append(
            Driver(
                index=index,
                first_name=_text(data, f"{prefix}_first_name"),
                last_name=_text(data, f"{prefix}_last_name"),
                date_of_birth=take_date(f"{prefix}_date_of_birth"),
                license_number=_text(data, f"{prefix}_license_number").upper(),
                license_state=_text(data, f"{prefix}_license_state").upper(),
                license_state_reason=_text(data, f"{prefix}_license_state_reason"),
                relationship=_text(data, f"{prefix}_relationship"),
                years_licensed=take_int(f"{prefix}_years_licensed"),
                accidents=take_int(f"{prefix}_accidents"),
                violations=take_int(f"{prefix}_violations"),
                mvr_required=_flag(data, f"{prefix}_mvr_required"),
            )
        )

    vehicles = []
    vehicle_fields = ("year", "make", "model", "vin", "usage", "ownership", "lienholder", "garaging_zip")
    for index in range(1, 5):
        prefix = f"vehicle_{index}"
        if not _occupied(data, prefix, vehicle_fields):
            continue
        vin = re.sub(r"\s+", "", _text(data, f"{prefix}_vin")).upper()
        if vin and not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
            invalid.append(f"{prefix}_vin")
            vin = ""
        vehicles.append(
            Vehicle(
                index=index,
                year=take_int(f"{prefix}_year"),
                make=_text(data, f"{prefix}_make"),
                model=_text(data, f"{prefix}_model"),
                vin=vin,
                usage=_text(data, f"{prefix}_usage"),
                ownership=_text(data, f"{prefix}_ownership"),
                lienholder=_text(data, f"{prefix}_lienholder"),
                garaging_zip=_zip(_text(data, f"{prefix}_garaging_zip")),
            )
        )

    comp_raw = _text(data, "coverage_comp")
    coll_raw = _text(data, "coverage_coll")
    comp = _deductible(comp_raw)
    coll = _deductible(coll_raw)
    if comp_raw not in ("", "none") and comp is None:
        invalid.append("coverage_comp")
    if coll_raw not in ("", "none") and coll is None:
        invalid.append("coverage_coll")

    coverage = Coverage(
        bodily_injury=_text(data, "coverage_bi"),
        property_damage=_text(data, "coverage_pd"),
        pip=_text(data, "coverage_pip"),
        uninsured_motorist=_text(data, "coverage_um"),
        comprehensive_deductible=comp,
        collision_deductible=coll,
        term_months=take_int("coverage_term"),
    )
    prior = PriorInsurance(
        currently_insured=_flag(data, "currently_insured"),
        carrier=_text(data, "prior_carrier"),
        expiration=take_date("prior_expiration"),
        lapse_reason=_text(data, "prior_lapse_reason"),
    )
    application = Application(
        line=line,
        jurisdiction=jurisdiction,
        effective_date=take_date("effective_date"),
        named_insured=insured,
        drivers=tuple(drivers),
        vehicles=tuple(vehicles),
        coverage=coverage,
        prior=prior,
        voluntary_market_declined=_flag(data, "voluntary_market_declined"),
        declination_carrier=_text(data, "declination_carrier"),
        mvr_pending=_flag(data, "mvr_pending"),
        invalid_fields=tuple(dict.fromkeys(invalid)),
    )
    return application, tuple(application.invalid_fields)


def requested_carriers(data) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_all(data, "carriers")))


def requested_mode(data) -> str:
    mode = _text(data, "run") or "demo"
    return mode if mode in ("demo", "live") else "demo"
