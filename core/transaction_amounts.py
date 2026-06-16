"""Canonical fee and outstanding-balance math for service transactions."""

from decimal import Decimal, ROUND_HALF_UP

from .models import ServiceRecord

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

CC_RATE_BY_METHOD = {
    "american_express": Decimal("0.05"),
    "visa": Decimal("0.035"),
    "mastercard": Decimal("0.035"),
    "discover": Decimal("0.035"),
    "diners_club": Decimal("0.035"),
}


def quantize_money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def cc_rate_for_method(method: str | None) -> Decimal:
    return CC_RATE_BY_METHOD.get((method or "").strip(), ZERO)


def base_fees_from_record(record) -> Decimal:
    """Sum of fee fields before credit-card surcharge."""
    return quantize_money(
        (record.processing_fee or ZERO)
        + (record.dmv_fee or ZERO)
        + (record.sales_tax or ZERO)
        + (record.dmv_sales_tax or ZERO)
        + (record.other_fees or ZERO)
        + (record.other_dmv_fee or ZERO)
    )


def base_fees_from_mapping(data: dict) -> Decimal:
    return quantize_money(
        (data.get("processing_fee") or ZERO)
        + (data.get("dmv_fee") or ZERO)
        + (data.get("sales_tax") or ZERO)
        + (data.get("dmv_sales_tax") or ZERO)
        + (data.get("other_fees") or ZERO)
        + (data.get("other_dmv_fee") or ZERO)
    )


def inclusive_to_base(inclusive_amount, method: str | None) -> Decimal:
    """Reverse fee-inclusive payment to raw base using the method's CC rate."""
    inclusive = quantize_money(inclusive_amount)
    rate = cc_rate_for_method(method)
    if inclusive <= ZERO or rate <= ZERO:
        return inclusive
    return quantize_money(inclusive / (Decimal("1") + rate))


def cc_fee_on_base(base_amount, method: str | None) -> Decimal:
    base = quantize_money(base_amount)
    rate = cc_rate_for_method(method)
    if base <= ZERO or rate <= ZERO:
        return ZERO
    return quantize_money(base * rate)


def compute_credit_card_fee(
    *,
    base_total: Decimal,
    payment_method: str | None,
    payment_method_2: str | None = None,
    paid_amount: Decimal | None = None,
    paid_amount_2: Decimal | None = None,
) -> Decimal:
    """
    Match the start-process form rules:
    - Single method: CC fee applies to the full base fee total.
    - Split methods: CC fee applies only to each paid portion's base.
    """
    base_total = quantize_money(base_total)
    paid_amount = quantize_money(paid_amount)
    paid_amount_2 = quantize_money(paid_amount_2)
    method_2 = (payment_method_2 or "").strip()

    if method_2 and paid_amount_2 > ZERO:
        p2_inclusive = paid_amount_2
        p1_inclusive = quantize_money(paid_amount - paid_amount_2)
        if p1_inclusive < ZERO:
            p1_inclusive = ZERO
        p1_base = inclusive_to_base(p1_inclusive, payment_method)
        p2_base = inclusive_to_base(p2_inclusive, payment_method_2)
        return quantize_money(
            cc_fee_on_base(p1_base, payment_method)
            + cc_fee_on_base(p2_base, payment_method_2)
        )

    return cc_fee_on_base(base_total, payment_method)


def compute_service_fee(record) -> Decimal:
    base = base_fees_from_record(record)
    cc = compute_credit_card_fee(
        base_total=base,
        payment_method=record.payment_method,
        payment_method_2=record.payment_method_2,
        paid_amount=record.paid_amount,
        paid_amount_2=record.paid_amount_2,
    )
    return quantize_money(base + cc)


def compute_referral_balance(service_fee: Decimal, paid_amount: Decimal) -> Decimal:
    """Outstanding balance; drop sub-penny rounding dust (e.g. 0.004 -> 0.00, not 0.01)."""
    service_fee = quantize_money(service_fee)
    paid_amount = quantize_money(paid_amount)
    raw_balance = service_fee - paid_amount
    balance = quantize_money(raw_balance)
    if balance == CENT and raw_balance < CENT:
        return ZERO
    return balance


def apply_transaction_amounts(record) -> None:
    """Recompute service_fee, credit_card_fee, referral_balance, and paid flag on a record."""
    base = base_fees_from_record(record)
    paid = quantize_money(record.paid_amount)
    record.paid_amount = paid

    cc_fee = compute_credit_card_fee(
        base_total=base,
        payment_method=record.payment_method,
        payment_method_2=record.payment_method_2,
        paid_amount=paid,
        paid_amount_2=record.paid_amount_2,
    )
    record.credit_card_fee = cc_fee
    record.service_fee = quantize_money(base + cc_fee)
    record.referral_balance = compute_referral_balance(record.service_fee, paid)
    record.is_referral_paid = record.referral_balance <= ZERO


def amounts_from_cleaned_form(cleaned_data: dict) -> tuple[Decimal, Decimal, Decimal]:
    """Return (service_fee, referral_balance, credit_card_fee) from form cleaned data."""
    base = base_fees_from_mapping(cleaned_data)
    paid = quantize_money(cleaned_data.get("paid_amount"))
    paid_2 = quantize_money(cleaned_data.get("paid_amount_2"))
    cc_fee = compute_credit_card_fee(
        base_total=base,
        payment_method=cleaned_data.get("payment_method"),
        payment_method_2=cleaned_data.get("payment_method_2"),
        paid_amount=paid,
        paid_amount_2=paid_2,
    )
    service_fee = quantize_money(base + cc_fee)
    balance = compute_referral_balance(service_fee, paid)
    return service_fee, balance, cc_fee
