"""Views for the TLC Policy Profitability Engine space."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .http import deny_access
from .models import Client, OrganizationMembership, Space, Vehicle
from .space_access import require_space_access
from .tlc_carriers import ensure_tlc_carrier, get_tlc_carrier_names
from .tlc_client_sync import apply_client_to_policy
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
    TLCInstallmentReminder,
    TLCPolicy,
    TLCPolicyCancellation,
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


def _money_label(value) -> str:
    amount = _parse_decimal(value)
    prefix = "+" if amount > 0 else ""
    return f"{prefix}${amount}"


def _record_timeline(policy, event_type, title, *, event_date=None, user=None, description=""):
    TLCPolicyTimelineEvent.objects.create(
        policy=policy,
        event_type=event_type,
        event_date=event_date,
        title=title,
        description=description,
        created_by=user,
    )


def _policy_carrier_choices(organization_id: int, current: str = "") -> list[str]:
    carriers = get_tlc_carrier_names(organization_id)
    cleaned = (current or "").strip()
    if cleaned and cleaned not in carriers:
        carriers.append(cleaned)
        carriers.sort(key=str.casefold)
    return carriers


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

    carriers = get_tlc_carrier_names(active_org.id)

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
        "carrier_statements": TLCCarrierStatement.objects.filter(organization=active_org).prefetch_related("lines")[:50],
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
    from .tlc_models import TLCPaymentTransaction

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
        "carrier_remittances": policy.carrier_remittances.all(),
        "cancellations": policy.cancellations.select_related("recorded_by"),
        "cancellation_reason_choices": TLCPolicyCancellation.CancelReason.choices,
        "documents": policy.documents.select_related("uploaded_by"),
        "timeline": policy.timeline_events.select_related("created_by"),
        "breakdown": getattr(policy, "premium_breakdown", None),
        "endorsement_type_choices": TLCEndorsement.EndorsementType.choices,
        "dmv_service_choices": TLCDMVService.ServiceType.choices,
        "document_type_choices": TLCPolicyDocument.DocumentType.choices,
        "finance_contract": getattr(policy, "finance_contract", None),
        "finance_companies": TLCFinanceCompany.objects.filter(organization=card.organization, is_active=True),
        "carriers": _policy_carrier_choices(card.organization_id, policy.carrier),
        "reminders": policy.installment_reminders.select_related("installment").order_by("scheduled_for")[:50],
        "clients": Client.objects.filter(organization=card.organization).order_by("first_name", "last_name")[:500],
        "vehicles": Vehicle.objects.filter(client__organization=card.organization).select_related("client")[:500],
        "status_choices": TLCPolicy.Status.choices,
        "policy_type_choices": TLCPolicy.PolicyType.choices,
        "policy_vehicles": policy.policy_vehicles.all(),
        "policy_drivers": policy.policy_drivers.all(),
        "receipts": policy.receipts.select_related("transaction", "generated_by").order_by("-generated_at"),
        "payment_transactions": policy.payment_transactions.prefetch_related("splits", "receipts").order_by(
            "-payment_date", "-created_at"
        ),
        "payment_method_choices": TLCPaymentTransaction.PAYMENT_METHODS,
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
            "carrier_remittances",
            "cancellations",
            "documents",
            "timeline_events",
            "policy_vehicles",
            "policy_drivers",
            "receipts",
            "payment_transactions",
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

    carrier_name = request.POST.get("carrier", "").strip()
    if carrier_name:
        ensure_tlc_carrier(card.organization, carrier_name)

    policy = TLCPolicy.objects.create(
        organization=card.organization,
        space=card,
        policy_number=policy_number,
        carrier=carrier_name,
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
def import_tlc_dec_page(request, space_id):
    """Create a new TLC policy by importing an American Transit declaration page PDF."""
    card, is_owner, membership = _resolve_tlc_access(request, space_id=space_id)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "You do not have permission to import TLC policies.")
        return _redirect_tlc(card, tab="policies")

    upload = request.FILES.get("dec_page")
    if not upload:
        messages.error(request, "Please choose a declaration page PDF.")
        return _redirect_tlc(card, tab="policies")
    if not upload.name.lower().endswith(".pdf"):
        messages.error(request, "Declaration page must be a PDF file.")
        return _redirect_tlc(card, tab="policies")

    from .tlc_dec_import import DecPageParseError, apply_parsed_dec_to_policy, parse_tlc_dec_page

    try:
        parsed = parse_tlc_dec_page(upload)
    except DecPageParseError as exc:
        messages.error(request, str(exc))
        return _redirect_tlc(card, tab="policies")

    if TLCPolicy.objects.filter(organization=card.organization, policy_number=parsed.policy_number).exists():
        messages.error(
            request,
            f"Policy {parsed.policy_number} already exists. Open it and use "
            f'"Update from Dec Page" on the policy overview.',
        )
        return _redirect_tlc(card, tab="policies")

    upload.seek(0)
    policy = TLCPolicy.objects.create(
        organization=card.organization,
        space=card,
        policy_number=parsed.policy_number,
        status=TLCPolicy.Status.ACTIVE,
        added_by=request.user,
    )
    apply_parsed_dec_to_policy(policy, parsed, user=request.user, dec_file=upload)

    if parsed.parse_warnings:
        messages.warning(request, "; ".join(parsed.parse_warnings))
    messages.success(
        request,
        f"Imported {policy.policy_number} — {parsed.named_insured} "
        f"({len(parsed.vehicles)} vehicle(s), {len(parsed.payments)} payment(s)).",
    )
    return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)


@login_required
@require_POST
def import_tlc_dec_to_policy(request, policy_id):
    """Refresh an existing TLC policy from a declaration page PDF."""
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    upload = request.FILES.get("dec_page")
    if not upload:
        messages.error(request, "Please choose a declaration page PDF.")
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")
    if not upload.name.lower().endswith(".pdf"):
        messages.error(request, "Declaration page must be a PDF file.")
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")

    from .tlc_dec_import import DecPageParseError, apply_parsed_dec_to_policy, parse_tlc_dec_page

    try:
        parsed = parse_tlc_dec_page(upload)
    except DecPageParseError as exc:
        messages.error(request, str(exc))
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")

    if parsed.policy_number and parsed.policy_number != policy.policy_number:
        messages.error(
            request,
            f"This dec page is for policy {parsed.policy_number}, not {policy.policy_number}.",
        )
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")

    upload.seek(0)
    apply_parsed_dec_to_policy(policy, parsed, user=request.user, dec_file=upload)

    if parsed.parse_warnings:
        messages.warning(request, "; ".join(parsed.parse_warnings))
    messages.success(request, "Policy updated from declaration page.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")


@login_required
@require_POST
def add_tlc_installment(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect("tlc-policy-detail", space_id=card.id, policy_id=policy.id)

    installment_number = int(request.POST.get("installment_number") or 1)
    gross = _parse_decimal(request.POST.get("gross_amount") or request.POST.get("amount"))
    per_fee = _parse_decimal(request.POST.get("installment_fee"))
    try:
        per_fee = per_fee or policy.premium_breakdown.installment_fee
    except TLCPremiumBreakdown.DoesNotExist:
        pass
    notes = request.POST.get("notes", "").strip()
    apply_fee = "down payment" not in notes.lower() and "deposit" not in notes.lower()
    row = build_installment_row(policy, gross, installment_fee=per_fee, apply_fee=apply_fee)
    balance = _parse_decimal(request.POST.get("balance"), default=row["balance"])

    TLCInstallment.objects.update_or_create(
        policy=policy,
        installment_number=installment_number,
        defaults={
            "due_date": _parse_date(request.POST.get("due_date")) or policy.effective_date,
            "amount": row["amount"],
            "installment_fee": row["installment_fee"],
            "commission_amount": row["commission_amount"],
            "late_fee": _parse_decimal(request.POST.get("late_fee")),
            "nsf_fee": _parse_decimal(request.POST.get("nsf_fee")),
            "was_reinstated": request.POST.get("was_reinstated") == "on",
            "balance": balance,
            "notes": notes,
        },
    )
    from .tlc_accounting import sync_installment_accounting

    sync_installment_accounting(policy)
    _record_timeline(
        policy,
        TLCPolicyTimelineEvent.EventType.INSTALLMENT,
        f"Installment #{installment_number}",
        event_date=_parse_date(request.POST.get("due_date")),
        user=request.user,
    )
    messages.success(request, "Installment saved. Use Collect Payment to record payment methods and generate a receipt.")
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
        dmv_document_number=request.POST.get("dmv_document_number", "").strip(),
        notes=request.POST.get("notes", "").strip(),
    )
    from .tlc_accounting import apply_reinstatement_accounting

    apply_reinstatement_accounting(policy)
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

    from .tlc_accounting import (
        apply_endorsement_accounting,
        format_endorsement_timeline_description,
        prepare_endorsement_amounts,
    )

    coverage_date = _parse_date(request.POST.get("coverage_change_date"))
    endorsement_type = request.POST.get("endorsement_type", TLCEndorsement.EndorsementType.OTHER)
    notes = request.POST.get("notes", "").strip()
    new_written_raw = request.POST.get("new_written_premium", "").strip()
    premium_diff_raw = request.POST.get("premium_difference", "").strip()
    amounts = prepare_endorsement_amounts(
        policy,
        new_written_premium=_parse_decimal(new_written_raw) if new_written_raw else None,
        premium_difference=_parse_decimal(premium_diff_raw) if premium_diff_raw else None,
        endorsement_fee=_parse_decimal(request.POST.get("endorsement_fee")),
        commission_difference=_parse_decimal(request.POST.get("commission_difference")),
    )
    if not new_written_raw and not premium_diff_raw:
        messages.error(
            request,
            "Enter the new written premium after this endorsement (or a premium adjustment).",
        )
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=endorsements")

    TLCEndorsement.objects.create(
        policy=policy,
        endorsement_type=endorsement_type,
        premium_difference=amounts["premium_difference"],
        written_premium_before=amounts["written_premium_before"],
        written_premium_after=amounts["written_premium_after"],
        endorsement_fee=amounts["endorsement_fee"],
        commission_difference=amounts["commission_difference"],
        coverage_change_date=coverage_date,
        processed_by=request.user,
        notes=notes,
    )
    apply_endorsement_accounting(policy)
    type_label = dict(TLCEndorsement.EndorsementType.choices).get(endorsement_type, endorsement_type)
    diff = amounts["premium_difference"]
    direction = "increased" if diff > 0 else "decreased" if diff < 0 else "unchanged"
    _record_timeline(
        policy,
        TLCPolicyTimelineEvent.EventType.ENDORSEMENT,
        f"{type_label}: written premium {direction} to ${amounts['written_premium_after']:,.2f}",
        event_date=coverage_date,
        user=request.user,
        description=format_endorsement_timeline_description(amounts, notes=notes),
    )
    messages.success(request, "Endorsement saved.")
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=endorsements")


@login_required
@require_POST
def record_tlc_cancellation(request, policy_id):
    policy = get_object_or_404(TLCPolicy, id=policy_id)
    card, is_owner, membership = _resolve_tlc_access(request, card=policy.space)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        messages.error(request, "Permission denied.")
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")

    cancellation_date = _parse_date(request.POST.get("cancellation_date"))
    reason = request.POST.get("cancellation_reason", "").strip()
    if not cancellation_date or not reason:
        messages.error(request, "Cancellation date and reason are required.")
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")

    custom_note = request.POST.get("custom_note", "").strip()
    if reason == TLCPolicyCancellation.CancelReason.CUSTOM and not custom_note:
        messages.error(request, "Please enter a custom cancellation note.")
        return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")

    from .tlc_accounting import (
        apply_cancellation_accounting,
        calculate_tlc_return_premium,
        calculate_tlc_unearned_commission,
        policy_commission_earned,
    )

    unearned_commission = calculate_tlc_unearned_commission(policy, cancellation_date)
    return_premium = calculate_tlc_return_premium(policy, cancellation_date)
    earned_commission_at_cancel = policy_commission_earned(policy)

    TLCPolicyCancellation.objects.create(
        policy=policy,
        cancellation_date=cancellation_date,
        reason=reason,
        custom_note=custom_note,
        successor_carrier=request.POST.get("successor_carrier", "").strip(),
        successor_broker=request.POST.get("successor_broker", "").strip(),
        successor_policy_number=request.POST.get("successor_policy_number", "").strip(),
        successor_effective_date=_parse_date(request.POST.get("successor_effective_date")),
        recorded_by=request.user,
        unearned_commission=unearned_commission,
        return_premium=return_premium,
        earned_commission_at_cancel=earned_commission_at_cancel,
    )
    apply_cancellation_accounting(policy, cancellation_date)
    _record_timeline(
        policy,
        TLCPolicyTimelineEvent.EventType.CANCELLATION,
        f"Policy cancelled — {dict(TLCPolicyCancellation.CancelReason.choices).get(reason, reason)}",
        event_date=cancellation_date,
        user=request.user,
        description=custom_note,
    )
    messages.success(request, "Cancellation recorded on policy profile.")
    if unearned_commission > 0:
        messages.info(
            request,
            f"Unearned commission chargeback recorded: ${_money_label(unearned_commission)}.",
        )
    return redirect(f"{_tlc_url(card, policy_id=policy.id)}?tab=overview")


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
    from .tlc_edit_views import _sync_policy_remitted_total

    _sync_policy_remitted_total(policy)
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
def add_tlc_carrier(request, space_id):
    card, is_owner, membership = _resolve_tlc_access(request, space_id=space_id)
    if not (is_owner or (membership and membership.can_deal_with_tlc)):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)
        messages.error(request, "Permission denied.")
        return _redirect_tlc(card, tab="policies")

    name = request.POST.get("name", "").strip()
    if not name:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Carrier name is required."}, status=400)
        messages.error(request, "Carrier name is required.")
        return _redirect_tlc(card, tab="policies")

    ensure_tlc_carrier(card.organization, name)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "name": name})
    messages.success(request, f"Carrier “{name}” saved.")
    return _redirect_tlc(card, tab="policies")


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
