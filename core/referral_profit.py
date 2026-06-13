"""Referral commission and net profit helpers."""

from decimal import Decimal

from django.db.models import Q

from .models import Referral, ServiceRecord


def resolve_referral_for_record(record):
    """Referral partner tied to a service record (direct or via client)."""
    if record.referral_id:
        return record.referral
    vehicle = getattr(record, "vehicle", None)
    if vehicle and getattr(vehicle, "client", None) and vehicle.client.referral_id:
        return vehicle.client.referral
    return None


def commission_amount(processing_fee, referral_fee) -> Decimal:
    """Referral share capped at gross processing fee."""
    gross = processing_fee or Decimal("0")
    fee = referral_fee or Decimal("0")
    if fee <= 0 or gross <= 0:
        return Decimal("0")
    return min(fee, gross)


def net_processing_profit(processing_fee, referral_commission) -> Decimal:
    gross = processing_fee or Decimal("0")
    commission = referral_commission or Decimal("0")
    return gross - commission


def effective_commission_for_record(record) -> Decimal:
    if record.referral_commission and record.referral_commission > 0:
        return record.referral_commission
    referral = resolve_referral_for_record(record)
    if not referral:
        return Decimal("0")
    return commission_amount(record.processing_fee, referral.referral_fee)


def records_for_referral(referral):
    return ServiceRecord.objects.filter(
        Q(referral=referral) | Q(vehicle__client__referral=referral)
    ).distinct()


def apply_referral_fee_to_records(referral):
    """Recompute stored commission on every record linked to this referral."""
    fee = referral.referral_fee or Decimal("0")
    records = list(records_for_referral(referral))
    for record in records:
        record.referral_commission = (
            commission_amount(record.processing_fee, fee) if fee > 0 else Decimal("0")
        )
    if records:
        ServiceRecord.objects.bulk_update(records, ["referral_commission"])
    return len(records)


def profit_totals_for_records(records):
    gross = Decimal("0")
    referral_earnings = Decimal("0")
    for record in records:
        proc = record.processing_fee or Decimal("0")
        comm = effective_commission_for_record(record)
        gross += proc
        referral_earnings += comm
    net_psb = gross - referral_earnings
    return {
        "gross_processing": gross,
        "referral_earnings": referral_earnings,
        "net_psb_profit": net_psb,
    }
