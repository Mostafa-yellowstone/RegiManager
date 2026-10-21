"""Side effects of producer payouts: the matching bank entry and the producer's email notice."""

from __future__ import annotations

import logging
import threading
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Sum
from django.template.loader import render_to_string

from .email_branding import (
    attach_brand_logo,
    email_brand_for_org,
    outbound_from_email,
    wrap_email_html,
)
from .insurance_producers import ZERO, money
from .models import BankAccount, BankTransaction

logger = logging.getLogger(__name__)

EXPENSE_CATEGORY = "Producer Commission"
INCOME_CATEGORY = "Producer Repayment"


def bank_account_for_org(organization, raw_id):
    raw = str(raw_id or "").strip()
    if not raw.isdigit():
        return None
    return BankAccount.objects.filter(organization=organization, id=int(raw)).first()


def _bank_fields(net: Decimal) -> tuple[str, str, Decimal]:
    if net >= 0:
        return BankTransaction.TransactionType.EXPENSE_DEBIT_TRANSFER, EXPENSE_CATEGORY, net
    return BankTransaction.TransactionType.INCOME_CREDIT_TRANSFER, INCOME_CATEGORY, -net


def record_bank_entry(payouts, bank_account, *, producer, paid_on, reference: str = ""):
    """One bank entry for the net of ``payouts``; links every payout to it. Returns the entry or None."""
    payouts = list(payouts)
    net = money(sum((p.amount for p in payouts), ZERO))
    if not payouts or net == 0:
        return None
    tx_type, category, amount = _bank_fields(net)
    policies = ", ".join(sorted({p.policy.policy_number or f"#{p.policy_id}" for p in payouts}))
    description = f"{producer.name} · {reference + ' · ' if reference else ''}{policies}"[:500]
    entry = BankTransaction.objects.create(
        bank_account=bank_account,
        transaction_type=tx_type,
        amount=amount,
        category=category,
        description=description,
        date=paid_on,
    )
    for p in payouts:
        p.bank_transaction = entry
    type(payouts[0]).objects.filter(id__in=[p.id for p in payouts]).update(bank_transaction=entry)
    return entry


def resync_bank_entry(entry_id) -> None:
    """Keep a bank entry equal to the net of the payouts still linked to it (delete when none are left)."""
    if not entry_id:
        return
    entry = BankTransaction.objects.select_for_update().filter(id=entry_id).first()
    if entry is None:
        return
    net = money(entry.producer_payouts.aggregate(total=Sum("amount"))["total"] or ZERO)
    if net == 0:
        entry.delete()
        return
    tx_type, category, amount = _bank_fields(net)
    if (entry.transaction_type, entry.amount) != (tx_type, amount):
        entry.transaction_type = tx_type
        entry.category = category
        entry.amount = amount
        entry.save()


# ── email ───────────────────────────────────────────────────────────────────


def _build_message(subject, text_body, to_email, inner, brand, *, include_logo: bool):
    message = EmailMultiAlternatives(subject, text_body, outbound_from_email(), [to_email])
    if include_logo and attach_brand_logo(message, brand):
        html_brand, logo_mode = brand, "cid"
    else:
        html_brand, logo_mode = {**brand, "logo_bytes": b"", "logo_cid": "", "logo_data_uri": ""}, "cid"
    message.attach_alternative(wrap_email_html(inner, html_brand, logo_mode=logo_mode), "text/html")
    return message


def _deliver(build) -> None:
    try:
        build(True).send(fail_silently=False)
    except Exception:
        logger.exception("Producer payout email with logo failed; retrying without logo")
        try:
            build(False).send(fail_silently=False)
        except Exception:
            logger.exception("Producer payout email failed")


def _send_in_background(build) -> None:
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    if "locmem" in backend or "console" in backend:
        _deliver(build)
        return
    threading.Thread(target=_deliver, args=(build,), daemon=True).start()


def producer_email_problem(producer) -> str:
    """Why a payout notice can't be emailed to this producer ("" when it can)."""
    email = (producer.email or "").strip()
    if not email:
        return "This producer has no email address."
    try:
        validate_email(email)
    except ValidationError:
        return "This producer's email address is not valid."
    return ""


def queue_payout_email(producer, payouts, *, paid_on, method_label: str, portal_url: str = "") -> None:
    """Email the producer a payment notice once the surrounding transaction commits."""
    if producer_email_problem(producer):
        return
    rows = [
        {
            "policy_number": p.policy.policy_number or f"#{p.policy_id}",
            "client": p.policy.client.name if p.policy.client_id else "",
            "is_deduction": p.amount < 0,
            "amount": money(abs(p.amount)),
        }
        for p in payouts
    ]
    net = money(sum((p.amount for p in payouts), ZERO))
    org = producer.organization
    to_email = producer.email.strip()

    def _on_commit():
        brand = email_brand_for_org(org)
        context = {
            "producer_name": producer.name,
            "agency_name": brand["name"],
            "rows": rows,
            "net": abs(net),
            "is_repayment": net < 0,
            "paid_on": paid_on,
            "method_label": method_label,
            "portal_url": portal_url,
        }
        inner = render_to_string("core/emails/producer_payout.html", context)
        text_body = render_to_string("core/emails/producer_payout.txt", {**context, "brand": brand})
        if net < 0:
            subject = f"{brand['name']}: ${abs(net):,.2f} repayment recorded"
        else:
            subject = f"{brand['name']}: ${net:,.2f} commission payment"
        _send_in_background(
            lambda with_logo: _build_message(
                subject[:180], text_body, to_email, inner, brand, include_logo=with_logo
            )
        )

    transaction.on_commit(_on_commit)
