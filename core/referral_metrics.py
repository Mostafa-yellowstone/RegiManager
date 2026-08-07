"""Referral list metrics without N+1 queries."""

from decimal import Decimal

from django.db.models import Count, Sum

from .models import ServiceRecord


def attach_referral_list_metrics(referrals):
    """
    Set `outstanding` and accurate `record_count` (direct FK + via client.referral).
    Uses a few aggregate queries instead of N.
    """
    referral_list = list(referrals)
    if not referral_list:
        return referral_list

    ref_ids = [ref.id for ref in referral_list]
    direct = {
        row["referral_id"]: row["total"] or Decimal("0")
        for row in ServiceRecord.objects.filter(
            referral_id__in=ref_ids,
            is_referral_paid=False,
        )
        .values("referral_id")
        .annotate(total=Sum("referral_balance"))
    }
    via_client = {
        row["vehicle__client__referral_id"]: row["total"] or Decimal("0")
        for row in ServiceRecord.objects.filter(
            vehicle__client__referral_id__in=ref_ids,
            is_referral_paid=False,
        )
        .exclude(referral_id__in=ref_ids)
        .values("vehicle__client__referral_id")
        .annotate(total=Sum("referral_balance"))
    }
    direct_counts = {
        row["referral_id"]: row["n"] or 0
        for row in ServiceRecord.objects.filter(referral_id__in=ref_ids)
        .values("referral_id")
        .annotate(n=Count("id"))
    }
    via_counts = {
        row["vehicle__client__referral_id"]: row["n"] or 0
        for row in ServiceRecord.objects.filter(
            vehicle__client__referral_id__in=ref_ids,
        )
        .exclude(referral_id__in=ref_ids)
        .values("vehicle__client__referral_id")
        .annotate(n=Count("id"))
    }

    for ref in referral_list:
        service_outstanding = direct.get(ref.id, Decimal("0")) + via_client.get(
            ref.id, Decimal("0")
        )
        ref.outstanding = service_outstanding + (ref.initial_balance or Decimal("0"))
        ref.record_count = direct_counts.get(ref.id, 0) + via_counts.get(ref.id, 0)
    return referral_list
