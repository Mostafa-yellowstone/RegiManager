"""Views for TLC customer payment capture and invoice/receipt access."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .tlc_models import TLCPaymentTransaction, TLCPolicy, TLCReceipt
from .tlc_payments import (
    TLCPaymentError,
    parse_payment_splits_from_post,
    record_tlc_payment,
    _parse_date,
    _parse_time,
)
from .tlc_views import _resolve_tlc_access, _tlc_url


@login_required
@require_POST
def record_tlc_payment_view(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    try:
        splits = parse_payment_splits_from_post(request.POST)
        txn, receipt = record_tlc_payment(
            policy,
            user=request.user,
            payment_date=_parse_date(request.POST.get("payment_date")),
            payment_time=_parse_time(request.POST.get("payment_time")),
            splits=splits,
            notes=request.POST.get("notes", "").strip(),
            installment_id=request.POST.get("installment_id") or None,
            reinstatement_id=request.POST.get("reinstatement_id") or None,
            endorsement_id=request.POST.get("endorsement_id") or None,
            dmv_service_id=request.POST.get("dmv_service_id") or None,
        )
    except TLCPaymentError as exc:
        messages.error(request, str(exc))
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=invoices")
    except Exception as exc:
        messages.error(request, f"Could not record payment: {exc}")
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=installments")

    messages.success(
        request,
        f"Payment recorded. Receipt {receipt.receipt_number} generated ({txn.transaction_id}).",
    )
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=invoices")


@login_required
@require_GET
def tlc_receipt_detail(request, receipt_id):
    receipt = get_object_or_404(
        TLCReceipt.objects.select_related(
            "policy", "transaction", "generated_by", "policy__organization"
        ).prefetch_related("transaction__splits"),
        id=receipt_id,
    )
    card, is_owner, membership = _resolve_tlc_access(request, card=receipt.policy.space)
    snapshot = receipt.snapshot_json or {}
    return render(
        request,
        "core/tlc_receipt_detail.html",
        {
            "card": card,
            "receipt": receipt,
            "policy": receipt.policy,
            "transaction": receipt.transaction,
            "snapshot": snapshot,
            "is_owner": is_owner,
            "can_manage_tlc": is_owner or (membership and membership.can_deal_with_tlc),
        },
    )


@login_required
@require_GET
def tlc_receipt_pdf(request, receipt_id):
    receipt = get_object_or_404(TLCReceipt.objects.select_related("policy"), id=receipt_id)
    _resolve_tlc_access(request, card=receipt.policy.space)
    if receipt.pdf_file:
        return FileResponse(
            receipt.pdf_file.open("rb"),
            as_attachment=False,
            filename=f"{receipt.receipt_number}.pdf",
            content_type="application/pdf",
        )
    from .tlc_receipt_pdf import render_tlc_receipt_pdf

    pdf_bytes = render_tlc_receipt_pdf(receipt)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{receipt.receipt_number}.pdf"'
    return response
