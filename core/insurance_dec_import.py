"""Parse Integon / NYAIP declaration page PDFs and apply data to insurance policies."""

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
_PAYMENT_ROW = re.compile(
    r"(?im)^\s*(DEPOSIT|DOWN\s*PAYMENT|INSTALLMENT\s*#?\s*\d+|Bill\s*#\s*\d+|PMT\s*#?\s*\d+|"
    r"Payment\s*\d+)\s+"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+"
    r"\$?\s*([\d,]+\.\d{2})",
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
    carrier_key: str = ""  # integon | nyaip
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
        return Decimal(str(raw).replace(",", "").replace("$", "").strip()).quantize(Decimal("0.01"))
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


def _parse_insured_address(text: str, result: ParsedInsuranceDec) -> None:
    address = _first_match(
        r"(?:Insured\s+Address|Mailing\s+Address|Garage\s+Address|Address)\s*[:\n]\s*([^\n]{8,120})",
        text,
        re.I,
    )
    if address and not re.search(r"policy|premium|effective|named insured", address, re.I):
        result.insured_address = re.sub(r"\s+", " ", address).strip(" ,")
        return
    # Named Insured block: name then following address-ish line
    block = re.search(
        r"(?:Named\s+Insured|Name\s+of\s+Insured)\s*[:\n]\s*[^\n]+\n\s*([A-Z0-9][^\n]{8,120})",
        text,
        re.I,
    )
    if block:
        line = re.sub(r"\s+", " ", block.group(1)).strip(" ,")
        if re.search(r"\d", line) and not re.search(r"policy|premium|effective", line, re.I):
            result.insured_address = line


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


def _parse_common_fields(text: str, result: ParsedInsuranceDec) -> None:
    result.policy_number = _first_match(
        r"(?:Policy\s*(?:Number|No\.?#?|#)|POL(?:ICY)?\s*(?:NO\.?|#))\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{4,})",
        text,
        re.I,
    )
    if not result.policy_number:
        # Fallback: long alphanumeric token near "POLICY"
        alt = re.search(r"POLICY[^\n]{0,40}?([A-Z0-9]{6,}[A-Z0-9\-/]*)", text, re.I)
        if alt:
            result.policy_number = alt.group(1).strip()

    insured = _first_match(
        r"(?:Named\s+Insured|Insured(?:'s)?\s+Name|Name\s+of\s+Insured)\s*[:\n]\s*([A-Z0-9][^\n]{2,80})",
        text,
        re.I,
    )
    result.named_insured = re.sub(r"\s+", " ", insured).strip(" ,")
    _parse_insured_address(text, result)

    eff = (
        _first_match(r"(?:Effective|Eff\.?)\s*Date\s*[:#]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.I)
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

    premium_raw = (
        _first_match(r"(?:Total\s+)?(?:Written\s+)?Premium\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"Annual\s+Premium\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"Total\s+Amount\s+Due\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
    )
    if premium_raw:
        result.premium = _parse_money(premium_raw)

    down_raw = (
        _first_match(r"Down\s*Payment\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
        or _first_match(r"Deposit\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})", text, re.I)
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
            "This PDF has no readable text. Scanned declaration pages are not supported — "
            "upload a text-based Integon or NYAIP DEC PDF."
        )
    return text.replace("\r\n", "\n")


def _detect_carrier(text: str) -> str:
    upper = text.upper()
    if "INTEGON" in upper or "GMAC INSURANCE" in upper:
        return "integon"
    if (
        "NYAIP" in upper
        or "N.Y.A.I.P" in upper
        or "NEW YORK AUTOMOBILE INSURANCE PLAN" in upper
        or "NY AUTOMOBILE INSURANCE PLAN" in upper
        or ("ASSIGNED RISK" in upper and "NEW YORK" in upper)
    ):
        return "nyaip"
    return ""


def parse_integon_dec_text(text: str) -> ParsedInsuranceDec:
    """Parse Integon / National General style declaration text."""
    result = ParsedInsuranceDec(carrier="Integon", carrier_key="integon")
    _parse_common_fields(text, result)
    if not result.carrier or result.carrier == "Integon":
        carrier_line = _first_match(r"(Integon[^\n]{0,60})", text, re.I)
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
    """Parse NYAIP / New York Automobile Insurance Plan declaration text."""
    result = ParsedInsuranceDec(carrier="NYAIP", carrier_key="nyaip")
    _parse_common_fields(text, result)
    if "NEW YORK AUTOMOBILE INSURANCE PLAN" in text.upper():
        result.carrier = "New York Automobile Insurance Plan (NYAIP)"
    if not result.policy_number:
        raise DecPageParseError("Could not find a policy number on this NYAIP declaration page.")
    if not result.effective_date or not result.expiration_date:
        result.parse_warnings.append("Could not fully read policy period dates from NYAIP DEC.")
    if not result.payments:
        result.parse_warnings.append(
            "No installment schedule rows detected — you can add payments manually on the detail page later."
        )
    return result


def parse_insurance_dec_page(upload: BinaryIO) -> ParsedInsuranceDec:
    """Router: extract PDF text, detect Integon/NYAIP, run carrier parser."""
    text = _extract_pdf_text(upload)
    key = _detect_carrier(text)
    if key == "integon":
        return parse_integon_dec_text(text)
    if key == "nyaip":
        return parse_nyaip_dec_text(text)
    raise DecPageParseError(
        "Unsupported declaration page. Currently supported carriers: Integon and NYAIP "
        "(New York Automobile Insurance Plan). Upload a text-based PDF from one of those carriers."
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
