"""Insurance producers: staff management pages and the producer's own read-only portal."""

from __future__ import annotations

import secrets
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .http import deny_access
from .insurance_permissions import can_manage_insurance_finance, membership_for_org
from .insurance_producers import (
    ZERO,
    build_policy_ledger,
    money,
    settlement_plan,
    summarize_producer,
)
from .models import (
    InsurancePolicy,
    InsuranceProducer,
    InsuranceProducerPayout,
    OrganizationMembership,
    Space,
)
from .views import _get_user_organizations

User = get_user_model()


# ── helpers ──────────────────────────────────────────────────────────────────


def _finance_org_or_deny(request, organization):
    if not _get_user_organizations(request).filter(id=organization.id).exists():
        deny_access("Access denied.")
    membership = membership_for_org(request.user, organization)
    if not can_manage_insurance_finance(request.user, organization, membership=membership):
        deny_access("Only finance managers can manage producers.")


def _insurance_space_url(org, tab="producers"):
    space = Space.objects.filter(organization=org, key="insurance").first()
    if not space:
        return reverse("spaces-home")
    return f"{reverse('inventory-detail', kwargs={'inventory_id': space.id})}?tab={tab}"


def _producer_for_staff(request, producer_id):
    producer = get_object_or_404(InsuranceProducer.objects.select_related("organization", "user"), id=producer_id)
    _finance_org_or_deny(request, producer.organization)
    return producer


def _decimal(raw, *, field, minimum=None, maximum=None) -> Decimal:
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a number.") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field} must be at most {maximum}.")
    return value


def _paid_on(raw):
    if not (raw or "").strip():
        return timezone.localdate()
    try:
        value = parse_date(raw.strip())
    except ValueError:
        value = None
    if value is None:
        raise ValueError("Enter a valid payment date.")
    return value


def _apply_producer_fields(producer, post) -> None:
    name = (post.get("name") or "").strip()
    if not name:
        raise ValueError("Producer name is required.")
    producer.name = name[:160]
    producer.email = (post.get("email") or "").strip()[:254]
    producer.phone = (post.get("phone") or "").strip()[:40]
    producer.license_number = (post.get("license_number") or "").strip()[:80]
    producer.default_rate = _decimal(post.get("default_rate") or "0", field="Default %", minimum=0, maximum=100)
    basis = post.get("rate_basis")
    producer.rate_basis = basis if basis in InsuranceProducer.RateBasis.values else InsuranceProducer.RateBasis.COMMISSION
    payout = post.get("default_payout")
    producer.default_payout = payout if payout in InsuranceProducer.PayoutMode.values else InsuranceProducer.PayoutMode.ONCE
    producer.notes = (post.get("notes") or "").strip()


def _is_staff_login(user) -> bool:
    if user is None:
        return False
    return bool(
        user.is_staff
        or user.is_superuser
        or OrganizationMembership.objects.filter(user_id=user.id).exists()
    )


def _set_login(producer, username: str, password: str) -> None:
    username = (username or "").strip()
    if not username:
        raise ValueError("Username is required for the producer login.")
    if len(username) > 150:
        raise ValueError("Username is too long.")
    try:
        UnicodeUsernameValidator()(username)
    except ValidationError as exc:
        raise ValueError("Username may only contain letters, numbers and @ . + - _") from exc
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")
    clash = User.objects.filter(username__iexact=username)
    if producer.user_id:
        clash = clash.exclude(id=producer.user_id)
    if clash.exists():
        raise ValueError("That username is already taken.")
    user = producer.user
    if user is None:
        user = User(username=username)
    else:
        user.username = username
    parts = producer.name.split(" ", 1)
    user.first_name = parts[0][:150]
    user.last_name = (parts[1] if len(parts) > 1 else "")[:150]
    user.email = producer.email
    user.is_active = producer.is_active
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ValueError(" ".join(exc.messages)) from exc
    user.set_password(password)
    user.save()
    if producer.user_id != user.id:
        producer.user = user
        producer.save(update_fields=["user", "updated_at"])


def build_producers_tab_context(org) -> dict:
    producers = list(
        InsuranceProducer.objects.filter(organization=org)
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "policies",
                queryset=InsurancePolicy.objects.select_related("client", "insurance_company")
                .prefetch_related("producer_payouts")
                .order_by("-start_date", "-id"),
            )
        )
    )
    summaries = [summarize_producer(p, policies=p.policies.all()) for p in producers]
    totals = {
        "count": len([s for s in summaries if s.producer.is_active]),
        "total_commission": money(sum((s.total_commission for s in summaries), ZERO)),
        "paid": money(sum((s.paid for s in summaries), ZERO)),
        "due_now": money(sum((s.due_now for s in summaries), ZERO)),
        "deductions": money(sum((s.deductions for s in summaries), ZERO)),
        "net_payable": money(sum((s.net_payable for s in summaries), ZERO)),
        "upcoming": money(sum((s.upcoming for s in summaries), ZERO)),
    }
    return {"producer_summaries": summaries, "producer_totals": totals}


# ── staff: producer CRUD ────────────────────────────────────────────────────


@login_required
@require_POST
def add_insurance_producer(request):
    org = get_object_or_404(_get_user_organizations(request), id=request.POST.get("organization"))
    _finance_org_or_deny(request, org)
    producer = InsuranceProducer(organization=org)
    try:
        _apply_producer_fields(producer, request.POST)
        with transaction.atomic():
            producer.save()
            if (request.POST.get("create_login") or "") in {"1", "on"}:
                _set_login(producer, request.POST.get("username"), request.POST.get("password"))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(_insurance_space_url(org))
    except IntegrityError:
        messages.error(request, "A producer with that name already exists.")
        return redirect(_insurance_space_url(org))
    messages.success(request, f"Producer {producer.name} added.")
    return redirect("insurance-producer-detail", producer_id=producer.id)


@login_required
@require_POST
def edit_insurance_producer(request, producer_id):
    producer = _producer_for_staff(request, producer_id)
    try:
        _apply_producer_fields(producer, request.POST)
        producer.is_active = (request.POST.get("is_active") or "") in {"1", "on"}
        with transaction.atomic():
            producer.save()
            if (
                producer.user_id
                and producer.user.is_active != producer.is_active
                and not _is_staff_login(producer.user)
            ):
                producer.user.is_active = producer.is_active
                producer.user.save(update_fields=["is_active"])
    except ValueError as exc:
        messages.error(request, str(exc))
    except IntegrityError:
        messages.error(request, "A producer with that name already exists.")
    else:
        messages.success(request, "Producer updated. Existing policies keep their own rate.")
    return redirect("insurance-producer-detail", producer_id=producer.id)


@login_required
@require_POST
def set_insurance_producer_login(request, producer_id):
    producer = _producer_for_staff(request, producer_id)
    if _is_staff_login(producer.user):
        messages.error(request, "This login belongs to a staff member and can't be changed here.")
        return redirect("insurance-producer-detail", producer_id=producer.id)
    if (request.POST.get("action") or "") == "disable":
        if producer.user_id:
            producer.user.is_active = False
            producer.user.save(update_fields=["is_active"])
        messages.success(request, "Portal login turned off.")
        return redirect("insurance-producer-detail", producer_id=producer.id)
    generate = (request.POST.get("generate") or "") == "1"
    password = secrets.token_urlsafe(9) if generate else (request.POST.get("password") or "")
    try:
        _set_login(producer, request.POST.get("username"), password)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("insurance-producer-detail", producer_id=producer.id)
    if generate:
        request.session["producer_new_password"] = {"producer": producer.id, "password": password}
    messages.success(request, "Portal login saved. Share the username and password with the producer.")
    return redirect("insurance-producer-detail", producer_id=producer.id)


# ── staff: payouts ──────────────────────────────────────────────────────────


@login_required
@require_POST
def record_insurance_producer_payout(request, producer_id):
    producer = _producer_for_staff(request, producer_id)
    policy = InsurancePolicy.objects.filter(
        id=request.POST.get("policy"), producer=producer, organization=producer.organization
    ).first()
    if policy is None:
        messages.error(request, "Choose one of this producer's policies.")
        return redirect("insurance-producer-detail", producer_id=producer.id)
    try:
        amount = money(_decimal(request.POST.get("amount") or "", field="Amount", minimum=-1_000_000, maximum=1_000_000))
        paid_on = _paid_on(request.POST.get("paid_on"))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("insurance-producer-detail", producer_id=producer.id)
    if amount == 0:
        messages.error(request, "Amount can't be zero.")
        return redirect("insurance-producer-detail", producer_id=producer.id)
    method = request.POST.get("method")
    if method not in InsuranceProducerPayout.Method.values:
        method = InsuranceProducerPayout.Method.CASH
    InsuranceProducerPayout.objects.create(
        organization=producer.organization,
        producer=producer,
        policy=policy,
        kind=(
            InsuranceProducerPayout.Kind.PAYMENT
            if amount > 0
            else InsuranceProducerPayout.Kind.DEDUCTION
        ),
        amount=amount,
        paid_on=paid_on,
        method=method,
        note=(request.POST.get("note") or "").strip()[:255],
        recorded_by=request.user,
    )
    messages.success(request, f"Recorded ${amount} for policy {policy.policy_number}.")
    return redirect("insurance-producer-detail", producer_id=producer.id)


@login_required
@require_POST
def settle_insurance_producer(request, producer_id):
    """Pay everything due now, minus deductions from cancelled policies, in one batch."""
    producer = _producer_for_staff(request, producer_id)
    try:
        paid_on = _paid_on(request.POST.get("paid_on"))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("insurance-producer-detail", producer_id=producer.id)
    method = request.POST.get("method")
    if method not in InsuranceProducerPayout.Method.values:
        method = InsuranceProducerPayout.Method.CASH
    batch = f"PAY-{timezone.now():%y%m%d%H%M%S}"
    note = (request.POST.get("note") or "").strip()[:255]
    with transaction.atomic():
        # Lock the producer so a double-submit can't pay the same balance twice.
        InsuranceProducer.objects.select_for_update().filter(id=producer.id).first()
        rows = settlement_plan(summarize_producer(producer))
        if not rows:
            messages.info(request, "Nothing is due for this producer right now.")
            return redirect("insurance-producer-detail", producer_id=producer.id)
        for policy, kind, amount in rows:
            InsuranceProducerPayout.objects.create(
                organization=producer.organization,
                producer=producer,
                policy=policy,
                kind=kind,
                amount=amount,
                paid_on=paid_on,
                method=method if kind == "payment" else InsuranceProducerPayout.Method.OFFSET,
                batch_reference=batch,
                note=note or ("Deducted from this payout" if kind == "deduction" else ""),
                recorded_by=request.user,
            )
    net = money(sum((amt for _, _, amt in rows), ZERO))
    messages.success(request, f"Paid {producer.name} ${net} (batch {batch}).")
    return redirect("insurance-producer-detail", producer_id=producer.id)


@login_required
@require_POST
def delete_insurance_producer_payout(request, payout_id):
    payout = get_object_or_404(InsuranceProducerPayout.objects.select_related("producer"), id=payout_id)
    _finance_org_or_deny(request, payout.organization)
    producer_id = payout.producer_id
    payout.delete()
    messages.success(request, "Payout removed.")
    return redirect("insurance-producer-detail", producer_id=producer_id)


# ── staff: producer profile ─────────────────────────────────────────────────


def _producer_page_context(producer, *, staff: bool) -> dict:
    policies = (
        InsurancePolicy.objects.filter(producer=producer)
        .select_related("client", "insurance_company")
        .prefetch_related("producer_payouts", "premium_changes")
        .order_by("-start_date", "-id")
    )
    summary = summarize_producer(producer, policies=policies)
    payouts = (
        InsuranceProducerPayout.objects.filter(producer=producer)
        .select_related("policy", "policy__client", "recorded_by")
        .order_by("-paid_on", "-id")
    )
    deduction_ledgers = [lg for lg in summary.ledgers if lg.owes_back > 0]
    return {
        "producer": producer,
        "summary": summary,
        "ledgers": summary.ledgers,
        "deduction_ledgers": deduction_ledgers,
        "payouts": payouts[:200],
        "is_staff_view": staff,
        "settle_rows": settlement_plan(summary) if staff else [],
    }


@never_cache
@login_required
def insurance_producer_detail(request, producer_id):
    producer = _producer_for_staff(request, producer_id)
    context = _producer_page_context(producer, staff=True)
    new_pw = request.session.pop("producer_new_password", None)
    if new_pw and new_pw.get("producer") == producer.id:
        context["new_password"] = new_pw.get("password")
    context.update(
        {
            "back_url": _insurance_space_url(producer.organization),
            "payout_methods": InsuranceProducerPayout.Method.choices,
            "today": timezone.localdate(),
        }
    )
    return render(request, "core/insurance_producer_detail.html", context)


# ── producer portal ─────────────────────────────────────────────────────────


@never_cache
@login_required
def producer_portal(request):
    producer = InsuranceProducer.objects.select_related("organization").filter(user=request.user).first()
    if producer is None:
        return redirect("dashboard")
    if not producer.is_active:
        messages.error(request, "Your producer account is paused. Please contact the agency.")
    context = _producer_page_context(producer, staff=False)
    context["password_form"] = PasswordChangeForm(request.user)
    context["today"] = timezone.localdate()
    return render(request, "core/producer_portal.html", context)


@login_required
@require_POST
def producer_portal_password(request):
    producer = InsuranceProducer.objects.filter(user=request.user).first()
    if producer is None:
        return redirect("dashboard")
    form = PasswordChangeForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Password updated.")
    else:
        for errors in form.errors.values():
            for err in errors:
                messages.error(request, err)
    return redirect("producer-portal")


def policy_producer_snapshot(policy):
    """Small producer/commission status used on client profile and policy pages."""
    if not policy.producer_id:
        return None
    return build_policy_ledger(policy)
