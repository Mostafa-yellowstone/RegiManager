"""Parse TLC declaration page PDFs and apply extracted data to policies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import BinaryIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from .tlc_commissions import apply_commission_rule_to_policy
from .tlc_models import (
    TLCPolicy,
    TLCPolicyDocument,
    TLCPolicyDriver,
    TLCPolicyVehicle,
    TLCPolicyTimelineEvent,
    TLCPremiumBreakdown,
    TLCInstallment,
)

ZERO = Decimal("0.00")
DEFAULT_INSTALLMENT_FEE = Decimal("5.00")
_CITY_STATE_ZIP = re.compile(r"^[A-Z0-9 .'-]+[A-Z]{2}\s+\d{5}(?:-\d{4})?$", re.I)
_DATE_MDY = re.compile(r"(\d{2}/\d{2}/\d{4})")
_MONEY = re.compile(r"\$?\s*([\d,]+\.\d{2})")
_VIN = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_VEHICLE_ROW = re.compile(
    r"^\s*(\d+)\s+(\d{4})\s+([A-Z][A-Z0-9-]*)\s+([A-HJ-NPR-Z0-9]{17})\s",
    re.M,
)
_DRIVER_ROW = re.compile(
    r"^([A-Z][A-Z'-]+,[A-Z][A-Z\s'-]+?)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})",
    re.M,
)
_PAYMENT_ROW = re.compile(
    r"^(DEPOSIT|Bill\s*#\s*\d+)\s+(\d{2}/\d{2}/\d{4})\s+\$?\s*([\d,]+\.\d{2})",
    re.M | re.I,
)


@dataclass
class DecVehicle:
    auto_number: int
    year: int
    make: str
    vin: str


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


@dataclass
class ParsedDecPage:
    carrier: str = ""
    policy_number: str = ""
    issue_date: date | None = None
    effective_date: date | None = None
    expiration_date: date | None = None
    named_insured: str = ""
    insured_address: str = ""
    form_of_business: str = ""
    broker_name: str = ""
    broker_address: str = ""
    annual_premium: Decimal = ZERO
    amended_total: Decimal = ZERO
    down_payment: Decimal = ZERO
    deposit_amount: Decimal = ZERO
    reinstatement_fee: Decimal = ZERO
    vehicles: list[DecVehicle] = field(default_factory=list)
    drivers: list[DecDriver] = field(default_factory=list)
    payments: list[DecPayment] = field(default_factory=list)
    installment_fee: Decimal = ZERO
    carrier_code: str = ""
    parse_warnings: list[str] = field(default_factory=list)


class DecPageParseError(Exception):
    """Raised when a declaration page cannot be parsed."""


def extract_pdf_text(file_obj: BinaryIO) -> str:
    try:
        reader = PdfReader(file_obj)
    except (PdfReadError, PdfStreamError) as exc:
        raise DecPageParseError("Could not read this PDF file. Upload a valid digital declaration page.") from exc
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_money(value: str | None) -> Decimal:
    if not value:
        return ZERO
    cleaned = value.replace(",", "").replace("$", "").strip()
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return ZERO


def _first_match(pattern: str, text: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def _parse_insured_and_broker(text: str, result: ParsedDecPage) -> None:
    header = re.search(r"NAMED INSURED AND ADDRESS", text, re.I)
    if not header:
        issued = re.search(r"Issued to:\s*(.+?)(?:\n|Policy No)", text, re.I)
        if issued:
            result.named_insured = issued.group(1).strip()
        return

    lines = [line.strip() for line in text[header.end() :].splitlines() if line.strip()]
    if lines and "PRODUCER" in lines[0].upper():
        lines = lines[1:]

    insured_lines: list[str] = []
    broker_lines: list[str] = []
    phase = "insured"
    for line in lines:
        upper = line.upper()
        if phase == "broker" and (
            upper.startswith("ANNUAL PREMIUM")
            or upper.startswith("SCHEDULE")
            or upper.startswith("COVERAGES")
            or upper.startswith("BODILY INJURY")
            or upper.startswith("DOWN PAYMENT")
        ):
            break
        if phase == "insured" and _CITY_STATE_ZIP.match(line):
            insured_lines.append(line)
            phase = "broker"
            continue
        if phase == "insured":
            insured_lines.append(line)
            continue
        broker_lines.append(line)

    if insured_lines:
        result.named_insured = insured_lines[0]
        if len(insured_lines) > 1:
            result.insured_address = ", ".join(insured_lines[1:])
    if broker_lines:
        name_parts: list[str] = []
        address_parts: list[str] = []
        for line in broker_lines:
            if _CITY_STATE_ZIP.match(line) or re.match(r"^\d", line):
                address_parts.append(line)
            elif not address_parts:
                name_parts.append(line)
            else:
                address_parts.append(line)
        result.broker_name = " ".join(name_parts).strip()
        result.broker_address = ", ".join(address_parts).strip()

    if not result.broker_name:
        broker = re.search(
            r"Broker:\s*(.+?)\n(.+?)\n(.+?)(?:\nDescription|\nDEPOSIT|\nASTORIANY)",
            text,
            re.I | re.S,
        )
        if broker:
            result.broker_name = broker.group(1).strip()
            result.broker_address = ", ".join(
                part.strip() for part in (broker.group(2), broker.group(3)) if part.strip()
            )


def parse_american_transit_dec_text(text: str) -> ParsedDecPage:
    """Parse American Transit multicar NY declaration page text."""
    result = ParsedDecPage()
    normalized = text.replace("\r\n", "\n")

    carrier_line = ""
    for line in normalized.splitlines():
        stripped = line.strip()
        if "INSURANCE COMPANY" in stripped.upper():
            carrier_line = stripped
            break
    carrier_match = re.match(r"^(.+?)\s*(?:\((\d+)\))?\s*$", carrier_line) if carrier_line else None
    if carrier_match:
        result.carrier = carrier_match.group(1).strip()
        result.carrier_code = carrier_match.group(2) or ""

    result.policy_number = _first_match(r"Policy Number\s+(\S+)", normalized) or _first_match(
        r"Policy No[.:]\s*(\S+)", normalized
    )
    result.issue_date = _parse_date(_first_match(r"Issue Date\s*:\s*(\d{2}/\d{2}/\d{4})", normalized))

    period = re.search(
        r"POLICY PERIOD Effective\s+(\d{2}/\d{2}/\d{4}).*?Expires\s*:\s*(\d{2}/\d{2}/\d{4})",
        normalized,
        re.I | re.S,
    )
    if period:
        result.effective_date = _parse_date(period.group(1))
        result.expiration_date = _parse_date(period.group(2))
    else:
        alt = re.search(
            r"Effective\s*:(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
            normalized,
            re.I,
        )
        if alt:
            result.effective_date = _parse_date(alt.group(1))
            result.expiration_date = _parse_date(alt.group(2))

    result.form_of_business = _first_match(
        r"Form Of Business\s+(.+?)(?:\n|Policy Number)", normalized, re.I | re.S
    ).split("\n", 1)[0].strip()

    _parse_insured_and_broker(normalized, result)

    if not result.broker_name:
        broker = re.search(
            r"Broker:\s*(.+?)\n(.+?)\n(.+?)(?:\nDescription|\nDEPOSIT)",
            normalized,
            re.I | re.S,
        )
        if broker:
            result.broker_name = broker.group(1).strip()
            result.broker_address = ", ".join(
                part.strip() for part in (broker.group(2), broker.group(3)) if part.strip()
            )

    annual = re.search(r"Annual Premium\s+\$?\s*([\d,]+\.\d{2})", normalized, re.I)
    if annual:
        result.annual_premium = _parse_money(annual.group(1))

    amended = re.search(
        r"DOWN PAYMENT\s*\n\$?\s*[\d,]+\.\d{2}\s*\n\$?\s*([\d,]+\.\d{2})",
        normalized,
        re.I,
    )
    if not amended:
        amended = re.search(r"\$?\s*([\d,]+\.\d{2})\s*\n\*\*AMENDED TOTAL", normalized, re.I)
    if amended:
        result.amended_total = _parse_money(amended.group(1))

    down = re.search(r"DOWN PAYMENT\s*\n\$?\s*([\d,]+\.\d{2})", normalized, re.I)
    if down:
        result.down_payment = _parse_money(down.group(1))

    reinstate = re.search(
        r"\$\s*([\d,]+\.\d{2})\s+Reinstatement Fee",
        normalized,
        re.I,
    )
    if reinstate:
        result.reinstatement_fee = _parse_money(reinstate.group(1))

    for match in _VEHICLE_ROW.finditer(normalized):
        result.vehicles.append(
            DecVehicle(
                auto_number=int(match.group(1)),
                year=int(match.group(2)),
                make=match.group(3).title(),
                vin=match.group(4),
            )
        )

    for match in _DRIVER_ROW.finditer(normalized):
        name = match.group(1).replace(",", ", ").strip()
        result.drivers.append(
            DecDriver(
                name=name,
                effective_date=_parse_date(match.group(2)),
                expiry_date=_parse_date(match.group(3)),
            )
        )

    for match in _PAYMENT_ROW.finditer(normalized):
        due = _parse_date(match.group(2))
        amount = _parse_money(match.group(3))
        if due and amount > ZERO:
            label = re.sub(r"\s+", " ", match.group(1)).strip().upper()
            result.payments.append(DecPayment(label=label, due_date=due, amount=amount))

    if result.payments:
        deposit = next((p for p in result.payments if p.label == "DEPOSIT"), None)
        if deposit:
            result.deposit_amount = deposit.amount

    if not result.policy_number:
        raise DecPageParseError("Could not find a policy number on this declaration page.")

    if not result.named_insured and not result.vehicles:
        raise DecPageParseError(
            "Could not extract insured or vehicle data — this may not be a supported dec page format."
        )

    if not result.amended_total and result.annual_premium:
        result.amended_total = result.annual_premium
        result.parse_warnings.append("Amended total not found; using annual premium.")

    return result


def parse_tlc_dec_page(file_obj: BinaryIO) -> ParsedDecPage:
    """Extract and parse a TLC declaration page PDF."""
    file_obj.seek(0)
    text = extract_pdf_text(file_obj)
    if not text.strip():
        raise DecPageParseError("This PDF has no readable text. Try a digital copy, not a scan.")
    upper = text.upper()
    if "AMERICAN TRANSIT" in upper or "ATIC" in upper:
        return parse_american_transit_dec_text(text)
    if _first_match(r"Policy Number\s+(\S+)", text) or _first_match(r"Policy No[.:]\s*(\S+)", text):
        result = parse_american_transit_dec_text(text)
        result.parse_warnings.append("Carrier not recognized; used American Transit parser.")
        return result
    raise DecPageParseError(
        "Unsupported declaration page format. Currently supported: American Transit (ATIC)."
    )


def _resolve_installment_fee(policy: TLCPolicy, parsed: ParsedDecPage) -> Decimal:
    if parsed.installment_fee and parsed.installment_fee > ZERO:
        return parsed.installment_fee
    from .tlc_models import TLCFinanceCompany

    org_default = (
        TLCFinanceCompany.objects.filter(
            organization=policy.organization,
            is_active=True,
            default_installment_fee__gt=ZERO,
        )
        .order_by("-default_installment_fee")
        .values_list("default_installment_fee", flat=True)
        .first()
    )
    if org_default:
        return Decimal(org_default).quantize(Decimal("0.01"))
    return DEFAULT_INSTALLMENT_FEE


def apply_dec_payment_schedule(
    policy: TLCPolicy,
    payments: list[DecPayment],
    *,
    installment_fee: Decimal = ZERO,
    replace_existing: bool = True,
) -> int:
    if replace_existing:
        policy.installments.all().delete()
    created = 0
    for number, payment in enumerate(payments, start=1):
        per_fee = ZERO if payment.label == "DEPOSIT" else installment_fee
        TLCInstallment.objects.create(
            policy=policy,
            installment_number=number,
            due_date=payment.due_date,
            amount=payment.amount,
            installment_fee=per_fee,
            balance=(payment.amount + per_fee).quantize(Decimal("0.01")),
            notes=payment.label,
        )
        created += 1
    return created


def apply_parsed_dec_to_policy(
    policy: TLCPolicy,
    parsed: ParsedDecPage,
    *,
    user=None,
    dec_file=None,
    replace_schedule: bool = True,
) -> TLCPolicy:
    """Apply parsed declaration data onto a TLC policy record."""
    is_llc = any(
        token in parsed.named_insured.upper()
        for token in (" LLC", " INC", " CORP", " LTD", " CO.")
    )

    policy.carrier = parsed.carrier or policy.carrier
    policy.issue_date = parsed.issue_date or policy.issue_date
    policy.effective_date = parsed.effective_date or policy.effective_date
    policy.expiration_date = parsed.expiration_date or policy.expiration_date
    policy.renewal_date = parsed.expiration_date or policy.renewal_date
    policy.form_of_business = parsed.form_of_business or policy.form_of_business
    policy.insured_address = parsed.insured_address or policy.insured_address
    policy.broker_name = parsed.broker_name or policy.broker_name
    policy.named_insured = parsed.named_insured or policy.named_insured
    if is_llc:
        policy.business_name = parsed.named_insured
    if parsed.vehicles:
        policy.vin = parsed.vehicles[0].vin
    if parsed.drivers:
        policy.driver_name = parsed.drivers[0].name

    written = parsed.amended_total or parsed.annual_premium
    bills = [p for p in parsed.payments if p.label != "DEPOSIT"]
    deposit = parsed.deposit_amount or parsed.down_payment

    breakdown, _created = TLCPremiumBreakdown.objects.get_or_create(policy=policy)
    breakdown.total_written_premium = written or breakdown.total_written_premium
    breakdown.down_payment = deposit or breakdown.down_payment
    if bills:
        breakdown.number_of_installments = len(bills)
        breakdown.monthly_installment = bills[0].amount
    breakdown.reinstatement_fee = parsed.reinstatement_fee or breakdown.reinstatement_fee
    per_installment_fee = _resolve_installment_fee(policy, parsed)
    breakdown.installment_fee = per_installment_fee
    if per_installment_fee > ZERO and not parsed.installment_fee:
        parsed.parse_warnings.append(
            f"Applied ${per_installment_fee} installment fee per monthly bill "
            f"(not itemized on dec page)."
        )
    if written and deposit and bills:
        breakdown.amount_financed = (written - deposit).quantize(Decimal("0.01"))
    breakdown.save()

    if not policy.commission_rate:
        apply_commission_rule_to_policy(policy, save=False)
    policy.save()

    policy.policy_vehicles.all().delete()
    for vehicle in parsed.vehicles:
        TLCPolicyVehicle.objects.create(
            policy=policy,
            auto_number=vehicle.auto_number,
            year=vehicle.year,
            make=vehicle.make,
            vin=vehicle.vin,
            effective_date=parsed.effective_date,
            expiration_date=parsed.expiration_date,
        )

    policy.policy_drivers.all().delete()
    for driver in parsed.drivers:
        TLCPolicyDriver.objects.create(
            policy=policy,
            name=driver.name,
            effective_date=driver.effective_date,
            expiry_date=driver.expiry_date,
        )

    if parsed.payments and replace_schedule:
        apply_dec_payment_schedule(
            policy,
            parsed.payments,
            installment_fee=per_installment_fee,
            replace_existing=True,
        )
    elif bills and replace_schedule:
        from .tlc_schedule import generate_installment_schedule

        generate_installment_schedule(policy, replace_existing=True)

    if dec_file is not None:
        TLCPolicyDocument.objects.create(
            policy=policy,
            document_type=TLCPolicyDocument.DocumentType.DECLARATION_PAGE,
            title=f"Declaration Page — {policy.policy_number}",
            file=dec_file,
            uploaded_by=user,
        )

    TLCPolicyTimelineEvent.objects.create(
        policy=policy,
        event_type=TLCPolicyTimelineEvent.EventType.ISSUED,
        event_date=parsed.issue_date or parsed.effective_date,
        title="Imported from declaration page",
        description=(
            f"Carrier: {parsed.carrier or '—'}; "
            f"{len(parsed.vehicles)} vehicle(s), {len(parsed.drivers)} driver(s), "
            f"{len(parsed.payments)} scheduled payment(s)."
        ),
        created_by=user,
    )
    return policy
