"""Value types for an application, a carrier result, and a quote job."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Issue:
    field: str
    message: str

    def to_dict(self) -> dict:
        return {"field": self.field, "message": self.message}


@dataclass(frozen=True)
class NamedInsured:
    first_name: str
    last_name: str
    date_of_birth: date | None
    phone: str
    email: str
    street: str
    city: str
    state: str
    zip_code: str


@dataclass(frozen=True)
class Driver:
    index: int
    first_name: str
    last_name: str
    date_of_birth: date | None
    license_number: str
    license_state: str
    license_state_reason: str
    relationship: str
    years_licensed: int | None
    accidents: int | None
    violations: int | None
    mvr_required: bool

    @property
    def display_name(self) -> str:
        name = " ".join(part for part in (self.first_name, self.last_name) if part).strip()
        return name or f"Driver {self.index}"


@dataclass(frozen=True)
class Vehicle:
    index: int
    year: int | None
    make: str
    model: str
    vin: str
    usage: str
    ownership: str
    lienholder: str
    garaging_zip: str

    @property
    def display_name(self) -> str:
        bits = [str(self.year) if self.year else "", self.make, self.model]
        label = " ".join(bit for bit in bits if bit).strip()
        return label or f"Vehicle {self.index}"


@dataclass(frozen=True)
class Coverage:
    bodily_injury: str
    property_damage: str
    pip: str
    uninsured_motorist: str
    comprehensive_deductible: int | None
    collision_deductible: int | None
    term_months: int | None


@dataclass(frozen=True)
class PriorInsurance:
    currently_insured: bool
    carrier: str
    expiration: date | None
    lapse_reason: str


@dataclass(frozen=True)
class Application:
    """One personal-auto application. Other lines can add their own type later."""

    line: str
    jurisdiction: str
    effective_date: date | None
    named_insured: NamedInsured
    drivers: tuple[Driver, ...]
    vehicles: tuple[Vehicle, ...]
    coverage: Coverage
    prior: PriorInsurance
    voluntary_market_declined: bool
    declination_carrier: str
    mvr_pending: bool
    invalid_fields: tuple[str, ...] = field(default_factory=tuple)

    @property
    def applicant_label(self) -> str:
        insured = self.named_insured
        name = " ".join(part for part in (insured.first_name, insured.last_name) if part).strip()
        return name or "Applicant"


@dataclass(frozen=True)
class Blocker:
    code: str
    title: str
    detail: str
    missing: tuple[str, ...]
    origin: str

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "title": self.title,
            "detail": self.detail,
            "missing": list(self.missing),
            "origin": self.origin,
        }


@dataclass(frozen=True)
class QuoteOffer:
    quote_number: str
    term_premium: Decimal
    term_months: int
    coverages: tuple[tuple[str, str], ...]
    source: str
    illustrative: bool
    note: str

    def to_dict(self) -> dict:
        return {
            "quote_number": self.quote_number,
            "term_premium": f"{self.term_premium:.2f}",
            "term_months": self.term_months,
            "coverages": [{"label": label, "value": value} for label, value in self.coverages],
            "source": self.source,
            "illustrative": self.illustrative,
            "note": self.note,
        }


@dataclass(frozen=True)
class CarrierResult:
    carrier_key: str
    carrier_name: str
    portal_url: str
    status: str
    offer: QuoteOffer | None = None
    blocker: Blocker | None = None

    def __post_init__(self) -> None:
        if self.status == "quoted" and (self.offer is None or self.blocker is not None):
            raise ValueError("A quoted result needs an offer and no blocker.")
        if self.status != "quoted" and self.offer is not None:
            raise ValueError("A stopped result cannot carry a premium.")

    def to_dict(self) -> dict:
        return {
            "carrier_key": self.carrier_key,
            "carrier_name": self.carrier_name,
            "portal_url": self.portal_url,
            "status": self.status,
            "offer": None if self.offer is None else self.offer.to_dict(),
            "blocker": None if self.blocker is None else self.blocker.to_dict(),
        }


@dataclass(frozen=True)
class JobResult:
    status: str
    mode: str
    issues: tuple[Issue, ...]
    results: tuple[CarrierResult, ...]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "mode": self.mode,
            "issues": [issue.to_dict() for issue in self.issues],
            "results": [result.to_dict() for result in self.results],
        }
