"""Net profit metrics for portal intake CRM by acquisition source."""

from __future__ import annotations

from decimal import Decimal

from .referral_profit import effective_commission_for_record
from .source_choices import norm_source, resolve_acquisition_source_for_record

GOOGLE_SEARCH_ROLLUP_KEY = "google_search"


def _profit_bucket_key(source_key: str, choice_keys: list[str]) -> str:
    """Map non-standard sources into the Google Search profit card."""
    if source_key in choice_keys:
        return source_key
    if GOOGLE_SEARCH_ROLLUP_KEY in choice_keys:
        return GOOGLE_SEARCH_ROLLUP_KEY
    return source_key


def build_intake_source_profit_cards(records, source_choices, *, selected_source: str = ""):
    """
    Build per-source net profit cards from service records in a date range.
    Net profit = processing fee minus referral commission (effective per record).

    Transactions whose source is not a standard acquisition channel are rolled into
    the Google Search card (profit and transaction count combined).
    """
    buckets: dict[str, Decimal] = {sc["key"]: Decimal("0.00") for sc in source_choices}
    counts: dict[str, int] = {sc["key"]: 0 for sc in source_choices}
    labels: dict[str, str] = {sc["key"]: sc["label"] for sc in source_choices}
    choice_keys = [sc["key"] for sc in source_choices]

    for record in records.iterator():
        source_key = norm_source(resolve_acquisition_source_for_record(record))
        if not source_key:
            continue
        bucket_key = _profit_bucket_key(source_key, choice_keys)
        if bucket_key not in buckets:
            continue
        proc = record.processing_fee or Decimal("0")
        net = proc - effective_commission_for_record(record)
        buckets[bucket_key] += net
        counts[bucket_key] += 1

    cards = []
    grand_total = Decimal("0.00")
    selected_norm = norm_source(selected_source)
    selected_bucket = (
        _profit_bucket_key(selected_norm, choice_keys) if selected_norm else ""
    )

    for sc in source_choices:
        key = sc["key"]
        net = buckets[key]
        grand_total += net
        cards.append(
            {
                "key": key,
                "label": labels[key],
                "net_profit": net,
                "transaction_count": counts[key],
                "is_selected": bool(selected_bucket and selected_bucket == key),
            }
        )

    return cards, grand_total
