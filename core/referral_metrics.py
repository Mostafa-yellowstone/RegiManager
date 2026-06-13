"""Referral list metrics without N+1 queries."""

from decimal import Decimal

from django.db.models import Q, Sum

from .models import Referral, ServiceRecord


def attach_referral_list_metrics(referrals):
    """
    Set `outstanding`, `display_category` is set by caller.
    Adds outstanding balance in two aggregate queries instead of N.
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

    for ref in referral_list:
        service_outstanding = direct.get(ref.id, Decimal("0")) + via_client.get(ref.id, Decimal("0"))
        ref.outstanding = service_outstanding + (ref.initial_balance or Decimal("0"))
    return referral_list
