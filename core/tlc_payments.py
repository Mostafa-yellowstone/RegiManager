"""TLC payment capture, split methods, and receipt generation."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .tlc_models import (
    TLCEndorsement,
    TLCInstallment,
    TLCPaymentSplit,
    TLCPaymentTransaction,
    TLCPolicy,
    TLCReceipt,
    TLCReinstatement,
    TLCDMVService,
)

ZERO = Decimal("0.00")


class TLCPaymentError(Exception):
    """Raised when a TLC payment cannot be recorded."""


def _money(value) -> Decimal:
    if value in (None, ""):
        return ZERO
    try:
        return Decimal(str(value).replace(",", "").replace("$", "").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return ZERO


def _parse_date(value) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_time(value) -> time | None:
    if isinstance(value, time):
        return value
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def generate_transaction_id() -> str:
    return f"TXN-{uuid.uuid4().hex[:12].upper()}"


def generate_receipt_number(organization_id: int) -> str:
    stamp = timezone.now().strftime("%Y%m%d")
    seq = TLCReceipt.objects.filter(policy__organization_id=organization_id).count() + 1
    return f"XIS-{stamp}-{seq:05d}"


def parse_payment_splits_from_post(post) -> list[dict[str, Any]]:
    """Parse split payment rows from POST (supports indexed and single-row forms)."""
    methods = post.getlist("split_method")
    amounts = post.getlist("split_amount")
    references = post.getlist("split_reference")
    approvals = post.getlist("split_approval")
    last_fours = post.getlist("split_last_four")
    notes_list = post.getlist("split_notes")

    if not methods and post.get("payment_method"):
        methods = [post.get("payment_method")]
        amounts = [post.get("amount_received") or post.get("split_amount") or "0"]
        references = [post.get("reference_number", "")]
        approvals = [post.get("approval_number", "")]
        last_fours = [post.get("last_four", "")]
        notes_list = [post.get("split_notes") or post.get("notes", "")]

    rows: list[dict[str, Any]] = []
    for index, method in enumerate(methods):
        amount = _money(amounts[index] if index < len(amounts) else ZERO)
        if amount <= ZERO and not (method or "").strip():
            continue
        rows.append(
            {
                "payment_method": (method or "cash").strip() or "cash",
                "amount": amount,
                "reference_number": (references[index] if index < len(references) else "") or "",
                "approval_number": (approvals[index] if index < len(approvals) else "") or "",
                "last_four": (last_fours[index] if index < len(last_fours) else "") or "",
                "notes": (notes_list[index] if index < len(notes_list) else "") or "",
                "sort_order": index,
            }
        )
    return rows


def resolve_payment_target(
    policy: TLCPolicy,
    *,
    installment_id=None,
    reinstatement_id=None,
    endorsement_id=None,
    dmv_service_id=None,
) -> tuple[str, Decimal, str, dict]:
    """Return (transaction_type, amount_due, description, linked_objects)."""
    links: dict = {
        "installment": None,
        "reinstatement": None,
        "endorsement": None,
        "dmv_service": None,
    }

    if installment_id:
        installment = TLCInstallment.objects.get(id=installment_id, policy=policy)
        notes_lower = (installment.notes or "").lower()
        txn_type = (
            TLCPaymentTransaction.TransactionType.DOWN_PAYMENT
            if "deposit" in notes_lower or "down" in notes_lower
            else TLCPaymentTransaction.TransactionType.INSTALLMENT
        )
        links["installment"] = installment
        return (
            txn_type,
            installment.total_due,
            f"Installment #{installment.installment_number}"
            + (f" — {installment.notes}" if installment.notes else ""),
            links,
        )

    if reinstatement_id:
        row = TLCReinstatement.objects.get(id=reinstatement_id, policy=policy)
        links["reinstatement"] = row
        return (
            TLCPaymentTransaction.TransactionType.REINSTATEMENT,
            Decimal(row.reinstatement_fee or ZERO),
            "Reinstatement fee",
            links,
        )

    if endorsement_id:
        row = TLCEndorsement.objects.get(id=endorsement_id, policy=policy)
        amount = Decimal(row.endorsement_fee or ZERO)
        if row.premium_difference and row.premium_difference > ZERO:
            amount = (amount + Decimal(row.premium_difference)).quantize(Decimal("0.01"))
        links["endorsement"] = row
        return (
            TLCPaymentTransaction.TransactionType.ENDORSEMENT,
            amount,
            f"Endorsement — {row.get_endorsement_type_display()}",
            links,
        )

    if dmv_service_id:
        row = TLCDMVService.objects.get(id=dmv_service_id, policy=policy)
        links["dmv_service"] = row
        return (
            TLCPaymentTransaction.TransactionType.DMV,
            Decimal(row.fee_charged or ZERO),
            f"DMV/TLC — {row.get_service_type_display()}",
            links,
        )

    raise TLCPaymentError("Select an installment, reinstatement, endorsement, or DMV service to collect payment.")


def build_receipt_snapshot(policy: TLCPolicy, txn: TLCPaymentTransaction) -> dict:
    from .tlc_profitability import build_policy_profitability

    profit = build_policy_profitability(policy)
    installments = list(policy.installments.all())
    paid = [row for row in installments if row.is_paid]
    unpaid = [row for row in installments if not row.is_paid]
    next_due = unpaid[0] if unpaid else None
    history = []
    for past in policy.payment_transactions.filter(status=TLCPaymentTransaction.Status.COMPLETED).select_related(
        "processed_by"
    ).prefetch_related("splits", "receipts")[:50]:
        receipt = past.receipts.order_by("-version").first()
        method_labels = ", ".join(s.get_payment_method_display() for s in past.splits.all()) or "—"
        history.append(
            {
                "date": past.payment_date.isoformat(),
                "receipt_number": receipt.receipt_number if receipt else "—",
                "transaction_type": past.get_transaction_type_display(),
                "amount": str(past.amount_received),
                "payment_method": method_labels,
                "processed_by": (
                    past.processed_by.get_full_name() or past.processed_by.username
                    if past.processed_by_id
                    else "—"
                ),
                "status": past.get_status_display(),
            }
        )
    schedule = [
        {
            "installment_number": row.installment_number,
            "due_date": row.due_date.isoformat() if row.due_date else "",
            "amount": str(row.total_due),
            "status": "Paid" if row.is_paid else ("Past Due" if row.due_date and row.due_date < date.today() else "Upcoming"),
        }
        for row in installments
    ]
    unpaid_balance = sum((row.total_due for row in unpaid), ZERO).quantize(Decimal("0.01"))
    org = policy.organization
    agency_name = (org.insurance_intake_display_name or org.name or "Xpress Insurance Solutions Inc.").strip()
    return {
        "agency": {
            "name": agency_name,
            "address": ", ".join(p for p in [org.address_line, org.city, org.state] if p),
            "phone": org.phone_number or "",
            "email": org.email or "",
            "website": "",
            "npn": "",
            "license": org.psbc_license or "",
            "logo_path": org.logo.path if org.logo else "",
        },
        "customer": {
            "name": policy.named_insured or "",
            "business_name": policy.business_name or "",
            "phone": getattr(policy.client, "phone_number", "") if policy.client_id else "",
            "email": (getattr(policy.client, "email", "") or "") if policy.client_id else "",
            "address": policy.insured_address or "",
        },
        "policy": {
            "policy_number": policy.policy_number,
            "policy_type": policy.get_policy_type_display(),
            "carrier": policy.carrier or "",
            "status": policy.get_status_display(),
            "status_code": policy.status,
            "effective_date": policy.effective_date.isoformat() if policy.effective_date else "",
            "expiration_date": policy.expiration_date.isoformat() if policy.expiration_date else "",
            "vin": policy.vin or "",
            "plate_number": policy.plate_number or "",
            "tlc_number": policy.tlc_license_number or policy.tlc_base_number or "",
            "driver": policy.driver_name or "",
            "vehicle": (
                f"{policy.policy_vehicles.first().year or ''} {policy.policy_vehicles.first().make or ''}".strip()
                if policy.policy_vehicles.exists()
                else ""
            ),
        },
        "payment": {
            "transaction_id": txn.transaction_id,
            "transaction_type": txn.get_transaction_type_display(),
            "status": txn.get_status_display(),
            "description": txn.description,
            "amount_due": str(txn.amount_due),
            "amount_received": str(txn.amount_received),
            "payment_date": txn.payment_date.isoformat(),
            "payment_time": txn.payment_time.strftime("%I:%M %p") if txn.payment_time else "",
            "processed_by": (
                txn.processed_by.get_full_name() or txn.processed_by.username
                if txn.processed_by_id
                else "—"
            ),
            "splits": [
                {
                    "payment_method": s.get_payment_method_display(),
                    "reference_number": s.reference_number,
                    "amount": str(s.amount),
                    "approval_number": s.approval_number,
                    "last_four": s.last_four,
                    "notes": s.notes,
                }
                for s in txn.splits.all()
            ],
        },
        "breakdown": {
            "policy_premium": str((txn.installment.amount if txn.installment_id else ZERO)),
            "installment_fee": str(txn.installment.installment_fee if txn.installment_id else ZERO),
            "late_fee": str(txn.installment.late_fee if txn.installment_id else ZERO),
            "nsf_fee": str(txn.installment.nsf_fee if txn.installment_id else ZERO),
            "reinstatement_fee": str(
                txn.reinstatement.reinstatement_fee if txn.reinstatement_id else ZERO
            ),
            "endorsement_fee": str(txn.endorsement.endorsement_fee if txn.endorsement_id else ZERO),
            "dmv_fee": str(txn.dmv_service.fee_charged if txn.dmv_service_id else ZERO),
            "broker_fee": "0.00",
            "total_due": str(txn.amount_due),
            "payment_received": str(txn.amount_received),
            "remaining_balance": str(unpaid_balance),
        },
        "installment_summary": {
            "paid_count": len(paid),
            "total_count": len(installments),
            "remaining_count": len(unpaid),
            "monthly_payment": str(unpaid[0].total_due) if unpaid else "0.00",
            "next_due_date": next_due.due_date.isoformat() if next_due and next_due.due_date else "",
            "past_due": str(profit.get("past_due_amount") or ZERO),
            "current_balance": str(unpaid_balance),
        },
        "schedule": schedule,
        "history": history,
        "account_summary": {
            "original_premium": str(profit.get("written_premium") or ZERO),
            "endorsements": str(profit.get("endorsement_adjustments") or ZERO),
            "current_written_premium": str(profit.get("current_written_premium") or ZERO),
            "payments_made": str(profit.get("total_collected") or ZERO),
            "outstanding_balance": str(unpaid_balance),
            "fees": str(
                (
                    Decimal(str(profit.get("installment_fees_collected") or ZERO))
                    + Decimal(str(profit.get("late_fees_collected") or ZERO))
                    + Decimal(str(profit.get("nsf_fees") or ZERO))
                ).quantize(Decimal("0.01"))
            ),
        },
        "notices": [
            "Thank you for your payment.",
            "Failure to make future payments before the due date may result in policy cancellation.",
            "Please keep this receipt for your records.",
        ],
    }


@transaction.atomic
def record_tlc_payment(
    policy: TLCPolicy,
    *,
    user=None,
    payment_date: date | None = None,
    payment_time: time | None = None,
    splits: list[dict] | None = None,
    notes: str = "",
    installment_id=None,
    reinstatement_id=None,
    endorsement_id=None,
    dmv_service_id=None,
    transaction_type: str | None = None,
    amount_due: Decimal | None = None,
    description: str = "",
) -> tuple[TLCPaymentTransaction, TLCReceipt]:
    txn_type, due, auto_description, links = resolve_payment_target(
        policy,
        installment_id=installment_id,
        reinstatement_id=reinstatement_id,
        endorsement_id=endorsement_id,
        dmv_service_id=dmv_service_id,
    )
    if transaction_type:
        txn_type = transaction_type
    if amount_due is not None:
        due = _money(amount_due)
    if description:
        auto_description = description

    rows = list(splits or [])
    if not rows:
        raise TLCPaymentError("Add at least one payment method.")
    received = sum((row["amount"] for row in rows), ZERO).quantize(Decimal("0.01"))
    if received <= ZERO:
        raise TLCPaymentError("Payment received must be greater than zero.")
    if due > ZERO and abs(received - due) > Decimal("0.01"):
        # Allow over/under pay but require totals when due is known and user intended full pay
        pass

    pay_date = _parse_date(payment_date) or timezone.localdate()
    pay_time = _parse_time(payment_time) or timezone.localtime().time().replace(microsecond=0)

    installment = links["installment"]
    if installment and installment.is_paid:
        raise TLCPaymentError("This installment is already marked paid.")

    if len(rows) > 1:
        txn_type = TLCPaymentTransaction.TransactionType.SPLIT_PAYMENT

    txn = TLCPaymentTransaction.objects.create(
        organization=policy.organization,
        policy=policy,
        transaction_id=generate_transaction_id(),
        transaction_type=txn_type,
        status=TLCPaymentTransaction.Status.COMPLETED,
        amount_due=due,
        amount_received=received,
        payment_date=pay_date,
        payment_time=pay_time,
        processed_by=user,
        installment=installment,
        reinstatement=links["reinstatement"],
        endorsement=links["endorsement"],
        dmv_service=links["dmv_service"],
        description=auto_description,
        notes=notes or "",
    )
    for row in rows:
        TLCPaymentSplit.objects.create(transaction=txn, **row)

    if installment:
        installment.is_paid = True
        installment.payment_date = pay_date
        installment.balance = ZERO
        installment.save(update_fields=["is_paid", "payment_date", "balance"])
        from .tlc_accounting import sync_installment_accounting

        sync_installment_accounting(policy)

    from .tlc_models import TLCPolicyTimelineEvent

    event_type = TLCPolicyTimelineEvent.EventType.DOWN_PAYMENT
    if txn_type == TLCPaymentTransaction.TransactionType.INSTALLMENT:
        event_type = TLCPolicyTimelineEvent.EventType.INSTALLMENT
    elif txn_type == TLCPaymentTransaction.TransactionType.REINSTATEMENT:
        event_type = TLCPolicyTimelineEvent.EventType.REINSTATEMENT
    elif txn_type == TLCPaymentTransaction.TransactionType.ENDORSEMENT:
        event_type = TLCPolicyTimelineEvent.EventType.ENDORSEMENT
    elif txn_type == TLCPaymentTransaction.TransactionType.DOWN_PAYMENT:
        event_type = TLCPolicyTimelineEvent.EventType.DOWN_PAYMENT
    else:
        event_type = TLCPolicyTimelineEvent.EventType.INSTALLMENT

    TLCPolicyTimelineEvent.objects.create(
        policy=policy,
        event_type=event_type,
        event_date=pay_date,
        title=f"Payment received — {auto_description}",
        description=f"{txn.transaction_id}: ${received} via {len(rows)} method(s).",
        created_by=user,
    )

    snapshot = build_receipt_snapshot(policy, txn)
    receipt_number = generate_receipt_number(policy.organization_id)
    payload = json.dumps(snapshot, sort_keys=True, default=str)
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    receipt = TLCReceipt.objects.create(
        transaction=txn,
        policy=policy,
        receipt_number=receipt_number,
        version=1,
        generated_by=user,
        content_hash=content_hash,
        snapshot_json=snapshot,
    )

    from .tlc_receipt_pdf import render_tlc_receipt_pdf

    pdf_bytes = render_tlc_receipt_pdf(receipt)
    receipt.pdf_file.save(f"{receipt_number}.pdf", ContentFile(pdf_bytes), save=True)
    return txn, receipt
