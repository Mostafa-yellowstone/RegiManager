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
    InsurancePolicyInstallment,
)

ZERO = Decimal("0.00")
_DATE_MDY = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})")
_MONEY = re.compile(r"\$?\s*([\d,]+\.\d{2})")
_POLICY_NUMBER = re.compile(
    r"(?:Policy\s*(?:Number|No\.?#?|#)|POL(?:ICY)?\s*(?:NO\.?|#))\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{4,})",
    re.I,
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
    effective_date: date | None = None
    expiration_date: date | None = None
    premium: Decimal | None = None
    down_payment: Decimal | None = None
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

    if parsed.carrier:
        company = _resolve_or_create_company(policy.organization, parsed.carrier)
        if policy.insurance_company_id != company.id:
            policy.insurance_company = company
            update_fields.append("insurance_company")

    policy.save(update_fields=list(dict.fromkeys(update_fields)))

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
