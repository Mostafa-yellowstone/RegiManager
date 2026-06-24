"""Issue refunds against DMV service receipts."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from .models import ServiceAuditLog, ServiceRecord, ServiceRecordPayment
from .service_payments import ensure_opening_ledger_entry, log_refund_payment, reconcile_ledger_balances

REFUND_NOTE_PREFIX = "Refund for"


def _copy_snapshot_fields(original: ServiceRecord) -> dict:
    return {
        "organization": original.organization,
        "vehicle": original.vehicle,
        "client_name": original.client_name,
        "client_identifier": original.client_identifier,
        "client_address": original.client_address,
        "vehicle_number": original.vehicle_number,
        "plate_number": original.plate_number,
        "vin": original.vin,
        "license_number": original.license_number,
        "driver_license_number": original.driver_license_number,
        "phone_no": original.phone_no,
        "email": original.email,
        "terminal_number": original.terminal_number,
        "transaction_type": original.transaction_type,
        "service_type": original.service_type,
        "payment_method": original.payment_method,
        "source": original.source,
        "referral": original.referral,
        "transaction_date": original.transaction_date or timezone.localdate(),
    }


def can_refund_service_record(record: ServiceRecord) -> bool:
    if record.status == "refund":
        return False
    if record.deleted_at is not None:
        return False
    if (record.paid_amount or Decimal("0")) <= Decimal("0"):
        return False
    return not record.refund_entries.filter(status="refund").exists()


def issue_service_refund(original: ServiceRecord, *, recorded_by) -> ServiceRecord:
    """Refund the full paid amount, reduce the original receipt, and add a refund row."""
    if not can_refund_service_record(original):
        raise ValueError("This transaction cannot be refunded.")

    with transaction.atomic():
        original = ServiceRecord.objects.select_for_update().get(pk=original.pk)
        refund_amount = original.paid_amount or Decimal("0")
        if refund_amount <= Decimal("0"):
            raise ValueError("No payment to refund.")
        if original.refund_entries.filter(status="refund").exists():
            raise ValueError("This receipt was already refunded.")

        refund_record = ServiceRecord(
            **_copy_snapshot_fields(original),
            handled_by=recorded_by,
            status="refund",
            paid_amount=refund_amount,
            paid_amount_2=Decimal("0"),
            payment_method_2=None,
            processing_fee=Decimal("0"),
            referral_commission=Decimal("0"),
            dmv_fee=Decimal("0"),
            sales_tax=Decimal("0"),
            dmv_sales_tax=Decimal("0"),
            credit_card_fee=Decimal("0"),
            other_fees=Decimal("0"),
            other_dmv_fee=Decimal("0"),
            service_fee=refund_amount,
            referral_balance=Decimal("0"),
            is_referral_paid=False,
            notes=f"{REFUND_NOTE_PREFIX} {original.receipt_number}",
            refunded_from=original,
        )
        ts = timezone.now().strftime("%Y%m%d%H%M%S")
        refund_record.receipt_number = (
            f"RFND-{ts}-{get_random_string(4, '0123456789')}-{original.organization_id}"
        )
        refund_record.case_id = None
        refund_record.save()

        log_refund_payment(
            original,
            refund_amount,
            payment_method=original.payment_method,
            payment_date=original.transaction_date,
            recorded_by=recorded_by,
        )
        original.paid_amount = Decimal("0")
        original.paid_amount_2 = Decimal("0")
        original.payment_method_2 = None
        original.save()
        ensure_opening_ledger_entry(original, recorded_by=recorded_by)
        reconcile_ledger_balances(original)

        ServiceAuditLog.objects.create(
            organization=original.organization,
            service_record=original,
            actor=recorded_by,
            action="updated",
            details=f"Refunded ${refund_amount:.2f} via {refund_record.receipt_number}",
        )
        ServiceAuditLog.objects.create(
            organization=original.organization,
            service_record=refund_record,
            actor=recorded_by,
            action="created",
            details=f"Refund issued for {original.receipt_number}",
        )

    return refund_record
