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
from .tlc_installments import build_installment_row
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
_CITY_STATE_ZIP = re.compile(
    r"^[A-Z0-9 .'#-]+(?:,\s*(?:[A-Z]{2}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))\s+\d{5}(?:-\d{4})?$",
    re.I,
)
_DATE_MDY = re.compile(r"(\d{2}/\d{2}/\d{4})")
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
_DRIVER_ROW = re.compile(
    r"^([A-Z][A-Z'-]+,[A-Z][A-Z\s'-]+?)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})",
    re.M,
)
_SINGLE_CAR_DRIVER_ROW = re.compile(
    r"DRIVER\s+(\d+)\.\s+([A-Z][A-Z\s'-]+?)(?=\s+DRIVER\s+\d+\.|\s*$)",
    re.M,
)
_PAYMENT_ROW = re.compile(
    r"^(DEPOSIT|Bill\s*#\s*\d+)\s+(\d{2}/\d{2}/\d{4})\s+\$?\s*([\d,]+\.\d{2})",
    re.M | re.I,
)
_MAYA_VEHICLE_ROW = re.compile(
    r"(\d+)\s+(\d{4}),\s*([A-Z]+),\s*([A-Z0-9\s]+?),\s*([A-HJ-NPR-Z0-9]{17})",
    re.I,
)
_MAYA_DRIVER_ROW = re.compile(
    r"(?m)^\s*(\d+)\s*\n\s*([A-Z][A-Z'-]+,\s*[A-Z][A-Z\s'-]+)\s*$",
)
_MAYA_PAYMENT_ROW = re.compile(
    r"(DEPOSIT|INSTALLMENT-\d+)\s+"
    r"(\d{2}/\d{2}/\d{4})\s+"
    r"\$?\s*([\d,]+\.\d{2})\s+"
    r"\$?\s*([\d,]+\.\d{2})\s+"
    r"\$?\s*([\d,]+\.\d{2})",
    re.M | re.I,
)
_HIC_PAYMENT_ROW = re.compile(
    r"^(Deposit|\d+)\s+"
    r"(\d{2}/\d{2}/\d{4})\s+"
    r"\$?\s*([\d,]+\.\d{2})\s+"
    r"\$?\s*([\d,]+\.\d{2})\s+"
    r"\$?\s*([\d,]+\.\d{2})\s+"
    r"\$?\s*([\d,]+\.\d{2})\s*$",
    re.M | re.I,
)
_INSURED_BROKER_STOP_MARKERS = (
    "POLICY PERIOD",
    "GARAGE ADDRESS",
    "CAR MODEL YEAR",
    "PREMIUMS(",
    "SCHEDULE #",
    "REGISTERED OWNED",
    "COVERAGES SYMBOL",
    "BODILY INJURY",
    "DOWN PAYMENT",
    "EFFECTIVE DATE PR/SR",
    "ANNUAL PREMIUM",
    "FORM OF BUSINESS",
    "DRIVER 1.",
    "DRIVER 1 ",
)


@dataclass
class DecVehicle:
    auto_number: int
    year: int
    make: str
    vin: str
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
    monthly_installment: Decimal = ZERO
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


def _parse_policy_number(text: str) -> str:
    return (
        _first_match(r"Policy Number:\s*(\S+)", text, re.I)
        or _first_match(r"Policy Number\s+(\S+)", text, re.I)
        or _first_match(r"Policy No\s*:\s*(\S+)", text, re.I)
        or _first_match(r"(\S+?)POLICY NO\.?", text, re.I)
    )


def _is_insured_broker_stop(line: str) -> bool:
    upper = line.upper()
    return any(upper.startswith(marker) or marker in upper for marker in _INSURED_BROKER_STOP_MARKERS)


def _normalize_person_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    if "," in cleaned and ", " not in cleaned:
        cleaned = cleaned.replace(",", ", ")
    return cleaned


def _is_header_junk_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped in {"(", ")"}:
        return True
    compact = stripped.strip("() ").upper()
    if not compact:
        return True
    return compact.startswith("PRODUCER") and "ADDRESS" in compact


def _parse_insured_and_broker(text: str, result: ParsedDecPage) -> None:
    header = re.search(r"NAMED INSURED AND ADDRESS", text, re.I)
    if not header:
        issued = re.search(r"Issued to:\s*(.+?)(?:\n|Policy No)", text, re.I)
        if issued:
            result.named_insured = _normalize_person_name(issued.group(1))
        return

    lines = [
        line.strip()
        for line in text[header.end() :].splitlines()
        if line.strip() and not _is_header_junk_line(line.strip())
    ]

    insured_lines: list[str] = []
    broker_lines: list[str] = []
    phase = "insured"
    for line in lines:
        if _is_insured_broker_stop(line):
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
        result.named_insured = _normalize_person_name(insured_lines[0])
        if len(insured_lines) > 1:
            result.insured_address = ", ".join(insured_lines[1:])
    if broker_lines:
        name_parts: list[str] = []
        address_parts: list[str] = []
        for line in broker_lines:
            if _is_insured_broker_stop(line):
                break
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


def _parse_policy_period(text: str, result: ParsedDecPage) -> None:
    if result.effective_date and result.expiration_date:
        return
    period = re.search(
        r"POLICY PERIOD Effective\s*(\d{2}/\d{2}/\d{4}).*?Expires\s*:\s*(\d{2}/\d{2}/\d{4})",
        text,
        re.I | re.S,
    )
    if period:
        result.effective_date = _parse_date(period.group(1))
        result.expiration_date = _parse_date(period.group(2))
        return
    single_period = re.search(
        r"POLICY PERIOD\s+(\d{2}/\d{2}/\d{4}).*?-\s*(\d{2}/\d{2}/\d{4})",
        text,
        re.I | re.S,
    )
    if single_period:
        result.effective_date = _parse_date(single_period.group(1))
        result.expiration_date = _parse_date(single_period.group(2))
        return
    alt = re.search(
        r"Effective\s*:(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
        text,
        re.I,
    )
    if alt:
        result.effective_date = _parse_date(alt.group(1))
        result.expiration_date = _parse_date(alt.group(2))


def _parse_premium_amounts(text: str, result: ParsedDecPage) -> None:
    annual = re.search(r"Annual Premium\s+\$?\s*([\d,]+\.\d{2})", text, re.I)
    if annual:
        result.annual_premium = _parse_money(annual.group(1))

    amended_hic = re.search(
        r"Amended Premium\s+\$?\s*([\d,]+\.\d{2})\s+Premium\s+\$?\s*([\d,]+\.\d{2})",
        text,
        re.I,
    )
    if amended_hic:
        result.amended_total = _parse_money(amended_hic.group(1))
        if not result.annual_premium:
            result.annual_premium = _parse_money(amended_hic.group(2))

    amended_row = re.search(
        r"EFFECTIVE DATE.*?AMENDED ANNUAL PREMIUM\s*"
        r"(\d{2}/\d{2}/\d{4})\s+[\d.]+\s+\$?\s*([\d,]+\.\d{2})\s+\$?\s*([\d,]+\.\d{2})",
        text,
        re.I | re.S,
    )
    if amended_row:
        if not result.effective_date:
            result.effective_date = _parse_date(amended_row.group(1))
        if not result.annual_premium:
            result.annual_premium = _parse_money(amended_row.group(2))
        result.amended_total = _parse_money(amended_row.group(3))

    amended = re.search(
        r"DOWN PAYMENT\s*\n\$?\s*[\d,]+\.\d{2}\s*\n\$?\s*([\d,]+\.\d{2})",
        text,
        re.I,
    )
    if not amended:
        amended = re.search(r"\$?\s*([\d,]+\.\d{2})\s*\n\*\*AMENDED TOTAL", text, re.I)
    if amended and not result.amended_total:
        result.amended_total = _parse_money(amended.group(1))

    down_inline = re.search(
        r"DOWN PAYMENT\s+\$?\s*([\d,]+\.\d{2}).*?MONTHLY PREMIUM THEREAFTER\s+\$?\s*([\d,]+\.\d{2})",
        text,
        re.I | re.S,
    )
    if down_inline:
        result.down_payment = _parse_money(down_inline.group(1))
        result.monthly_installment = _parse_money(down_inline.group(2))
    else:
        down = re.search(r"DOWN PAYMENT\s*\n\$?\s*([\d,]+\.\d{2})", text, re.I)
        if down:
            result.down_payment = _parse_money(down.group(1))
        elif not result.down_payment:
            down_same_line = re.search(r"DOWN PAYMENT\s+\$?\s*([\d,]+\.\d{2})", text, re.I)
            if down_same_line:
                result.down_payment = _parse_money(down_same_line.group(1))


def _parse_vehicles(text: str, result: ParsedDecPage) -> None:
    for match in _VEHICLE_ROW.finditer(text):
        result.vehicles.append(
            DecVehicle(
                auto_number=int(match.group(1)),
                year=int(match.group(2)),
                make=match.group(3).title(),
                vin=match.group(4),
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
                vin=match.group(4),
                plate=(match.group(5) or "").strip(),
            )
        )


def _parse_drivers(text: str, result: ParsedDecPage) -> None:
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


def _append_synthesized_payments(result: ParsedDecPage) -> None:
    if result.payments or not result.monthly_installment:
        return
    written = result.amended_total or result.annual_premium
    down = result.down_payment
    monthly = result.monthly_installment
    if not result.effective_date or written <= ZERO or monthly <= ZERO:
        return

    from dateutil.relativedelta import relativedelta

    if down > ZERO:
        result.payments.append(DecPayment("DEPOSIT", result.effective_date, down))
        result.deposit_amount = down
    remaining = (written - down).quantize(Decimal("0.01"))
    bill_num = 1
    while remaining > ZERO and bill_num <= 24:
        due = result.effective_date + relativedelta(months=bill_num)
        amount = min(monthly, remaining)
        result.payments.append(DecPayment(f"BILL # {bill_num}", due, amount))
        remaining = (remaining - amount).quantize(Decimal("0.01"))
        bill_num += 1
    result.parse_warnings.append(
        "Built payment schedule from down payment and monthly premium shown on the dec page."
    )


def _parse_maya_form_of_business(text: str) -> str:
    for business_type in ("Individual", "Corporation", "Partnership", "Other"):
        if re.search(rf"\nX\s*\n\s*{business_type}\b", text, re.I):
            return business_type
    return ""


def _parse_maya_insured_and_broker(text: str, result: ParsedDecPage) -> None:
    insured_block = re.search(
        r"NAMED INSURED & ADDRESS\s*(.+?)\s*FORM OF NAMED INSURED",
        text,
        re.I | re.S,
    )
    if insured_block:
        lines = [line.strip() for line in insured_block.group(1).splitlines() if line.strip()]
        if lines:
            result.named_insured = _normalize_person_name(lines[0])
            if len(lines) > 1:
                result.insured_address = ", ".join(lines[1:])

    producer_block = re.search(
        r"PRODUCER\s*\n(.+?)\n\s*New",
        text,
        re.I | re.S,
    )
    if producer_block:
        lines = [line.strip() for line in producer_block.group(1).splitlines() if line.strip()]
        if lines:
            result.broker_name = lines[0]
            if len(lines) > 1:
                result.broker_address = ", ".join(lines[1:])


def _normalize_maya_payment_label(label: str) -> str:
    cleaned = label.strip().upper()
    installment = re.match(r"INSTALLMENT-(\d+)", cleaned)
    if installment:
        return f"BILL # {installment.group(1)}"
    return cleaned


def parse_maya_assurance_dec_text(text: str) -> ParsedDecPage:
    """Parse Maya Assurance NY business auto declaration page text."""
    result = ParsedDecPage()
    normalized = text.replace("\r\n", "\n")

    carrier_match = re.search(r"^(MAYA ASSURANCE COMPANY)\b", normalized, re.M | re.I)
    if carrier_match:
        result.carrier = carrier_match.group(1).strip()

    result.policy_number = (
        _first_match(r"POLICY NUMBER\s+BUSINESS AUTO DECLARATIONS\s+(\S+)", normalized, re.I)
        or _first_match(r"POLICY NUMBER\s+PAYMENT SCHEDULE\s+(\S+)", normalized, re.I)
        or _first_match(r"AUTOMOBILE LIABILITY\s+(\d+-MA\d+)", normalized, re.I)
    )

    period = re.search(
        r"POLICY PERIOD:\s*FROM\s+(\d{2}/\d{2}/\d{4})\s+TO\s+(\d{2}/\d{2}/\d{4})",
        normalized,
        re.I,
    )
    if period:
        result.effective_date = _parse_date(period.group(1))
        result.expiration_date = _parse_date(period.group(2))
    else:
        cert_period = re.search(
            r"POLICY EFFECTIVE DATE\s+POLICY EXPIRATION DATE\s+"
            r"AUTOMOBILE LIABILITY\s+\S+\s+(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})",
            normalized,
            re.I | re.S,
        )
        if cert_period:
            result.effective_date = _parse_date(cert_period.group(1))
            result.expiration_date = _parse_date(cert_period.group(2))

    result.issue_date = result.effective_date
    result.form_of_business = _parse_maya_form_of_business(normalized)
    _parse_maya_insured_and_broker(normalized, result)

    annual = re.search(r"ESTIMATED TOTAL ANNUAL PREMIUM[^\d$]*\$?\s*([\d,]+\.\d{2})", normalized, re.I)
    if annual:
        result.annual_premium = _parse_money(annual.group(1))
        result.amended_total = result.annual_premium

    reinstate = re.search(r"A \$(\d+)\s+FEE WILL BE ASSESSED", normalized, re.I)
    if reinstate:
        result.reinstatement_fee = Decimal(reinstate.group(1)).quantize(Decimal("0.01"))

    for match in _MAYA_VEHICLE_ROW.finditer(normalized):
        result.vehicles.append(
            DecVehicle(
                auto_number=int(match.group(1)),
                year=int(match.group(2)),
                make=match.group(3).title(),
                vin=match.group(5),
            )
        )

    driver_block = re.search(
        r"DRIVERS SCHEDULE\s*(.+?)\s*(?:COVERAGE-|POLICY NUMBER)",
        normalized,
        re.I | re.S,
    )
    if driver_block:
        for match in _MAYA_DRIVER_ROW.finditer(driver_block.group(1)):
            result.drivers.append(
                DecDriver(
                    name=_normalize_person_name(match.group(2)),
                    effective_date=result.effective_date,
                    expiry_date=result.expiration_date,
                )
            )

    installment_fee = ZERO
    for match in _MAYA_PAYMENT_ROW.finditer(normalized):
        due = _parse_date(match.group(2))
        premium = _parse_money(match.group(3))
        fee = _parse_money(match.group(4))
        bill_amount = _parse_money(match.group(5))
        if not due or bill_amount <= ZERO:
            continue
        label = _normalize_maya_payment_label(match.group(1))
        result.payments.append(
            DecPayment(label=label, due_date=due, amount=bill_amount, fee=fee)
        )
        if label == "DEPOSIT":
            result.deposit_amount = bill_amount
            result.down_payment = premium
        elif label.startswith("BILL #") and installment_fee <= ZERO and fee > ZERO:
            installment_fee = fee

    if installment_fee > ZERO:
        result.installment_fee = installment_fee

    bills = [payment for payment in result.payments if payment.label != "DEPOSIT"]
    if bills:
        result.monthly_installment = bills[0].amount

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


def _normalize_hic_payment_label(label: str) -> str:
    cleaned = label.strip().upper()
    if cleaned == "DEPOSIT":
        return "DEPOSIT"
    if cleaned.isdigit():
        return f"BILL # {cleaned}"
    return cleaned


def _parse_hic_payment_schedule(text: str, result: ParsedDecPage) -> None:
    installment_fee = ZERO
    for match in _HIC_PAYMENT_ROW.finditer(text):
        due = _parse_date(match.group(2))
        premium = _parse_money(match.group(3))
        fee = _parse_money(match.group(5))
        bill_amount = _parse_money(match.group(6))
        if not due or bill_amount <= ZERO:
            continue
        label = _normalize_hic_payment_label(match.group(1))
        result.payments.append(
            DecPayment(label=label, due_date=due, amount=bill_amount, fee=fee)
        )
        if label == "DEPOSIT":
            result.deposit_amount = bill_amount
            result.down_payment = premium
        elif installment_fee <= ZERO and fee > ZERO:
            installment_fee = fee

    if installment_fee > ZERO:
        result.installment_fee = installment_fee

    bills = [payment for payment in result.payments if payment.label != "DEPOSIT"]
    if bills:
        result.monthly_installment = bills[0].amount


def parse_hereford_dec_text(text: str) -> ParsedDecPage:
    """Parse Hereford Insurance (HIC) NY commercial auto declaration pages."""
    result = ParsedDecPage()
    normalized = text.replace("\r\n", "\n")

    carrier_match = re.search(r"(HEREFORD INSURANCE COMPANY)", normalized, re.I)
    if carrier_match:
        result.carrier = carrier_match.group(1).strip()

    result.policy_number = _parse_policy_number(normalized)
    _parse_policy_period(normalized, result)
    result.issue_date = result.effective_date
    _parse_insured_and_broker(normalized, result)
    _parse_premium_amounts(normalized, result)
    _parse_vehicles(normalized, result)
    _parse_drivers(normalized, result)
    _parse_hic_payment_schedule(normalized, result)

    reinstate = re.search(
        r"fee of \$(\d+)\s+per day",
        normalized,
        re.I,
    )
    if reinstate:
        result.reinstatement_fee = Decimal(reinstate.group(1)).quantize(Decimal("0.01"))

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


def parse_american_transit_dec_text(text: str) -> ParsedDecPage:
    """Parse American Transit NY declaration page text (single-car or multicar)."""
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

    result.policy_number = _parse_policy_number(normalized)
    result.issue_date = _parse_date(
        _first_match(r"Issue Date\s*:\s*(\d{2}/\d{2}/\d{4})", normalized, re.I)
        or _first_match(r"DATE OF ISSUE\s+(\d{2}/\d{2}/\d{4})", normalized, re.I)
    )

    _parse_policy_period(normalized, result)

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

    _parse_premium_amounts(normalized, result)

    reinstate = re.search(
        r"\$\s*([\d,]+\.\d{2})\s+Reinstatement Fee",
        normalized,
        re.I,
    )
    if reinstate:
        result.reinstatement_fee = _parse_money(reinstate.group(1))

    _parse_vehicles(normalized, result)
    _parse_drivers(normalized, result)

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

    _append_synthesized_payments(result)

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
    if "MAYA ASSURANCE" in upper:
        return parse_maya_assurance_dec_text(text)
    if "HEREFORD" in upper or "HIC- DEC" in upper or "HIC-ALI" in upper:
        return parse_hereford_dec_text(text)
    if _parse_policy_number(text):
        result = parse_american_transit_dec_text(text)
        result.parse_warnings.append("Carrier not recognized; used American Transit parser.")
        return result
    if re.search(r"\d+-MA\d+", text, re.I):
        result = parse_maya_assurance_dec_text(text)
        result.parse_warnings.append("Carrier not recognized; used Maya Assurance parser.")
        return result
    raise DecPageParseError(
        "Unsupported declaration page format. Currently supported: American Transit (ATIC), "
        "Maya Assurance, Hereford Insurance (HIC)."
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
        if payment.fee > ZERO:
            row = build_installment_row(
                policy,
                payment.amount,
                installment_fee=payment.fee,
                apply_fee=True,
            )
        elif payment.label == "DEPOSIT":
            row = build_installment_row(
                policy,
                payment.amount,
                installment_fee=installment_fee,
                apply_fee=False,
            )
        else:
            row = build_installment_row(
                policy,
                payment.amount,
                installment_fee=installment_fee,
                apply_fee=True,
            )
        TLCInstallment.objects.create(
            policy=policy,
            installment_number=number,
            due_date=payment.due_date,
            amount=row["amount"],
            installment_fee=row["installment_fee"],
            commission_amount=row["commission_amount"],
            balance=row["balance"],
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
        if parsed.vehicles[0].plate:
            policy.plate_number = parsed.vehicles[0].plate
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
    elif parsed.monthly_installment > ZERO:
        breakdown.monthly_installment = parsed.monthly_installment
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

    from .tlc_accounting import sync_installment_accounting, sync_policy_commission_amount

    sync_policy_commission_amount(policy)
    policy.save(update_fields=["carrier_commission_amount", "updated_at"])
    sync_installment_accounting(policy)

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
