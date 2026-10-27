"""Producer commission math: totals, monthly accrual, payouts, and cancellation deductions."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
EARNING_STAGES = frozenset({"bound", "endorsement"})
EARNING_STATUSES = frozenset({"active", "inactive"})


def _d(value) -> Decimal:
    if value is None or value == "":
        return ZERO
    return Decimal(str(value))


def money(value) -> Decimal:
    return _d(value).quantize(CENT, rounding=ROUND_HALF_UP)


def producer_base_amount(policy, basis: str | None = None) -> Decimal:
    """What the producer's percentage applies to: our commission or the premium."""
    basis = basis or policy.producer_rate_basis or "commission"
    if basis == "premium":
        return _d(policy.premium)
    paid = getattr(policy, "commission_paid", None)
    if paid is not None:
        return _d(paid)
    if policy.commission_amount is not None:
        return _d(policy.commission_amount)
    if policy.commission_rate is None:
        return ZERO
    return _d(policy.premium) * _d(policy.commission_rate) / Decimal("100")


def producer_total_for_policy(policy) -> Decimal | None:
    """Full-term producer commission at the policy's current premium (None without a producer)."""
    if not policy.producer_id or policy.producer_rate is None:
        return None
    return money(producer_base_amount(policy) * _d(policy.producer_rate) / Decimal("100"))


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def months_elapsed(start: date | None, as_of: date, term: int) -> int:
    """Monthly installments earned by ``as_of``; the first month counts on the start date."""
    if not start or as_of < start:
        return 0
    months = (as_of.year - start.year) * 12 + (as_of.month - start.month)
    if as_of >= add_months(start, months):
        months += 1
    return max(0, min(months, term))


@dataclass
class PolicyProducerLedger:
    policy: object
    total: Decimal = ZERO
    effective_total: Decimal = ZERO
    per_month: Decimal = ZERO
    term_months: int = 0
    months_earned: int = 0
    earned_to_date: Decimal = ZERO
    paid: Decimal = ZERO
    due_now: Decimal = ZERO
    owes_back: Decimal = ZERO
    remaining: Decimal = ZERO
    upcoming: Decimal = ZERO
    cancelled_reduction: Decimal = ZERO
    next_payment_date: date | None = None
    is_monthly: bool = False
    earns: bool = False
    payouts: list = field(default_factory=list)

    @property
    def status_key(self) -> str:
        if not self.earns:
            return "not_bound"
        if self.owes_back > 0:
            return "owes_back"
        if self.total > 0 and self.remaining <= 0 and self.due_now <= 0:
            return "paid"
        if self.due_now > 0:
            return "due"
        if self.paid > 0:
            return "partial"
        return "upcoming"

    @property
    def status_label(self) -> str:
        return {
            "not_bound": "Not bound yet",
            "owes_back": "Deduction",
            "paid": "Paid in full",
            "due": "Due now",
            "partial": "On schedule",
            "upcoming": "Upcoming",
        }[self.status_key]

    @property
    def paid_percent(self) -> int:
        if self.effective_total <= 0:
            return 100 if self.paid > 0 else 0
        pct = int((self.paid / self.effective_total) * 100)
        return max(0, min(pct, 100))


def build_policy_ledger(policy, payouts=None, *, today: date | None = None) -> PolicyProducerLedger:
    from .insurance_commissions import calculate_unearned_commission

    today = today or timezone.localdate()
    if payouts is None:
        payouts = (
            [p for p in policy.producer_payouts.all() if p.producer_id == policy.producer_id]
            if policy.producer_id
            else []
        )
    ledger = PolicyProducerLedger(policy=policy, payouts=list(payouts))
    ledger.paid = money(sum((_d(p.amount) for p in payouts), ZERO))
    ledger.total = money(policy.producer_commission_amount)
    ledger.is_monthly = policy.producer_payout == "monthly"
    ledger.earns = policy.stage in EARNING_STAGES and policy.status in EARNING_STATUSES

    if not ledger.earns:
        ledger.owes_back = max(ledger.paid, ZERO)
        return ledger

    cutoff = today
    effective_total = ledger.total
    if policy.status == "inactive":
        unearned = calculate_unearned_commission(
            ledger.total,
            policy.start_date,
            policy.end_date,
            policy.inactive_date,
            insurance_period_months=policy.insurance_period_months,
        )
        effective_total = money(ledger.total - unearned)
        ledger.cancelled_reduction = money(unearned)
        if policy.inactive_date:
            cutoff = min(today, policy.inactive_date)
    ledger.effective_total = effective_total

    if ledger.is_monthly:
        term = max(int(policy.insurance_period_months or 1), 1)
        ledger.term_months = term
        ledger.per_month = money(ledger.total / term)
        start = policy.start_date or policy.bound_date
        ledger.months_earned = months_elapsed(start, cutoff, term)
        if ledger.months_earned >= term:
            earned = effective_total
        else:
            earned = min(effective_total, money(ledger.total * ledger.months_earned / term))
        if start and ledger.months_earned < term and policy.status == "active":
            ledger.next_payment_date = add_months(start, ledger.months_earned)
    else:
        earned = effective_total
    ledger.earned_to_date = money(earned)

    balance = ledger.earned_to_date - ledger.paid
    ledger.due_now = money(max(balance, ZERO))
    ledger.owes_back = money(max(-balance, ZERO))
    ledger.remaining = money(max(effective_total - ledger.paid, ZERO))
    ledger.upcoming = money(max(ledger.remaining - ledger.due_now, ZERO))
    return ledger


@dataclass
class ProducerSummary:
    producer: object
    ledgers: list
    total_commission: Decimal = ZERO
    paid: Decimal = ZERO
    due_now: Decimal = ZERO
    deductions: Decimal = ZERO
    upcoming: Decimal = ZERO
    net_payable: Decimal = ZERO
    carried_deduction: Decimal = ZERO
    bound_count: int = 0
    active_count: int = 0
    inactive_count: int = 0
    carrier_received_count: int = 0

    @property
    def paid_percent(self) -> int:
        if self.total_commission <= 0:
            return 0
        return max(0, min(int(self.paid / self.total_commission * 100), 100))


def summarize_producer(producer, *, today: date | None = None, policies=None) -> ProducerSummary:
    from .models import InsurancePolicy

    if policies is None:
        policies = (
            InsurancePolicy.objects.filter(producer=producer)
            .select_related("client", "insurance_company")
            .prefetch_related("producer_payouts")
            .order_by("-start_date", "-id")
        )
    ledgers = []
    for policy in policies:
        payouts = [p for p in policy.producer_payouts.all() if p.producer_id == producer.id]
        ledgers.append(build_policy_ledger(policy, payouts, today=today))

    s = ProducerSummary(producer=producer, ledgers=ledgers)
    for lg in ledgers:
        if not lg.earns:
            continue
        s.bound_count += 1
        if lg.policy.status == "active":
            s.active_count += 1
        else:
            s.inactive_count += 1
        if lg.policy.commission_received:
            s.carrier_received_count += 1
        s.total_commission += lg.effective_total
        s.paid += lg.paid
        s.due_now += lg.due_now
        s.deductions += lg.owes_back
        s.upcoming += lg.upcoming
    for lg in ledgers:
        if not lg.earns:
            s.deductions += lg.owes_back
    s.total_commission = money(s.total_commission)
    s.paid = money(s.paid)
    s.due_now = money(s.due_now)
    s.deductions = money(s.deductions)
    s.upcoming = money(s.upcoming)
    s.net_payable = money(max(s.due_now - s.deductions, ZERO))
    s.carried_deduction = money(max(s.deductions - s.due_now, ZERO))
    return s


class ProducerInputError(ValueError):
    pass


def apply_producer_from_post(policy, post, *, organization, can_edit_rates: bool) -> None:
    """Set producer fields on an unsaved policy from the add/edit policy form."""
    from .models import InsuranceProducer

    if (post.get("has_producer") or "").lower() not in {"1", "on", "true", "yes"}:
        policy.producer = None
        policy.producer_rate = None
        policy.producer_rate_basis = ""
        policy.producer_payout = ""
        return

    raw_id = (post.get("producer") or "").strip()
    if not raw_id.isdigit():
        raise ProducerInputError("Choose the producer for this policy.")
    producer = (
        InsuranceProducer.objects.filter(organization=organization, id=int(raw_id))
        .filter(_active_or_current_q(policy))
        .first()
    )
    if producer is None:
        raise ProducerInputError("That producer is not available.")

    changed = producer.id != policy.producer_id
    policy.producer = producer
    if changed or policy.producer_rate is None:
        policy.producer_rate = producer.default_rate
        policy.producer_rate_basis = producer.rate_basis
        policy.producer_payout = producer.default_payout

    if can_edit_rates:
        raw_rate = (post.get("producer_rate") or "").strip()
        if raw_rate:
            try:
                rate = Decimal(raw_rate)
            except Exception as exc:
                raise ProducerInputError("Producer rate must be a number.") from exc
            if rate < 0 or rate > 100:
                raise ProducerInputError("Producer rate must be between 0 and 100.")
            policy.producer_rate = rate
        payout = (post.get("producer_payout") or "").strip()
        if payout in {"once", "monthly"}:
            policy.producer_payout = payout
    if not policy.producer_rate_basis:
        policy.producer_rate_basis = producer.rate_basis


def _active_or_current_q(policy):
    from django.db.models import Q

    q = Q(is_active=True)
    if policy.producer_id:
        q |= Q(id=policy.producer_id)
    return q


def record_premium_change(policy, old_premium, *, user=None, note: str = "") -> None:
    from .models import InsurancePolicyPremiumChange

    old = money(old_premium)
    new = money(policy.premium)
    if old == new:
        return
    InsurancePolicyPremiumChange.objects.create(
        policy=policy,
        old_premium=old,
        new_premium=new,
        effective_date=timezone.localdate(),
        note=note,
        changed_by=user,
    )


def settlement_plan(summary: ProducerSummary) -> list[tuple[object, str, Decimal]]:
    """Rows to record when paying a producer everything due, net of cancellation deductions."""
    rows = []
    for lg in summary.ledgers:
        if lg.due_now > 0:
            rows.append((lg.policy, "payment", lg.due_now))
    available = sum((amt for _, _, amt in rows), ZERO)

    def _deduction_order(lg):
        p = lg.policy
        return (p.inactive_date is None, p.inactive_date or date.min, p.id)

    for lg in sorted((l for l in summary.ledgers if l.owes_back > 0), key=_deduction_order):
        if available <= 0:
            break
        apply = min(lg.owes_back, available)
        rows.append((lg.policy, "deduction", -apply))
        available -= apply
    return rows
