"""Net profit metrics for portal intake CRM by acquisition source."""

from __future__ import annotations

from decimal import Decimal

from .referral_profit import effective_commission_for_record
from .source_choices import _label_for_key, norm_source, resolve_acquisition_source_for_record


def build_intake_source_profit_cards(records, source_choices, *, selected_source: str = ""):
    """
    Build per-source net profit cards from service records in a date range.
    Net profit = processing fee minus referral commission (effective per record).

    Sources outside the standard choice list each get their own card (not lumped
    into a single "Other Sources" total).
    """
    buckets: dict[str, Decimal] = {sc["key"]: Decimal("0.00") for sc in source_choices}
    counts: dict[str, int] = {sc["key"]: 0 for sc in source_choices}
    labels: dict[str, str] = {sc["key"]: sc["label"] for sc in source_choices}
    choice_keys = [sc["key"] for sc in source_choices]

    for record in records.iterator():
        raw_source = resolve_acquisition_source_for_record(record)
        key = norm_source(raw_source)
        if not key:
            continue
        proc = record.processing_fee or Decimal("0")
        net = proc - effective_commission_for_record(record)
        if key not in buckets:
            buckets[key] = Decimal("0.00")
            counts[key] = 0
            labels[key] = _label_for_key(key, raw_source)
        buckets[key] += net
        counts[key] += 1

    cards = []
    grand_total = Decimal("0.00")
    selected_norm = norm_source(selected_source)
    extra_keys = sorted(
        (key for key in buckets if key not in choice_keys),
        key=lambda key: labels[key].lower(),
    )

    for key in choice_keys + extra_keys:
        net = buckets[key]
        grand_total += net
        cards.append(
            {
                "key": key,
                "label": labels[key],
                "net_profit": net,
                "transaction_count": counts[key],
                "is_selected": bool(selected_norm and selected_norm == key),
            }
        )

    return cards, grand_total
