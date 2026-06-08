"""Helpers for Daily Payment Transactions in Insurance Space."""

from decimal import Decimal

from django.utils import timezone

from .models import DailyPaymentTransaction

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
}

BUSINESS_TYPE_TO_PAYMENT_TYPE = {
    "new_business": DailyPaymentTransaction.PaymentType.NEW_BUSINESS,
    "renewal": DailyPaymentTransaction.PaymentType.RENEWAL,
    "rewrite": DailyPaymentTransaction.PaymentType.ENDORSEMENT,
}

VALID_PAYMENT_METHODS = {key for key in PAYMENT_METHOD_META}
VALID_PAYMENT_TYPES = {choice.value for choice in DailyPaymentTransaction.PaymentType}


def agent_colors(username):
    h = sum(ord(c) for c in username) * 37 % 360
    return f"hsl({h}, 75%, 93%)", f"hsl({h}, 80%, 25%)"


def summarize_daily_payments(transactions):
    """Build method totals and grand total from a transaction queryset/list."""
    totals = {method: Decimal("0.00") for method in PAYMENT_METHOD_META}
    for tx in transactions:
        totals[tx.payment_method] = totals.get(tx.payment_method, Decimal("0.00")) + tx.amount

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


def enrich_daily_transactions(transactions):
    """Attach agent display colors to transaction objects."""
    enriched = []
    for tx in transactions:
        if tx.recorded_by:
            bg, text = agent_colors(tx.recorded_by.username)
            tx.agent_bg_color = bg
            tx.agent_text_color = text
            tx.agent_name = tx.recorded_by.get_full_name() or tx.recorded_by.username
        else:
            tx.agent_bg_color = "#f1f5f9"
            tx.agent_text_color = "#475569"
            tx.agent_name = "—"
        enriched.append(tx)
    return enriched


def create_daily_payment_from_policy(policy, payment_method, agent):
    """Auto-log broker fee collection when a policy is saved with a payment method."""
    if not payment_method or payment_method not in VALID_PAYMENT_METHODS:
        return None
    if not policy.broker_fee or policy.broker_fee <= 0:
        return None

    payment_type = BUSINESS_TYPE_TO_PAYMENT_TYPE.get(
        policy.business_type,
        DailyPaymentTransaction.PaymentType.MISC,
    )

    return DailyPaymentTransaction.objects.create(
        organization=policy.organization,
        client=policy.client,
        insurance_policy=policy,
        transaction_date=timezone.localdate(),
        amount=policy.broker_fee,
        payment_type=payment_type,
        payment_method=payment_method,
        recorded_by=agent,
        notes=f"Auto-logged from policy {policy.policy_number}",
    )
