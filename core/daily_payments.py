"""Helpers for Daily Payment Transactions in Insurance Space."""

from decimal import Decimal

from .models import DailyPaymentTransaction

ZERO = Decimal("0.00")

PAYMENT_METHOD_META = {
    "cash": {
        "label": "Cash",
        "icon": "💵",
        "gradient": "linear-gradient(135deg, #14532d 0%, #166534 45%, #4ade80 100%)",
        "accent": "#bbf7d0",
    },
    "zelle": {
        "label": "Zelle",
        "icon": "📱",
        "gradient": "linear-gradient(135deg, #4c1d95 0%, #6d28d9 45%, #a78bfa 100%)",
        "accent": "#ede9fe",
    },
    "credit_card": {
        "label": "Credit Card",
        "icon": "💳",
        "gradient": "linear-gradient(135deg, #0f172a 0%, #1e3a8a 45%, #3b82f6 100%)",
        "accent": "#dbeafe",
    },
    "checks": {
        "label": "Checks",
        "icon": "📝",
        "gradient": "linear-gradient(135deg, #78350f 0%, #b45309 45%, #fbbf24 100%)",
        "accent": "#fef3c7",
    },
    "payment_hub": {
        "label": "Payment Hub",
        "icon": "🏦",
        "gradient": "linear-gradient(135deg, #0c4a6e 0%, #0369a1 45%, #38bdf8 100%)",
        "accent": "#e0f2fe",
    },
}

# ServiceRecord card brands still roll into the credit_card summary bucket on Finance hub.
CARD_PAYMENT_METHODS = frozenset({
    "visa",
    "mastercard",
    "discover",
    "diners_club",
    "american_express",
    "credit_card",
})

VALID_PAYMENT_METHODS = {choice.value for choice in DailyPaymentTransaction.PaymentMethod}
VALID_PAYMENT_TYPES = {choice.value for choice in DailyPaymentTransaction.PaymentType}


def payment_fee_breakdown(payment: DailyPaymentTransaction) -> dict:
    """Base amount + Section 2119 / broker / CC fees — matches receipt grand total."""
    base = Decimal(str(payment.amount or 0)).quantize(Decimal("0.01"))
    section = ZERO
    if payment.payment_type in (
        DailyPaymentTransaction.PaymentType.NEW_BUSINESS,
        DailyPaymentTransaction.PaymentType.RENEWAL,
    ):
        raw = getattr(payment, "section_2119", None)
        if raw is not None and raw > 0:
            section = Decimal(str(raw)).quantize(Decimal("0.01"))
    broker_fee = ZERO
    raw_broker = getattr(payment, "broker_fee", None)
    if raw_broker is not None and raw_broker > 0:
        broker_fee = Decimal(str(raw_broker)).quantize(Decimal("0.01"))
    cc_fee = ZERO
    raw_cc = getattr(payment, "credit_card_fee", None)
    if raw_cc is not None and raw_cc > 0:
        cc_fee = Decimal(str(raw_cc)).quantize(Decimal("0.01"))
    return {
        "base": base,
        "section_2119": section,
        "broker_fee": broker_fee,
        "credit_card_fee": cc_fee,
        "total": base + section + broker_fee + cc_fee,
        "has_section_2119": section > 0,
        "has_broker_fee": broker_fee > 0,
        "has_credit_card_fee": cc_fee > 0,
        "has_fees": section > 0 or broker_fee > 0 or cc_fee > 0,
    }


def payment_grand_total(payment: DailyPaymentTransaction) -> Decimal:
    """CRM / receipt display total for a daily payment."""
    return payment_fee_breakdown(payment)["total"]


def bucket_payment_method(payment_method: str) -> str | None:
    """Map a stored payment method onto a summary-card bucket."""
    if payment_method in PAYMENT_METHOD_META:
        return payment_method
    if payment_method in CARD_PAYMENT_METHODS:
        return "credit_card"
    return None


def agent_colors(username):
    h = sum(ord(c) for c in username) * 37 % 360
    return f"hsl({h}, 75%, 93%)", f"hsl({h}, 80%, 25%)"


def summarize_daily_payments(transactions):
    """Build method totals and grand total using receipt grand totals (amount + fees)."""
    totals = {method: Decimal("0.00") for method in PAYMENT_METHOD_META}
    for tx in transactions:
        bucket = bucket_payment_method(tx.payment_method)
        if bucket:
            totals[bucket] = totals.get(bucket, Decimal("0.00")) + payment_grand_total(tx)

    method_cards = []
    for method, meta in PAYMENT_METHOD_META.items():
        method_cards.append({
            "key": method,
            "label": meta["label"],
            "icon": meta["icon"],
            "gradient": meta["gradient"],
            "accent": meta["accent"],
            "total": totals.get(method, Decimal("0.00")),
        })

    grand_total = sum(totals.values(), Decimal("0.00"))
    return method_cards, grand_total


def compute_payable_total(organization):
    """Sum of uncleared daily payments (grand totals) owed to the bank."""
    qs = DailyPaymentTransaction.objects.filter(
        organization=organization,
        is_cleared=False,
    )
    return sum((payment_grand_total(tx) for tx in qs.iterator()), ZERO)


def sum_payment_grand_totals(queryset) -> Decimal:
    return sum((payment_grand_total(tx) for tx in queryset.iterator()), ZERO)


def enrich_daily_transactions(transactions):
    """Attach agent display colors and receipt grand total to transaction objects."""
    enriched = []
    for tx in transactions:
        fees = payment_fee_breakdown(tx)
        tx.display_total = fees["total"]
        tx.fee_breakdown = fees
        if tx.recorded_by:
            bg, text = agent_colors(tx.recorded_by.username)
            tx.agent_bg_color = bg
            tx.agent_text_color = text
            tx.agent_name = tx.recorded_by.get_full_name() or tx.recorded_by.username
        else:
            tx.agent_bg_color = "#f1f5f9"
            tx.agent_text_color = "#475569"
            tx.agent_name = "—"
        if tx.updated_by:
            editor_bg, editor_text = agent_colors(tx.updated_by.username)
            tx.editor_bg_color = editor_bg
            tx.editor_text_color = editor_text
            tx.editor_name = tx.updated_by.get_full_name() or tx.updated_by.username
        else:
            tx.editor_bg_color = ""
            tx.editor_text_color = ""
            tx.editor_name = ""
        enriched.append(tx)
    return enriched
