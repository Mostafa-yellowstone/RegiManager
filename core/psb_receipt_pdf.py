"""Shared helpers for classic PSB service receipt PDFs."""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_DOWN

from .models import ServiceRecord

OFFICIAL_FOOTER_LINES = (
    "This is a Liscensed Private Service Bureau, but is not an official agency",
    "of the Department of Motor Vehicles , State of New York",
)

OFFICIAL_FOOTER = " ".join(OFFICIAL_FOOTER_LINES)


def dollars_to_words(amount) -> str:
    dollars = int(Decimal(str(amount or 0)).quantize(Decimal("1"), rounding=ROUND_DOWN))
    if dollars == 0:
        return "Zero"

    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def under_thousand(n: int) -> str:
        if n == 0:
            return ""
        if n < 20:
            return ones[n]
        if n < 100:
            return f"{tens[n // 10]}{' ' + ones[n % 10] if n % 10 else ''}".strip()
        return f"{ones[n // 100]} Hundred{' ' + under_thousand(n % 100) if n % 100 else ''}".strip()

    parts = []
    millions = dollars // 1_000_000
    if millions:
        parts.append(f"{under_thousand(millions)} Million")
        dollars %= 1_000_000
    thousands = dollars // 1_000
    if thousands:
        parts.append(f"{under_thousand(thousands)} Thousand")
        dollars %= 1_000
    if dollars:
        parts.append(under_thousand(dollars))
    return " ".join(parts)


def format_receipt_number_display(service_record) -> str:
    """Show receipt # as digits only (consecutive per PSB, e.g. 00001)."""
    if service_record.organization_id:
        seq = ServiceRecord.objects.filter(
            organization_id=service_record.organization_id,
            id__lte=service_record.id,
        ).count()
        return f"{seq:05d}"

    digits = re.sub(r"\D", "", str(service_record.receipt_number or ""))
    if digits:
        return digits[-5:].zfill(5)
    return "00000"
