"""Edit handlers for TLC space records."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import Client, Vehicle
from .tlc_carriers import ensure_tlc_carrier
from .tlc_client_sync import apply_client_to_policy
from .tlc_commissions import apply_commission_rule_to_policy
from .tlc_installments import build_installment_row
from .tlc_models import (
    TLCCarrierCommissionRule,
    TLCCarrierRemittance,
    TLCCarrierStatement,
    TLCCarrierStatementLine,
    TLCDMVService,
    TLCEndorsement,
    TLCFinanceCompany,
    TLCInstallment,
    TLCPolicy,
    TLCPolicyDocument,
    TLCPremiumBreakdown,
    TLCReinstatement,
)
from .tlc_reconciliation import reconcile_statement
from .tlc_views import (
    TLCPolicyTimelineEvent,
    _parse_date,
    _parse_decimal,
    _record_timeline,
    _resolve_tlc_access,
    _tlc_url,
)


def _deny_manage(request, card, membership, is_owner, *, policy_id=None, tab="overview"):
    messages.error(request, "Permission denied.")
    if policy_id:
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy_id)
    from .tlc_views import _redirect_tlc

    return _redirect_tlc(card, tab=tab)


def _sync_policy_remitted_total(policy: TLCPolicy) -> None:
    total = policy.carrier_remittances.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    policy.amount_remitted_to_carrier = _parse_decimal(total)
    policy.save(update_fields=["amount_remitted_to_carrier", "updated_at"])


def _sync_endorsement_balance(policy: TLCPolicy) -> None:
    from .tlc_accounting import apply_endorsement_accounting

    apply_endorsement_accounting(policy)


@login_required
@require_POST
def edit_tlc_policy(request, policy_id):
    policy = get_object_or_404(TLCPolicy.objects.select_related("premium_breakdown"), id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        return _deny_manage(request, card, membership, is_owner, policy_id=policy.id)

    client_id = request.POST.get("client") or None
    vehicle_id = request.POST.get("vehicle") or None
    client = Client.objects.filter(id=client_id, organization=card.organization).first() if client_id else None
    vehicle = (
        Vehicle.objects.filter(id=vehicle_id, client__organization=card.organization).first()
        if vehicle_id
        else None
    )

    carrier_name = request.POST.get("carrier", "").strip()
    if carrier_name:
        ensure_tlc_carrier(card.organization, carrier_name)
    policy.carrier = carrier_name
    policy.policy_type = request.POST.get("policy_type", policy.policy_type)
    policy.named_insured = request.POST.get("named_insured", "").strip()
    policy.business_name = request.POST.get("business_name", "").strip()
    policy.tlc_base_number = request.POST.get("tlc_base_number", "").strip()
    policy.tlc_license_number = request.POST.get("tlc_license_number", "").strip()
    policy.vin = request.POST.get("vin", "").strip()
    policy.plate_number = request.POST.get("plate_number", "").strip()
    policy.driver_name = request.POST.get("driver_name", "").strip()
    policy.broker_name = request.POST.get("broker_name", "").strip()
    policy.status = request.POST.get("status", policy.status)
    policy.effective_date = _parse_date(request.POST.get("effective_date"))
    policy.expiration_date = _parse_date(request.POST.get("expiration_date"))
    policy.renewal_date = _parse_date(request.POST.get("renewal_date"))
    policy.commission_rate = _parse_decimal(request.POST.get("commission_rate"))
    policy.broker_fee_collected = _parse_decimal(request.POST.get("broker_fee_collected"))
    policy.producer_commission_amount = _parse_decimal(request.POST.get("producer_commission_amount"))
    policy.csr_commission_amount = _parse_decimal(request.POST.get("csr_commission_amount"))
    policy.commission_received = _parse_decimal(request.POST.get("commission_received"))
    apply_client_to_policy(policy, client, vehicle)
    if request.POST.get("named_insured", "").strip():
        policy.named_insured = request.POST.get("named_insured", "").strip()
    if request.POST.get("business_name", "").strip():
        policy.business_name = request.POST.get("business_name", "").strip()

    breakdown, _created = TLCPremiumBreakdown.objects.get_or_create(policy=policy)
    breakdown.total_written_premium = _parse_decimal(request.POST.get("total_written_premium"))
    breakdown.down_payment = _parse_decimal(request.POST.get("down_payment"))
    breakdown.amount_financed = _parse_decimal(request.POST.get("amount_financed"))
    breakdown.number_of_installments = int(request.POST.get("number_of_installments") or 0)
    breakdown.monthly_installment = _parse_decimal(request.POST.get("monthly_installment"))
    breakdown.policy_fee = _parse_decimal(request.POST.get("policy_fee"))
    breakdown.installment_fee = _parse_decimal(request.POST.get("installment_fee"))
    breakdown.finance_charge = _parse_decimal(request.POST.get("finance_charge"))
    breakdown.taxes = _parse_decimal(request.POST.get("taxes"))
    breakdown.save()

    if not policy.commission_rate:
        apply_commission_rule_to_policy(policy, save=False)
    policy.save()
    from .tlc_accounting import apply_endorsement_accounting, sync_policy_commission_amount

    sync_policy_commission_amount(policy)
    policy.save(update_fields=["carrier_commission_amount", "updated_at"])
    messages.success(request, "Policy updated.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")


@login_required
@require_POST
def edit_tlc_installment(request, installment_id):
    installment = get_object_or_404(TLCInstallment, id=installment_id)
    policy = installment.policy
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        return _deny_manage(request, card, membership, is_owner, policy_id=policy.id, tab="installments")

    is_paid = request.POST.get("is_paid") == "on"
    gross = _parse_decimal(request.POST.get("gross_amount") or request.POST.get("amount"))
    per_fee = _parse_decimal(request.POST.get("installment_fee"))
    notes = request.POST.get("notes", "").strip()
    apply_fee = "down payment" not in notes.lower() and "deposit" not in notes.lower()
    row = build_installment_row(policy, gross, installment_fee=per_fee, apply_fee=apply_fee)
    installment.installment_number = int(request.POST.get("installment_number") or installment.installment_number)
    installment.due_date = _parse_date(request.POST.get("due_date")) or installment.due_date
    installment.amount = row["amount"]
    installment.installment_fee = row["installment_fee"]
    installment.commission_amount = row["commission_amount"]
    installment.is_paid = is_paid
    installment.payment_date = _parse_date(request.POST.get("payment_date")) if is_paid else None
    installment.late_fee = _parse_decimal(request.POST.get("late_fee"))
    installment.nsf_fee = _parse_decimal(request.POST.get("nsf_fee"))
    installment.was_reinstated = request.POST.get("was_reinstated") == "on"
    installment.balance = _parse_decimal(
        request.POST.get("balance"), default=Decimal("0") if is_paid else row["balance"]
    )
    installment.notes = notes
    installment.save()
    from .tlc_accounting import sync_installment_accounting

    sync_installment_accounting(policy)
    messages.success(request, "Installment updated.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=installments")


@login_required
@require_POST
def edit_tlc_reinstatement(request, reinstatement_id):
    row = get_object_or_404(TLCReinstatement, id=reinstatement_id)
    policy = row.policy
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        return _deny_manage(request, card, membership, is_owner, policy_id=policy.id, tab="reinstatements")

    row.cancellation_date = _parse_date(request.POST.get("cancellation_date"))
    row.cancellation_reason = request.POST.get("cancellation_reason", "").strip()
    row.reinstatement_date = _parse_date(request.POST.get("reinstatement_date"))
    row.reinstatement_fee = _parse_decimal(request.POST.get("reinstatement_fee"))
    row.dmv_document_number = request.POST.get("dmv_document_number", "").strip()
    row.notes = request.POST.get("notes", "").strip()
    row.save()
    from .tlc_accounting import apply_reinstatement_accounting

    apply_reinstatement_accounting(policy)
    messages.success(request, "Reinstatement updated.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=reinstatements")


@login_required
@require_POST
def edit_tlc_endorsement(request, endorsement_id):
    row = get_object_or_404(TLCEndorsement, id=endorsement_id)
    policy = row.policy
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        return _deny_manage(request, card, membership, is_owner, policy_id=policy.id, tab="endorsements")

    from .tlc_accounting import prepare_endorsement_amounts

    new_written_raw = request.POST.get("new_written_premium", "").strip()
    premium_diff_raw = request.POST.get("premium_difference", "").strip()
    amounts = prepare_endorsement_amounts(
        policy,
        new_written_premium=_parse_decimal(new_written_raw) if new_written_raw else None,
        premium_difference=_parse_decimal(premium_diff_raw) if premium_diff_raw else None,
        endorsement_fee=_parse_decimal(request.POST.get("endorsement_fee")),
        commission_difference=_parse_decimal(request.POST.get("commission_difference")),
        exclude_endorsement_id=row.id,
    )
    row.endorsement_type = request.POST.get("endorsement_type", row.endorsement_type)
    row.premium_difference = amounts["premium_difference"]
    row.written_premium_before = amounts["written_premium_before"]
    row.written_premium_after = amounts["written_premium_after"]
    row.endorsement_fee = amounts["endorsement_fee"]
    row.commission_difference = amounts["commission_difference"]
    row.coverage_change_date = _parse_date(request.POST.get("coverage_change_date"))
    row.notes = request.POST.get("notes", "").strip()
    row.save()
    _sync_endorsement_balance(policy)
    messages.success(request, "Endorsement updated.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=endorsements")


@login_required
@require_POST
def edit_tlc_dmv_service(request, service_id):
    row = get_object_or_404(TLCDMVService, id=service_id)
    policy = row.policy
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        return _deny_manage(request, card, membership, is_owner, policy_id=policy.id, tab="dmv")

    row.service_type = request.POST.get("service_type", row.service_type)
    row.fee_charged = _parse_decimal(request.POST.get("fee_charged"))
    row.dmv_tlc_cost = _parse_decimal(request.POST.get("dmv_tlc_cost"))
    row.service_date = _parse_date(request.POST.get("service_date"))
    row.notes = request.POST.get("notes", "").strip()
    row.save()
    messages.success(request, "DMV/TLC service updated.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=dmv")


@login_required
@require_POST
def edit_tlc_remittance(request, remittance_id):
    row = get_object_or_404(TLCCarrierRemittance, id=remittance_id)
    policy = row.policy
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        return _deny_manage(request, card, membership, is_owner, policy_id=policy.id, tab="carrier")

    row.amount = _parse_decimal(request.POST.get("amount"))
    row.remittance_date = _parse_date(request.POST.get("remittance_date"))
    row.notes = request.POST.get("notes", "").strip()
    row.save()
    _sync_policy_remitted_total(policy)
    messages.success(request, "Remittance updated.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=carrier")


@login_required
@require_POST
def edit_tlc_document(request, document_id):
    row = get_object_or_404(TLCPolicyDocument, id=document_id)
    policy = row.policy
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        return _deny_manage(request, card, membership, is_owner, policy_id=policy.id, tab="documents")

    title = request.POST.get("title", "").strip()
    if not title:
        messages.error(request, "Document title is required.")
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=documents")
    row.title = title
    row.document_type = request.POST.get("document_type", row.document_type)
    if request.FILES.get("file"):
        row.file = request.FILES["file"]
    row.save()
    messages.success(request, "Document updated.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=documents")


@login_required
@require_POST
def edit_tlc_commission_rule(request, rule_id):
    rule = get_object_or_404(TLCCarrierCommissionRule, id=rule_id)
    from .models import Space
    from .tlc_views import _redirect_tlc

    card = get_object_or_404(Space, organization=rule.organization, key="tlc")
    card, is_owner, membership = _resolve_tlc_access(request, card=card)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return _redirect_tlc(card, tab="commission_rules")

    rule.carrier = request.POST.get("carrier", "").strip() or rule.carrier
    rule.policy_type = request.POST.get("policy_type", "").strip()
    rule.product_type = request.POST.get("product_type", "").strip()
    rule.commission_rate = _parse_decimal(request.POST.get("commission_rate"), default=rule.commission_rate)
    rule.renewal_commission_rate = _parse_decimal(request.POST.get("renewal_commission_rate"))
    rule.notes = request.POST.get("notes", "").strip()
    rule.is_active = request.POST.get("is_active") == "on"
    rule.save()
    messages.success(request, "Commission rule updated.")
    return _redirect_tlc(card, tab="commission_rules")


@login_required
@require_POST
def edit_tlc_finance_company(request, company_id):
    company = get_object_or_404(TLCFinanceCompany, id=company_id)
    from .models import Space

    card = get_object_or_404(Space, organization=company.organization, key="tlc")
    card, is_owner, membership = _resolve_tlc_access(request, card=card)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        from .tlc_views import _redirect_tlc

        messages.error(request, "Permission denied.")
        return _redirect_tlc(card, tab="finance")

    company.name = request.POST.get("name", "").strip() or company.name
    company.contact_phone = request.POST.get("contact_phone", "").strip()
    company.contact_email = request.POST.get("contact_email", "").strip()
    company.default_installment_fee = _parse_decimal(request.POST.get("default_installment_fee"))
    company.is_active = request.POST.get("is_active") == "on"
    company.save()
    messages.success(request, "Finance company updated.")
    from .tlc_views import _redirect_tlc

    return _redirect_tlc(card, tab="finance")


@login_required
@require_POST
def edit_tlc_carrier_statement(request, statement_id):
    statement = get_object_or_404(TLCCarrierStatement, id=statement_id)
    from .models import Space

    card = get_object_or_404(Space, organization=statement.organization, key="tlc")
    card, is_owner, membership = _resolve_tlc_access(request, card=card)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        from .tlc_views import _redirect_tlc

        messages.error(request, "Permission denied.")
        return _redirect_tlc(card, tab="reconciliation")

    statement.carrier = request.POST.get("carrier", "").strip() or statement.carrier
    statement.statement_date = _parse_date(request.POST.get("statement_date")) or statement.statement_date
    statement.period_start = _parse_date(request.POST.get("period_start"))
    statement.period_end = _parse_date(request.POST.get("period_end"))
    statement.total_premium = _parse_decimal(request.POST.get("total_premium"))
    statement.total_commission = _parse_decimal(request.POST.get("total_commission"))
    statement.total_remitted = _parse_decimal(request.POST.get("total_remitted"))
    statement.notes = request.POST.get("notes", "").strip()
    statement.save()

    if request.POST.get("lines", "").strip():
        statement.lines.all().delete()
        for line in request.POST.get("lines", "").splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 4:
                continue
            TLCCarrierStatementLine.objects.create(
                statement=statement,
                policy_number=parts[0],
                premium_amount=_parse_decimal(parts[1]),
                commission_amount=_parse_decimal(parts[2]),
                remitted_amount=_parse_decimal(parts[3]),
            )
    reconcile_statement(statement)
    messages.success(request, "Carrier statement updated.")
    from .tlc_views import _redirect_tlc

    return _redirect_tlc(card, tab="reconciliation")
