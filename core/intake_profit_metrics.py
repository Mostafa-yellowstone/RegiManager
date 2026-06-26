"""Net profit metrics for portal intake CRM by acquisition source."""

from __future__ import annotations

from decimal import Decimal

from .referral_profit import effective_commission_for_record
from .source_choices import norm_source


def build_intake_source_profit_cards(records, source_choices, *, selected_source: str = ""):
    """
    Build per-source net profit cards from service records in a date range.
    Net profit = processing fee minus referral commission (effective per record).
    """
    buckets: dict[str, Decimal] = {sc["key"]: Decimal("0.00") for sc in source_choices}
    counts: dict[str, int] = {sc["key"]: 0 for sc in source_choices}
    other_net = Decimal("0.00")
    other_count = 0
    known_keys = set(buckets.keys())

    for record in records.iterator():
        key = norm_source(record.source)
        proc = record.processing_fee or Decimal("0")
        net = proc - effective_commission_for_record(record)
        if key in known_keys:
            buckets[key] += net
            counts[key] += 1
        else:
            other_net += net
            other_count += 1

    cards = []
    grand_total = Decimal("0.00")
    selected_norm = norm_source(selected_source)

    for sc in source_choices:
        net = buckets[sc["key"]]
        grand_total += net
        cards.append(
            {
                "key": sc["key"],
                "label": sc["label"],
                "net_profit": net,
                "transaction_count": counts[sc["key"]],
                "is_selected": bool(selected_norm and selected_norm == sc["key"]),
            }
        )

    if other_count:
        grand_total += other_net
        cards.append(
            {
                "key": "_other",
                "label": "Other Sources",
                "net_profit": other_net,
                "transaction_count": other_count,
                "is_selected": False,
            }
        )

    return cards, grand_total
