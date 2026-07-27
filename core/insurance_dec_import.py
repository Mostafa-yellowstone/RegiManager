"""Parse insurance declaration page PDFs and apply data to policies.

Supported text-based carriers:
  - Integon / National General / GMAC
  - NYAIP / NY Automobile Insurance Plan / 21st Century AIP
  - Maya Assurance (business auto)
  - Progressive (text-layer PDFs)

Scanned image-only Progressive/DEC PDFs need a text-based export or OCR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import BinaryIO

from django.db import transaction
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from .models import (
    Client,
    InsuranceCompany,
    InsurancePolicy,
    InsurancePolicyDocument,
    InsurancePolicyDriver,
    InsurancePolicyInstallment,
    InsurancePolicyVehicle,
)

ZERO = Decimal("0.00")
_DATE_MDY = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})")
_MONEY = re.compile(r"\$?\s*([\d,]+\.\d{2})")
_VIN = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_VEHICLE_ROW = re.compile(
    r"^\s*(\d+)\s+(\d{4})\s+([A-Z][A-Z0-9-]*)\s+([A-HJ-NPR-Z0-9]{17})\s",
    re.M,
)
_SINGLE_CAR_VEHICLE_ROW = re.compile(
    r"^([A-Z][A-Z0-9-]*)\s+(\d{4})\s+([A-Z0-9-]+)\s+([A-HJ-NPR-Z0-9]{17})(?:\s+\S+\s+\d+\s+(\S+))?",
    re.M,
)
_LOOSE_VEHICLE_ROW = re.compile(
    r"(?im)(?:Vehicle|Auto|Veh\.?)\s*#?\s*(\d+)?\s*[:\-]?\s*"
    r"(?:(\d{4})\s+)?([A-Za-z][A-Za-z0-9 \-]{1,20})?\s*"
    r"(?:VIN[:\s#]*)?([A-HJ-NPR-Z0-9]{17})",
)
# Maya: "2024, TOYOTA, HIGHLANDER, 5TDKDRBH0RS564584"
_MAYA_VEHICLE_ROW = re.compile(
    r"(?im)(\d{4})\s*,\s*([A-Za-z][A-Za-z0-9 \-]{1,24})\s*,\s*([A-Za-z0-9 \-/]{1,30})\s*,\s*"
    r"([A-HJ-NPR-Z0-9]{17})",
)
# AIP: "1 55 35 32 7 20 TOYOTA SIENNA" then VIN on a later line
_AIP_VEHICLE_ROW = re.compile(
    r"(?im)^\s*(\d+)\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d{2,4})\s+([A-Z][A-Z0-9 \-]{2,40})\s*$",
)
_DRIVER_ROW = re.compile(
    r"^([A-Z][A-Z'-]+,[A-Z][A-Z\s'-]+?)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    re.M,
)
_SINGLE_CAR_DRIVER_ROW = re.compile(
    r"DRIVER\s+(\d+)\.\s+([A-Z][A-Z\s'-]+?)(?=\s+DRIVER\s+\d+\.|\s*$)",
    re.M,
)
_LABELED_DRIVER = re.compile(
    r"(?im)(?:Driver|Operator)\s*#?\s*\d*\s*[:\-]\s*([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,4})",
)
_AIP_DRIVER_ROW = re.compile(
    r"(?im)^\s*(\d+)\)\s+([A-Z][A-Z\s'\-]{2,60})\s*$",
)
_MAYA_DRIVER_BLOCK = re.compile(
    r"(?is)DRIVERS?\s+SCHEDULE\s*(.*?)(?:COVERAGE-|ITEM\s+FOUR|TOTAL\s+PREMIUM|$)",
)
_PAYMENT_ROW = re.compile(
    r"(?im)^\s*(DEPOSIT|DOWN\s*PAYMENT|INSTALLMENT\s*#?\s*\d+|Bill\s*#\s*\d+|PMT\s*#?\s*\d+|"
    r"Payment\s*\d+)\s+"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+"
    r"\$?\s*([\d,]+\.\d{2})",
)
_SUPPORTED_CARRIERS_MSG = (
    "Supported text-based declaration PDFs: Progressive, Integon/National General, "
    "NYAIP / NY Automobile Insurance Plan (incl. 21st Century AIP), and Maya Assurance. "
    "Scanned image-only PDFs cannot be read — export/print as a text PDF or use a searchable DEC."
)


class DecPageParseError(Exception):
    """Raised when a declaration page cannot be parsed."""


@dataclass
class DecVehicle:
    auto_number: int
    year: int | None = None
    make: str = ""
    vin: str = ""
    plate: str = ""


@dataclass
class DecDriver:
    name: str
    effective_date: date | None = None
    expiry_date: date | None = None


@dataclass
class DecPayment:
    label: str
    due_date: date
    amount: Decimal
    fee: Decimal = ZERO


@dataclass
class ParsedInsuranceDec:
    carrier: str = ""
    carrier_key: str = ""  # integon | nyaip | maya | progressive | generic
    policy_number: str = ""
    named_insured: str = ""
    insured_address: str = ""
    effective_date: date | None = None
    expiration_date: date | None = None
    premium: Decimal | None = None
    down_payment: Decimal | None = None
    vehicles: list[DecVehicle] = field(default_factory=list)
    drivers: list[DecDriver] = field(default_factory=list)
    payments: list[DecPayment] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)


def _parse_money(raw: str | None) -> Decimal:
    if not raw:
        return ZERO
    try:
        return Decimal(str(raw).replace(",", "").replace("$", "").replace("S", "").strip()).quantize(
            Decimal("0.01")
        )
    except (InvalidOperation, ValueError):
        return ZERO


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = str(raw).strip().replace("-", "/")
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _first_match(pattern: str, text: str, flags=0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def _normalize_person_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", (name or "").strip())
    if "," in cleaned and ", " not in cleaned:
        cleaned = cleaned.replace(",", ", ")
    return cleaned


def _normalize_policy_number(raw: str) -> str:
    cleaned = re.sub(r"\s+", " ", (raw or "").strip(" :#."))
    # Keep readable spacing for AIP ("CAR 5007 97 71") but trim junk tails.
    cleaned = re.sub(r"[^\w\-/\s]", "", cleaned).strip()
    return cleaned[:100]


def _year_from_short(raw: str | int | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None
    if value < 100:
        # AIP often prints model year as 2 digits ("20" → 2020).
        return 2000 + value if value < 80 else 1900 + value
    if 1900 <= value <= 2100:
        return value
    return None


def _parse_insured_address(text: str, result: ParsedInsuranceDec) -> None:
    address = _first_match(
        r"(?:Insured\s+Address|Mailing\s+Address|Garage\s+Address|Address)\s*[:\n]\s*([^\n]{8,120})",
        text,
        re.I,
    )
    if address and not re.search(r"policy|premium|effective|named insured", address, re.I):
        result.insured_address = re.sub(r"\s+", " ", address).strip(" ,")
        return
    # Named Insured block: name then following address-ish line(s)
    block = re.search(
        r"(?:Named\s+Insured|Name\s+of\s+Insured|NAMED\s+INSURED\s*&\s*ADDRESS)\s*[:\n]\s*"
        r"([^\n]+)\n\s*([A-Z0-9][^\n]{5,120})(?:\n\s*([A-Z][^\n]{5,80}))?",
        text,
        re.I,
    )
    if block:
        lines = [re.sub(r"\s+", " ", g).strip(" ,") for g in block.groups() if g]
        # Skip the name line; prefer lines with digits (street / city zip).
        for line in lines[1:]:
            if re.search(r"\d", line) and not re.search(r"policy|premium|effective", line, re.I):
                if result.insured_address:
                    result.insured_address = f"{result.insured_address}, {line}"[:500]
                else:
                    result.insured_address = line
        if not result.named_insured and lines:
            result.named_insured = lines[0]


def _parse_vehicles(text: str, result: ParsedInsuranceDec) -> None:
    for match in _VEHICLE_ROW.finditer(text):
        result.vehicles.append(
            DecVehicle(
                auto_number=int(match.group(1)),
                year=int(match.group(2)),
                make=match.group(3).title(),
                vin=match.group(4).upper(),
            )
        )
    if result.vehicles:
        return

    for index, match in enumerate(_MAYA_VEHICLE_ROW.finditer(text), start=1):
        make_model = f"{match.group(2).strip()} {match.group(3).strip()}".strip()
        result.vehicles.append(
            DecVehicle(
                auto_number=index,
                year=int(match.group(1)),
                make=make_model.title()[:60],
                vin=match.group(4).upper(),
            )
        )
    if result.vehicles:
        return

    for match in _AIP_VEHICLE_ROW.finditer(text):
        auto_no = int(match.group(1))
        year = _year_from_short(match.group(2))
        make = re.sub(r"\s+", " ", match.group(3)).strip().title()
        # Find the next VIN after this row.
        tail = text[match.end() : match.end() + 400]
        vin_match = _VIN.search(tail)
        vin = vin_match.group(1).upper() if vin_match else ""
        result.vehicles.append(
            DecVehicle(auto_number=auto_no, year=year, make=make, vin=vin)
        )
    if result.vehicles:
        return

    for index, match in enumerate(_SINGLE_CAR_VEHICLE_ROW.finditer(text), start=1):
        result.vehicles.append(
            DecVehicle(
                auto_number=index,
                year=int(match.group(2)),
                make=match.group(1).title(),
                vin=match.group(4).upper(),
                plate=(match.group(5) or "").strip().upper(),
            )
        )
    if result.vehicles:
        return

    seen: set[str] = set()
    for index, match in enumerate(_LOOSE_VEHICLE_ROW.finditer(text), start=1):
        vin = (match.group(4) or "").upper()
        if not vin or vin in seen:
            continue
        seen.add(vin)
        year_raw = match.group(2)
        make = (match.group(3) or "").strip()
        auto_no = int(match.group(1)) if match.group(1) else index
        result.vehicles.append(
            DecVehicle(
                auto_number=auto_no,
                year=int(year_raw) if year_raw else None,
                make=make.title() if make else "",
                vin=vin,
            )
        )
    if result.vehicles:
        return

    # Last resort: bare VIN tokens
    for index, match in enumerate(_VIN.finditer(text), start=1):
        vin = match.group(1).upper()
        if vin in seen:
            continue
        seen.add(vin)
        result.vehicles.append(DecVehicle(auto_number=index, vin=vin))


def _parse_drivers(text: str, result: ParsedInsuranceDec) -> None:
    for match in _DRIVER_ROW.finditer(text):
        name = _normalize_person_name(match.group(1))
        result.drivers.append(
            DecDriver(
                name=name,
                effective_date=_parse_date(match.group(2)),
                expiry_date=_parse_date(match.group(3)),
            )
        )
    if result.drivers:
        return

    for match in _SINGLE_CAR_DRIVER_ROW.finditer(text):
        name = re.sub(r"\s+", " ", match.group(2)).strip(" .")
        if len(name) < 3:
            continue
        result.drivers.append(
            DecDriver(
                name=name.title(),
                effective_date=result.effective_date,
                expiry_date=result.expiration_date,
            )
        )
    if result.drivers:
        return

    # AIP: "DRIVER NAME" then "1) FATEH ZINDANI"
    aip_block = re.search(r"(?is)DRIVER\s+NAME\s*(.*?)(?:ENDORSEMENTS:|DISCOUNTS:|PREMIUM\s+FINANCE|$)", text)
    scan = aip_block.group(1) if aip_block else text
    for match in _AIP_DRIVER_ROW.finditer(scan):
        name = re.sub(r"\s+", " ", match.group(2)).strip(" .")
        if len(name) < 3 or re.search(r"LICENSE|BIRTH|ENDORSEMENT", name, re.I):
            continue
        result.drivers.append(
            DecDriver(
                name=name.title(),
                effective_date=result.effective_date,
                expiry_date=result.expiration_date,
            )
        )
    if result.drivers:
        return

    maya_block = _MAYA_DRIVER_BLOCK.search(text)
    if maya_block:
        for line in maya_block.group(1).splitlines():
            cleaned = re.sub(r"^\s*\d+\s*", "", line).strip()
            if not cleaned or len(cleaned) < 3:
                continue
            if not re.match(r"^[A-Z][A-Z'\-]+,\s*[A-Z]", cleaned):
                continue
            result.drivers.append(
                DecDriver(
                    name=_normalize_person_name(cleaned).title(),
                    effective_date=result.effective_date,
                    expiry_date=result.expiration_date,
                )
            )
        if result.drivers:
            return

    seen: set[str] = set()
    for match in _LABELED_DRIVER.finditer(text):
        name = _normalize_person_name(match.group(1)).title()
        key = name.casefold()
        if len(name) < 3 or key in seen:
            continue
        seen.add(key)
        result.drivers.append(
            DecDriver(
                name=name,
                effective_date=result.effective_date,
                expiry_date=result.expiration_date,
            )
        )


def _parse_policy_period(text: str, result: ParsedInsuranceDec) -> None:
    period = re.search(
        r"(?is)(?:Policy\s+Period|Policy\s+Term|Standard\s+Time|POLICY\s+PERIOD)"
        r"(?:\s*Begins\s+and\s+Ends[^\n]*\n[^\n]*?)?"
        r"[\s:]*"
        r"(?:FROM[\s:]*)?"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:TO|THROUGH|–|-)\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        text,
    )
    if period:
        result.effective_date = result.effective_date or _parse_date(period.group(1))
        result.expiration_date = result.expiration_date or _parse_date(period.group(2))


def _looks_like_policy_number(raw: str) -> bool:
    cleaned = _normalize_policy_number(raw)
    if len(cleaned) < 5:
        return False
    if re.search(r"[A-Za-z]{4,}\s+[A-Za-z]{4,}", cleaned):
        # Reject phrases like "BUSINESS AUTO DECLARATIONS"
        return False
    return bool(re.search(r"[0-9]", cleaned))


def _parse_common_fields(text: str, result: ParsedInsuranceDec) -> None:
    policy_raw = (
        _first_match(
            r"(?:Policy\s*(?:Number|No\.?#?|#)|POL(?:ICY)?\s*(?:NO\.?|#))\s*[:#]?\s*"
            r"([A-Z0-9][A-Z0-9\-/ ]{4,})",
            text,
            re.I,
        )
        or _first_match(
            r"POLICY\s+NUMBER\s*(?:\n\s*[A-Z][A-Z ]{0,40})?\n\s*([A-Z0-9][A-Z0-9\-/]{4,})",
            text,
            re.I,
        )
    )
    if not policy_raw:
        alt = re.search(r"POLICY[^\n]{0,40}?([A-Z0-9]{6,}[A-Z0-9\-/ ]*)", text, re.I)
        if alt and _looks_like_policy_number(alt.group(1)):
            policy_raw = alt.group(1)
    if policy_raw and _looks_like_policy_number(policy_raw):
        result.policy_number = _normalize_policy_number(policy_raw)

    insured = _first_match(
        r"(?:Named\s+Insured|Insured(?:'s)?\s+Name|Name\s+of\s+Insured|NAMED\s+INSURED\s*&\s*ADDRESS)"
        r"\s*[:\n]\s*([A-Z0-9][^\n]{2,80})",
        text,
        re.I,
    )
    if insured:
        result.named_insured = re.sub(r"\s+", " ", insured).strip(" ,")
    _parse_insured_address(text, result)

    eff = (
        _first_match(r"(?:Effective|Eff\.?)\s*Date(?:\s+of\s+Change)?\s*[:#]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.I)
        or _first_match(r"Policy\s+Period\s*[:#]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.I)
    )
    exp = (
        _first_match(r"(?:Expiration|Expiry|Exp\.?)\s*Date\s*[:#]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.I)
        or _first_match(
            r"Policy\s+Period\s*[:#]?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*(?:to|through|-|–)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            text,
            re.I,
        )
    )
    result.effective_date = _parse_date(eff)
    result.expiration_date = _parse_date(exp)
    _parse_policy_period(text, result)

    premium_raw = (
        _first_match(r"TOTAL\s+FULL\s+TERM\s+PREMIUM\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"ESTIMATED\s+TOTAL\s+ANNUAL\s+PREMIUM[^\n]*\n?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"(?:Total\s+(?:Written\s+)?Premium|Written\s+Premium)\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"Annual\s+Premium\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"Total\s+Amount\s+Due\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"Total\s+Premium\s+Per\s+Auto\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
    )
    if premium_raw:
        result.premium = _parse_money(premium_raw)

    down_raw = (
        _first_match(r"Down\s*Payment\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"Deposit\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"Minimum\s+Earned\s+Premium\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
    )
    if down_raw:
        result.down_payment = _parse_money(down_raw)

    for match in _PAYMENT_ROW.finditer(text):
        due = _parse_date(match.group(2))
        if not due:
            continue
        result.payments.append(
            DecPayment(
                label=re.sub(r"\s+", " ", match.group(1)).strip(),
                due_date=due,
                amount=_parse_money(match.group(3)),
            )
        )

    _parse_vehicles(text, result)
    _parse_drivers(text, result)
    if not result.vehicles:
        result.parse_warnings.append("No vehicles detected on this DEC — add them after import if needed.")
    if not result.drivers:
        result.parse_warnings.append("No drivers detected on this DEC — add them after import if needed.")


def _extract_pdf_text(upload: BinaryIO) -> str:
    try:
        reader = PdfReader(upload)
    except (PdfReadError, PdfStreamError, TypeError, ValueError) as exc:
        raise DecPageParseError(f"Could not read PDF: {exc}") from exc
    chunks: list[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(chunks).strip()
    if not text:
        raise DecPageParseError(
            "This PDF has no readable text (likely a scanned image). "
            + _SUPPORTED_CARRIERS_MSG
        )
    return text.replace("\r\n", "\n")


def _detect_carrier(text: str) -> str:
    upper = text.upper()
    if "PROGRESSIVE" in upper:
        return "progressive"
    if "MAYA ASSURANCE" in upper:
        return "maya"
    if "INTEGON" in upper or "GMAC INSURANCE" in upper or "NATIONAL GENERAL" in upper:
        return "integon"
    if (
        "NYAIP" in upper
        or "N.Y.A.I.P" in upper
        or "NEW YORK AUTOMOBILE INSURANCE PLAN" in upper
        or "NY AUTOMOBILE INSURANCE PLAN" in upper
        or "AUTOMOBILE INSURANCE PLAN DEPARTMENT" in upper
        or ("ASSIGNED RISK" in upper and ("NEW YORK" in upper or "AIP" in upper or "NY" in upper))
        or ("21ST CENTURY" in upper and "AIP" in upper)
        or "ACCOUNT AIP" in upper
        or "ACCOUNT. AIP" in upper
    ):
        return "nyaip"
    return ""


def parse_integon_dec_text(text: str) -> ParsedInsuranceDec:
    """Parse Integon / National General style declaration text."""
    result = ParsedInsuranceDec(carrier="Integon", carrier_key="integon")
    _parse_common_fields(text, result)
    if not result.carrier or result.carrier == "Integon":
        carrier_line = _first_match(r"((?:Integon|National General)[^\n]{0,60})", text, re.I)
        if carrier_line:
            result.carrier = re.sub(r"\s+", " ", carrier_line).strip(" ,")
    if not result.policy_number:
        raise DecPageParseError("Could not find a policy number on this Integon declaration page.")
    if not result.effective_date or not result.expiration_date:
        result.parse_warnings.append("Could not fully read policy period dates from Integon DEC.")
    if not result.payments:
        result.parse_warnings.append(
            "No installment schedule rows detected — you can add payments manually on the detail page later."
        )
    return result


def parse_nyaip_dec_text(text: str) -> ParsedInsuranceDec:
    """Parse NYAIP / New York Automobile Insurance Plan / 21st Century AIP declaration text."""
    result = ParsedInsuranceDec(carrier="NYAIP", carrier_key="nyaip")
    _parse_common_fields(text, result)
    insurer = _first_match(r"Insurer\s*:\s*([^\n]{4,80})", text, re.I)
    if insurer:
        result.carrier = re.sub(r"\s+", " ", insurer).strip(" ,")
    elif "NEW YORK AUTOMOBILE INSURANCE PLAN" in text.upper() or "NY AUTOMOBILE INSURANCE PLAN" in text.upper():
        result.carrier = "New York Automobile Insurance Plan (NYAIP)"
    if not result.named_insured:
        # Cover letter "RE:\nNAME"
        re_name = _first_match(r"(?im)^RE:\s*\n\s*([A-Z][A-Z\s'\-]{2,60})\s*$", text)
        if re_name:
            result.named_insured = re.sub(r"\s+", " ", re_name).strip()
    if not result.policy_number:
        raise DecPageParseError("Could not find a policy number on this NYAIP declaration page.")
    if not result.effective_date or not result.expiration_date:
        result.parse_warnings.append("Could not fully read policy period dates from NYAIP DEC.")
    if not result.payments:
        result.parse_warnings.append(
            "No installment schedule rows detected — you can add payments manually on the detail page later."
        )
    return result


def parse_maya_dec_text(text: str) -> ParsedInsuranceDec:
    """Parse Maya Assurance business-auto declarations."""
    result = ParsedInsuranceDec(carrier="Maya Assurance Company", carrier_key="maya")
    _parse_common_fields(text, result)
    maya_pol = _first_match(
        r"POLICY\s+NUMBER\s*(?:BUSINESS\s+AUTO\s+DECLARATIONS\s*)?\n?\s*([0-9A-Z][0-9A-Z\-/]{4,})",
        text,
        re.I,
    )
    if maya_pol and _looks_like_policy_number(maya_pol):
        result.policy_number = _normalize_policy_number(maya_pol)
    if not result.policy_number:
        # Bare number/code sitting under the declarations header.
        bare = re.search(
            r"BUSINESS\s+AUTO\s+DECLARATIONS\s*\n\s*([0-9A-Z][0-9A-Z\-/]{4,})",
            text,
            re.I,
        )
        if bare:
            result.policy_number = _normalize_policy_number(bare.group(1))
    if not result.named_insured:
        block = re.search(
            r"NAMED\s+INSURED\s*&\s*ADDRESS\s*\n\s*([^\n]+)\n\s*([^\n]+)\n\s*([^\n]+)",
            text,
            re.I,
        )
        if block:
            result.named_insured = re.sub(r"\s+", " ", block.group(1)).strip(" ,")
            addr = f"{block.group(2).strip()}, {block.group(3).strip()}"
            result.insured_address = re.sub(r"\s+", " ", addr)[:500]
    if not result.policy_number:
        raise DecPageParseError("Could not find a policy number on this Maya Assurance DEC.")
    if not result.effective_date or not result.expiration_date:
        result.parse_warnings.append("Could not fully read policy period dates from Maya DEC.")
    return result


def parse_progressive_dec_text(text: str) -> ParsedInsuranceDec:
    """Parse Progressive personal-auto declaration text (text-layer PDFs)."""
    result = ParsedInsuranceDec(carrier="Progressive", carrier_key="progressive")
    _parse_common_fields(text, result)
    if not result.policy_number:
        prog = _first_match(
            r"(?:Policy\s*(?:number|no\.?|#)|Progressive\s+policy)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{5,})",
            text,
            re.I,
        )
        result.policy_number = _normalize_policy_number(prog)
    if not result.policy_number:
        raise DecPageParseError(
            "Could not find a Progressive policy number. If this is a scanned DEC image, "
            "re-export it as a searchable/text PDF and try again."
        )
    if not result.effective_date or not result.expiration_date:
        result.parse_warnings.append("Could not fully read policy period dates from Progressive DEC.")
    if not result.payments:
        result.parse_warnings.append(
            "No installment schedule rows detected — you can add payments manually on the detail page later."
        )
    return result


def parse_insurance_dec_page(upload: BinaryIO) -> ParsedInsuranceDec:
    """Router: extract PDF text, detect carrier, run carrier parser."""
    text = _extract_pdf_text(upload)
    key = _detect_carrier(text)
    if key == "integon":
        return parse_integon_dec_text(text)
    if key == "nyaip":
        return parse_nyaip_dec_text(text)
    if key == "maya":
        return parse_maya_dec_text(text)
    if key == "progressive":
        return parse_progressive_dec_text(text)

    # Last-chance generic parse when policy number + period are obvious.
    generic = ParsedInsuranceDec(carrier="Unknown Carrier", carrier_key="generic")
    _parse_common_fields(text, generic)
    if generic.policy_number and generic.effective_date and generic.expiration_date:
        generic.parse_warnings.append(
            "Carrier was not recognized — fields were imported with generic heuristics. Verify details."
        )
        return generic

    raise DecPageParseError(
        "Unsupported or unreadable declaration page. " + _SUPPORTED_CARRIERS_MSG
    )


def _resolve_or_create_company(organization, carrier_name: str) -> InsuranceCompany:
    name = (carrier_name or "").strip() or "Unknown Carrier"
    existing = (
        InsuranceCompany.objects.filter(organization=organization, name__iexact=name).first()
        or InsuranceCompany.objects.filter(organization=organization, name__icontains=name[:20]).first()
    )
    if existing:
        return existing
    return InsuranceCompany.objects.create(organization=organization, name=name)


def _resolve_or_create_client(organization, named_insured: str, *, source: str = "insurance") -> Client:
    from .client_matching import resolve_client_for_display_name

    display = (named_insured or "").strip() or "Unknown Insured"
    return resolve_client_for_display_name(organization, display, source=source)


def _replace_installments(policy: InsurancePolicy, parsed: ParsedInsuranceDec) -> None:
    InsurancePolicyInstallment.objects.filter(policy=policy).delete()
    if parsed.payments:
        used_numbers: set[int] = set()
        for idx, payment in enumerate(parsed.payments):
            label = (payment.label or "").lower()
            if "deposit" in label or "down" in label:
                number = 0
            else:
                number = idx if 0 not in used_numbers and idx > 0 else idx + (1 if 0 in used_numbers else 0)
                if number == 0 and "deposit" not in label:
                    number = idx + 1
            while number in used_numbers:
                number += 1
            used_numbers.add(number)
            InsurancePolicyInstallment.objects.create(
                policy=policy,
                installment_number=number,
                due_date=payment.due_date,
                amount=payment.amount,
                installment_fee=payment.fee,
                notes=payment.label[:255],
                is_paid=False,
            )
        return

    # Synthesize a minimal schedule when only premium/down payment is known.
    if parsed.down_payment and parsed.effective_date:
        InsurancePolicyInstallment.objects.create(
            policy=policy,
            installment_number=0,
            due_date=parsed.effective_date,
            amount=parsed.down_payment,
            notes="Deposit",
            is_paid=False,
        )


@transaction.atomic
def apply_parsed_dec_to_insurance_policy(
    policy: InsurancePolicy,
    parsed: ParsedInsuranceDec,
    *,
    user=None,
    dec_file=None,
    replace_schedule: bool = True,
) -> InsurancePolicy:
    """Apply parsed DEC fields onto an existing InsurancePolicy and store the PDF."""
    update_fields = ["updated_at"]

    if parsed.policy_number:
        policy.policy_number = parsed.policy_number[:100]
        update_fields.append("policy_number")
    if parsed.named_insured:
        policy.named_insured = parsed.named_insured[:255]
        update_fields.append("named_insured")
    if parsed.insured_address:
        policy.insured_address = parsed.insured_address[:500]
        update_fields.append("insured_address")
    if parsed.effective_date:
        policy.start_date = parsed.effective_date
        update_fields.append("start_date")
    if parsed.expiration_date:
        policy.end_date = parsed.expiration_date
        policy.renewal_date = parsed.expiration_date
        update_fields.extend(["end_date", "renewal_date"])
    if parsed.premium is not None:
        policy.premium = parsed.premium
        update_fields.append("premium")

    if parsed.vehicles:
        first = parsed.vehicles[0]
        if first.vin:
            policy.vin = first.vin[:17]
            update_fields.append("vin")
        if first.plate:
            policy.plate_number = first.plate[:50]
            update_fields.append("plate_number")
    if parsed.drivers:
        policy.driver_name = parsed.drivers[0].name[:200]
        update_fields.append("driver_name")

    if parsed.carrier:
        company = _resolve_or_create_company(policy.organization, parsed.carrier)
        if policy.insurance_company_id != company.id:
            policy.insurance_company = company
            update_fields.append("insurance_company")

    policy.save(update_fields=list(dict.fromkeys(update_fields)))

    if parsed.vehicles:
        policy.policy_vehicles.all().delete()
        for vehicle in parsed.vehicles:
            InsurancePolicyVehicle.objects.create(
                policy=policy,
                auto_number=vehicle.auto_number,
                year=vehicle.year,
                make=(vehicle.make or "")[:60],
                vin=(vehicle.vin or "")[:17],
                plate_number=(vehicle.plate or "")[:50],
                effective_date=parsed.effective_date,
                expiration_date=parsed.expiration_date,
            )

    if parsed.drivers:
        policy.policy_drivers.all().delete()
        for driver in parsed.drivers:
            InsurancePolicyDriver.objects.create(
                policy=policy,
                name=driver.name[:200],
                effective_date=driver.effective_date or parsed.effective_date,
                expiry_date=driver.expiry_date or parsed.expiration_date,
            )

    if replace_schedule:
        _replace_installments(policy, parsed)

    if dec_file is not None:
        try:
            dec_file.seek(0)
        except Exception:
            pass
        InsurancePolicyDocument.objects.create(
            policy=policy,
            document_type=InsurancePolicyDocument.DocumentType.DECLARATION_PAGE,
            title=f"Declaration Page — {policy.policy_number}",
            file=dec_file,
            uploaded_by=user,
        )

    return policy


def create_policy_from_parsed_dec(
    *,
    organization,
    parsed: ParsedInsuranceDec,
    user=None,
    dec_file=None,
    commission_rate: Decimal | None = None,
) -> InsurancePolicy:
    """Create a bound insurance policy from a parsed DEC."""
    if not parsed.policy_number:
        raise DecPageParseError("Parsed DEC is missing a policy number.")
    if not parsed.effective_date or not parsed.expiration_date:
        raise DecPageParseError(
            "Parsed DEC is missing effective/expiration dates. "
            "Open the policy manually or re-upload after parser calibration."
        )

    client = _resolve_or_create_client(organization, parsed.named_insured)
    company = _resolve_or_create_company(organization, parsed.carrier or "Unknown Carrier")
    premium = parsed.premium if parsed.premium is not None else ZERO
    rate = commission_rate if commission_rate is not None else ZERO

    policy = InsurancePolicy(
        organization=organization,
        client=client,
        policy_number=parsed.policy_number[:100],
        insurance_company=company,
        premium=premium,
        broker_fee=ZERO,
        commission_rate=rate,
        stage=InsurancePolicy.StageChoices.BOUND,
        status=InsurancePolicy.StatusChoices.ACTIVE,
        business_type=InsurancePolicy.BusinessTypeChoices.NEW_BUSINESS,
        bound_date=parsed.effective_date,
        start_date=parsed.effective_date,
        end_date=parsed.expiration_date,
        renewal_date=parsed.expiration_date,
        named_insured=(parsed.named_insured or "")[:255],
        insured_address=(parsed.insured_address or "")[:500],
        added_by=user,
    )
    policy.save()
    apply_parsed_dec_to_insurance_policy(
        policy,
        parsed,
        user=user,
        dec_file=dec_file,
        replace_schedule=True,
    )
    return policy
