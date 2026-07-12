"""Views for the TLC Policy Profitability Engine space."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .http import deny_access
from .models import Client, OrganizationMembership, Space, Vehicle
from .space_access import require_space_access
from .tlc_client_sync import apply_client_to_policy
from .tlc_models import (
    TLCAgencyExpense,
    TLCCarrierCommissionRule,
    TLCCarrierRemittance,
    TLCCarrierStatement,
    TLCCarrierStatementLine,
    TLCDMVService,
    TLCEndorsement,
    TLCFinanceCompany,
    TLCInstallment,
    TLCInstallmentReminder,
    TLCPolicy,
    TLCPolicyDocument,
    TLCPolicyFinance,
    TLCPolicyTimelineEvent,
    TLCPremiumBreakdown,
    TLCReinstatement,
)
from .tlc_analytics import build_receivables_aging, build_renewal_forecast
from .tlc_commissions import apply_commission_rule_to_policy
from .tlc_profitability import build_policy_profitability, tlc_dashboard_stats
from .tlc_reconciliation import reconcile_statement
from .tlc_schedule import generate_installment_schedule
from .tlc_tasks import schedule_installment_reminders
from .views import _get_user_organizations


def _parse_decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _resolve_tlc_access(request, space_id=None, card=None):
    organizations = _get_user_organizations(request)
    if card is None:
        card = get_object_or_404(
            Space,
            id=space_id,
            organization__in=organizations,
            key="tlc",
        )

    if request.user.is_superuser:
        return card, True, None

    membership = OrganizationMembership.objects.filter(
        user=request.user,
        organization=card.organization,
        is_active=True,
        organization__is_active=True,
    ).first()
    if not membership:
        deny_access("Access denied.")

    is_owner = membership.role == OrganizationMembership.Role.OWNER
    require_space_access(membership, card)
    return card, is_owner, membership


def _tlc_url(card, tab=None, policy_id=None):
    from django.urls import reverse

    if policy_id:
        url = reverse("tlc-policy-detail", kwargs={"space_id": card.id, "policy_id": policy_id})
    else:
        url = reverse("inventory-detail", kwargs={"inventory_id": card.id})
    params = []
    if tab:
        params.append(f"tab={tab}")
    if params:
        url += "?" + "&".join(params)
    return url


def _redirect_tlc(card, tab=None):
    return redirect(_tlc_url(card, tab=tab))


def _record_timeline(policy, event_type, title, *, event_date=None, user=None, description=""):
    TLCPolicyTimelineEvent.objects.create(
        policy=policy,
        event_type=event_type,
        event_date=event_date,
        title=title,
        description=description,
        created_by=user,
    )


def build_tlc_space_context(request, card, is_owner, membership):
    active_org = card.organization
    stats = tlc_dashboard_stats(card)
    search = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    carrier_filter = request.GET.get("carrier", "").strip()

    policies_qs = (
        TLCPolicy.objects.filter(space=card)
        .select_related("client", "producer", "csr", "premium_breakdown")
        .order_by("-created_at")
    )
    if search:
        policies_qs = policies_qs.filter(
            Q(policy_number__icontains=search)
            | Q(named_insured__icontains=search)
            | Q(business_name__icontains=search)
            | Q(carrier__icontains=search)
            | Q(vin__icontains=search)
            | Q(plate_number__icontains=search)
            | Q(tlc_base_number__icontains=search)
        )
    if status_filter:
        policies_qs = policies_qs.filter(status=status_filter)
    if carrier_filter:
        policies_qs = policies_qs.filter(carrier__icontains=carrier_filter)

    page = Paginator(policies_qs, 15).get_page(request.GET.get("page", 1))
    policy_rows = []
    for policy in page:
        policy_rows.append(
            {
                "policy": policy,
                "profit": build_policy_profitability(policy),
            }
        )

    carriers = (
        TLCPolicy.objects.filter(space=card)
        .exclude(carrier="")
        .values_list("carrier", flat=True)
        .distinct()
        .order_by("carrier")
    )

    can_manage = is_owner or (membership and membership.can_deal_with_tlc)

    return {
        "card": card,
        "active_org": active_org,
        "is_owner": is_owner,
        "can_manage_tlc": can_manage,
        "stats": stats,
        "policies_page": page,
        "policy_rows": policy_rows,
        "carriers": carriers,
        "clients": Client.objects.filter(organization=active_org).order_by("first_name", "last_name")[:500],
        "vehicles": Vehicle.objects.filter(client__organization=active_org).select_related("client")[:500],
        "commission_rules": TLCCarrierCommissionRule.objects.filter(organization=active_org),
        "finance_companies": TLCFinanceCompany.objects.filter(organization=active_org),
        "carrier_statements": TLCCarrierStatement.objects.filter(organization=active_org)[:50],
        "receivables_aging": build_receivables_aging(card),
        "renewal_forecast": build_renewal_forecast(card),
        "active_tab": request.GET.get("tab", "dashboard"),
        "search": search,
        "status_filter": status_filter,
        "carrier_filter": carrier_filter,
        "status_choices": TLCPolicy.Status.choices,
        "policy_type_choices": TLCPolicy.PolicyType.choices,
    }


def build_tlc_policy_detail_context(request, card, policy, is_owner, membership):
    profit = build_policy_profitability(policy)
    can_manage = is_owner or (membership and membership.can_deal_with_tlc)
    return {
        "card": card,
        "active_org": card.organization,
        "policy": policy,
        "profit": profit,
        "is_owner": is_owner,
        "can_manage_tlc": can_manage,
        "installments": policy.installments.all(),
        "reinstatements": policy.reinstatements.select_related("processed_by"),
        "endorsements": policy.endorsements.select_related("processed_by"),
        "dmv_services": policy.dmv_services.all(),
        "agency_expenses": policy.agency_expenses.all(),
        "carrier_remittances": policy.carrier_remittances.all(),
        "documents": policy.documents.select_related("uploaded_by"),
        "timeline": policy.timeline_events.select_related("created_by"),
        "breakdown": getattr(policy, "premium_breakdown", None),
        "endorsement_type_choices": TLCEndorsement.EndorsementType.choices,
        "dmv_service_choices": TLCDMVService.ServiceType.choices,
        "expense_type_choices": TLCAgencyExpense.ExpenseType.choices,
        "document_type_choices": TLCPolicyDocument.DocumentType.choices,
        "finance_contract": getattr(policy, "finance_contract", None),
        "finance_companies": TLCFinanceCompany.objects.filter(organization=card.organization, is_active=True),
        "reminders": policy.installment_reminders.select_related("installment").order_by("scheduled_for")[:50],
        "active_tab": request.GET.get("tab", "overview"),
    }


@login_required
def tlc_policy_detail(request, space_id, policy_id):
    card, is_owner, membership = _resolve_tlc_access(request, space_id=space_id)
    policy = get_object_or_404(
        TLCPolicy.objects.select_related(
            "premium_breakdown", "client", "vehicle", "producer", "csr", "finance_contract__finance_company"
        )
        .prefetch_related(
            "installments",
            "reinstatements",
            "endorsements",
            "dmv_services",
            "agency_expenses",
            "carrier_remittances",
            "documents",
            "timeline_events",
        ),
        id=policy_id,
        space=card,
    )
    context = build_tlc_policy_detail_context(request, card, policy, is_owner, membership)
    return render(request, "core/tlc_policy_detail.html", context)


@login_required
@require_POST
def add_tlc_policy(request, space_id):
    card, is_owner, membership = _resolve_tlc_access(request, space_id=space_id)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "You do not have permission to add TLC policies.")
        return _redirect_tlc(card)

    policy_number = request.POST.get("policy_number", "").strip()
    if not policy_number:
        messages.error(request, "Policy number is required.")
        return _redirect_tlc(card, tab="policies")

    if TLCPolicy.objects.filter(organization=card.organization, policy_number=policy_number).exists():
        messages.error(request, "A policy with this number already exists.")
        return _redirect_tlc(card, tab="policies")

    client_id = request.POST.get("client") or None
    vehicle_id = request.POST.get("vehicle") or None
    client = Client.objects.filter(id=client_id, organization=card.organization).first() if client_id else None
    vehicle = (
        Vehicle.objects.filter(id=vehicle_id, client__organization=card.organization).first()
        if vehicle_id
        else None
    )

    policy = TLCPolicy.objects.create(
        organization=card.organization,
        space=card,
        policy_number=policy_number,
        carrier=request.POST.get("carrier", "").strip(),
        policy_type=request.POST.get("policy_type", TLCPolicy.PolicyType.NEW_BUSINESS),
        named_insured=request.POST.get("named_insured", "").strip(),
        business_name=request.POST.get("business_name", "").strip(),
        tlc_base_number=request.POST.get("tlc_base_number", "").strip(),
        tlc_license_number=request.POST.get("tlc_license_number", "").strip(),
        vin=request.POST.get("vin", "").strip(),
        plate_number=request.POST.get("plate_number", "").strip(),
        driver_name=request.POST.get("driver_name", "").strip(),
        broker_name=request.POST.get("broker_name", "").strip(),
        status=request.POST.get("status", TLCPolicy.Status.PENDING),
        effective_date=_parse_date(request.POST.get("effective_date")),
        expiration_date=_parse_date(request.POST.get("expiration_date")),
        renewal_date=_parse_date(request.POST.get("renewal_date")),
        commission_rate=_parse_decimal(request.POST.get("commission_rate")),
        broker_fee_collected=_parse_decimal(request.POST.get("broker_fee_collected")),
        added_by=request.user,
    )
    apply_client_to_policy(policy, client, vehicle)
    if request.POST.get("named_insured", "").strip():
        policy.named_insured = request.POST.get("named_insured", "").strip()
    if request.POST.get("business_name", "").strip():
        policy.business_name = request.POST.get("business_name", "").strip()

    TLCPremiumBreakdown.objects.create(
        policy=policy,
        total_written_premium=_parse_decimal(request.POST.get("total_written_premium")),
        down_payment=_parse_decimal(request.POST.get("down_payment")),
        amount_financed=_parse_decimal(request.POST.get("amount_financed")),
        number_of_installments=int(request.POST.get("number_of_installments") or 0),
        monthly_installment=_parse_decimal(request.POST.get("monthly_installment")),
        policy_fee=_parse_decimal(request.POST.get("policy_fee")),
        installment_fee=_parse_decimal(request.POST.get("installment_fee")),
    )
    if not policy.commission_rate:
        apply_commission_rule_to_policy(policy, save=False)
    policy.save()

    if policy.premium_breakdown.number_of_installments > 0:
        generate_installment_schedule(policy, replace_existing=True)

    _record_timeline(
        policy,
        TLCPolicyTimelineEvent.EventType.QUOTE,
        "Policy created",
        event_date=policy.effective_date,
        user=request.user,
    )
    messages.success(request, f"TLC policy {policy.policy_number} created.")
    return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)


@login_required
@require_POST
def add_tlc_installment(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    installment_number = int(request.POST.get("installment_number") or 1)
    is_paid = request.POST.get("is_paid") == "on"
    amount = _parse_decimal(request.POST.get("amount"))
    balance = _parse_decimal(request.POST.get("balance"), default=amount if not is_paid else Decimal("0"))

    TLCInstallment.objects.update_or_create(
        policy=policy,
        installment_number=installment_number,
        defaults={
            "due_date": _parse_date(request.POST.get("due_date")) or policy.effective_date,
            "amount": amount,
            "installment_fee": _parse_decimal(request.POST.get("installment_fee")),
            "is_paid": is_paid,
            "payment_date": _parse_date(request.POST.get("payment_date")) if is_paid else None,
            "late_fee": _parse_decimal(request.POST.get("late_fee")),
            "nsf_fee": _parse_decimal(request.POST.get("nsf_fee")),
            "was_reinstated": request.POST.get("was_reinstated") == "on",
            "balance": balance,
            "notes": request.POST.get("notes", "").strip(),
        },
    )
    _record_timeline(
        policy,
        TLCPolicyTimelineEvent.EventType.INSTALLMENT,
        f"Installment #{installment_number}",
        event_date=_parse_date(request.POST.get("payment_date")) or _parse_date(request.POST.get("due_date")),
        user=request.user,
    )
    messages.success(request, "Installment saved.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=installments")


@login_required
@require_POST
def add_tlc_dmv_service(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    TLCDMVService.objects.create(
        policy=policy,
        service_type=request.POST.get("service_type", TLCDMVService.ServiceType.REGISTRATION),
        fee_charged=_parse_decimal(request.POST.get("fee_charged")),
        dmv_tlc_cost=_parse_decimal(request.POST.get("dmv_tlc_cost")),
        service_date=_parse_date(request.POST.get("service_date")),
        notes=request.POST.get("notes", "").strip(),
    )
    messages.success(request, "DMV/TLC service recorded.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=dmv")


@login_required
@require_POST
def add_tlc_reinstatement(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    TLCReinstatement.objects.create(
        policy=policy,
        cancellation_date=_parse_date(request.POST.get("cancellation_date")),
        cancellation_reason=request.POST.get("cancellation_reason", "").strip(),
        reinstatement_date=_parse_date(request.POST.get("reinstatement_date")),
        reinstatement_fee=_parse_decimal(request.POST.get("reinstatement_fee")),
        processed_by=request.user,
        carrier_confirmation=request.POST.get("carrier_confirmation", "").strip(),
        is_paid=request.POST.get("is_paid") == "on",
        notes=request.POST.get("notes", "").strip(),
    )
    policy.status = TLCPolicy.Status.REINSTATED
    policy.save(update_fields=["status", "updated_at"])
    _record_timeline(
        policy,
        TLCPolicyTimelineEvent.EventType.REINSTATEMENT,
        "Policy reinstated",
        event_date=_parse_date(request.POST.get("reinstatement_date")),
        user=request.user,
    )
    messages.success(request, "Reinstatement recorded.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=reinstatements")


@login_required
@require_POST
def add_tlc_endorsement(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    premium_diff = _parse_decimal(request.POST.get("premium_difference"))
    TLCEndorsement.objects.create(
        policy=policy,
        endorsement_type=request.POST.get("endorsement_type", TLCEndorsement.EndorsementType.OTHER),
        premium_difference=premium_diff,
        commission_difference=_parse_decimal(request.POST.get("commission_difference")),
        effective_date=_parse_date(request.POST.get("effective_date")),
        processed_by=request.user,
        notes=request.POST.get("notes", "").strip(),
    )
    policy.endorsement_balance += premium_diff
    policy.save(update_fields=["endorsement_balance", "updated_at"])
    _record_timeline(
        policy,
        TLCPolicyTimelineEvent.EventType.ENDORSEMENT,
        "Endorsement processed",
        event_date=_parse_date(request.POST.get("effective_date")),
        user=request.user,
    )
    messages.success(request, "Endorsement saved.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=endorsements")


@login_required
@require_POST
def add_tlc_expense(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    TLCAgencyExpense.objects.create(
        policy=policy,
        expense_type=request.POST.get("expense_type", TLCAgencyExpense.ExpenseType.MISC),
        amount=_parse_decimal(request.POST.get("amount")),
        expense_date=_parse_date(request.POST.get("expense_date")),
        notes=request.POST.get("notes", "").strip(),
    )
    messages.success(request, "Expense recorded.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=expenses")


@login_required
@require_POST
def add_tlc_remittance(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    amount = _parse_decimal(request.POST.get("amount"))
    TLCCarrierRemittance.objects.create(
        policy=policy,
        amount=amount,
        remittance_date=_parse_date(request.POST.get("remittance_date")),
        notes=request.POST.get("notes", "").strip(),
    )
    policy.amount_remitted_to_carrier += amount
    policy.save(update_fields=["amount_remitted_to_carrier", "updated_at"])
    messages.success(request, "Carrier remittance recorded.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=carrier")


@login_required
@require_POST
def add_tlc_document(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    title = request.POST.get("title", "").strip()
    if not title:
        messages.error(request, "Document title is required.")
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=documents")

    doc = TLCPolicyDocument(
        policy=policy,
        document_type=request.POST.get("document_type", TLCPolicyDocument.DocumentType.OTHER),
        title=title,
        uploaded_by=request.user,
    )
    if request.FILES.get("file"):
        doc.file = request.FILES["file"]
    doc.save()
    messages.success(request, "Document uploaded.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=documents")


@login_required
@require_POST
def generate_tlc_installment_schedule(request, policy_id):
    policy = get_object_or_404(TLCPolicy.objects.select_related("premium_breakdown"), id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)
    created = generate_installment_schedule(policy, replace_existing=request.POST.get("replace") == "1")
    if created:
        messages.success(request, f"Generated {created} installments with installment fees.")
    else:
        messages.error(request, "Set number of installments and monthly amount on premium breakdown first.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=installments")


@login_required
@require_POST
def schedule_tlc_reminders(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)
    days = int(request.POST.get("days_before", 3) or 3)
    count = schedule_installment_reminders(policy, days_before=days)
    messages.success(request, f"Scheduled {count} email reminder(s).")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=reminders")


@login_required
@require_POST
def save_tlc_policy_finance(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)
    company_id = request.POST.get("finance_company") or None
    company = (
        TLCFinanceCompany.objects.filter(id=company_id, organization=card.organization).first()
        if company_id
        else None
    )
    TLCPolicyFinance.objects.update_or_create(
        policy=policy,
        defaults={
            "finance_company": company,
            "contract_number": request.POST.get("contract_number", "").strip(),
            "amount_financed": _parse_decimal(request.POST.get("amount_financed")),
            "payoff_amount": _parse_decimal(request.POST.get("payoff_amount")),
            "next_payoff_date": _parse_date(request.POST.get("next_payoff_date")),
            "is_delinquent": request.POST.get("is_delinquent") == "on",
            "delinquency_notes": request.POST.get("delinquency_notes", "").strip(),
        },
    )
    messages.success(request, "Finance contract saved.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=finance")


@login_required
@require_POST
def add_tlc_commission_rule(request, space_id):
    card, is_owner, membership = _resolve_tlc_access(request, space_id=space_id)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return _redirect_tlc(card, tab="commission_rules")
    carrier = request.POST.get("carrier", "").strip()
    rate = _parse_decimal(request.POST.get("commission_rate"))
    if not carrier or rate <= 0:
        messages.error(request, "Carrier and commission rate are required.")
        return _redirect_tlc(card, tab="commission_rules")
    TLCCarrierCommissionRule.objects.update_or_create(
        organization=card.organization,
        carrier=carrier,
        policy_type=request.POST.get("policy_type", "").strip(),
        product_type=request.POST.get("product_type", "").strip(),
        defaults={
            "commission_rate": rate,
            "renewal_commission_rate": _parse_decimal(request.POST.get("renewal_commission_rate")),
            "notes": request.POST.get("notes", "").strip(),
            "is_active": True,
        },
    )
    messages.success(request, "Commission rule saved.")
    return _redirect_tlc(card, tab="commission_rules")


@login_required
@require_POST
def add_tlc_finance_company(request, space_id):
    card, is_owner, membership = _resolve_tlc_access(request, space_id=space_id)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return _redirect_tlc(card, tab="finance")
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Finance company name is required.")
        return _redirect_tlc(card, tab="finance")
    TLCFinanceCompany.objects.update_or_create(
        organization=card.organization,
        name=name,
        defaults={
            "contact_phone": request.POST.get("contact_phone", "").strip(),
            "contact_email": request.POST.get("contact_email", "").strip(),
            "default_installment_fee": _parse_decimal(request.POST.get("default_installment_fee")),
            "is_active": True,
        },
    )
    messages.success(request, "Finance company saved.")
    return _redirect_tlc(card, tab="finance")


@login_required
@require_POST
def add_tlc_carrier_statement(request, space_id):
    card, is_owner, membership = _resolve_tlc_access(request, space_id=space_id)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return _redirect_tlc(card, tab="reconciliation")
    carrier = request.POST.get("carrier", "").strip()
    statement_date = _parse_date(request.POST.get("statement_date"))
    if not carrier or not statement_date:
        messages.error(request, "Carrier and statement date are required.")
        return _redirect_tlc(card, tab="reconciliation")
    statement = TLCCarrierStatement.objects.create(
        organization=card.organization,
        carrier=carrier,
        statement_date=statement_date,
        period_start=_parse_date(request.POST.get("period_start")),
        period_end=_parse_date(request.POST.get("period_end")),
        total_premium=_parse_decimal(request.POST.get("total_premium")),
        total_commission=_parse_decimal(request.POST.get("total_commission")),
        total_remitted=_parse_decimal(request.POST.get("total_remitted")),
        notes=request.POST.get("notes", "").strip(),
    )
    for line in request.POST.get("lines", "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        policy_number, premium, commission, remitted = parts[0], parts[1], parts[2], parts[3]
        TLCCarrierStatementLine.objects.create(
            statement=statement,
            policy_number=policy_number,
            premium_amount=_parse_decimal(premium),
            commission_amount=_parse_decimal(commission),
            remitted_amount=_parse_decimal(remitted),
        )
    reconcile_statement(statement)
    messages.success(request, "Carrier statement imported and reconciled.")
    return _redirect_tlc(card, tab="reconciliation")
