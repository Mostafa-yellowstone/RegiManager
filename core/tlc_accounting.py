"""Central TLC policy accounting — links installments, fees, endorsements, and lifecycle events."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .insurance_commissions import calculate_unearned_commission
from .tlc_models import TLCPolicy, TLCPolicyCancellation, TLCInstallment

ZERO = Decimal("0.00")


def _d(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))


def policy_base_written_premium(policy: TLCPolicy) -> Decimal:
    breakdown = getattr(policy, "premium_breakdown", None)
    if breakdown is None:
        try:
            breakdown = policy.premium_breakdown
        except Exception:
            breakdown = None
    return _d(breakdown.total_written_premium if breakdown else ZERO)


def policy_written_premium(policy: TLCPolicy) -> Decimal:
    """Original written premium plus endorsement premium adjustments."""
    return (policy_base_written_premium(policy) + _d(policy.endorsement_balance)).quantize(Decimal("0.01"))


def endorsement_commission_total(policy: TLCPolicy) -> Decimal:
    total = ZERO
    rate = _d(policy.commission_rate)
    for row in policy.endorsements.all():
        delta = _d(row.commission_difference)
        if delta == ZERO and rate > ZERO:
            delta = (_d(row.premium_difference) * rate / Decimal("100")).quantize(Decimal("0.01"))
        total += delta
    return total.quantize(Decimal("0.01"))


def policy_expected_commission(policy: TLCPolicy) -> Decimal:
    """Total carrier commission expected on current written premium."""
    written = policy_written_premium(policy)
    rate = _d(policy.commission_rate)
    if rate > ZERO and written > ZERO:
        return (written * rate / Decimal("100")).quantize(Decimal("0.01"))
    return _d(policy.carrier_commission_amount)


def installment_commission_earned(policy: TLCPolicy) -> Decimal:
    return _d(
        policy.installments.filter(is_paid=True).aggregate(total=Sum("commission_amount"))["total"]
    )


def policy_commission_earned(policy: TLCPolicy) -> Decimal:
    """Commission earned from paid installments plus recorded endorsement commission."""
    return (installment_commission_earned(policy) + endorsement_commission_total(policy)).quantize(
        Decimal("0.01")
    )


def policy_net_premium_collected(policy: TLCPolicy) -> Decimal:
    """Net premium portion collected (after installment fees are deducted from gross)."""
    return _d(policy.installments.filter(is_paid=True).aggregate(total=Sum("amount"))["total"])


def policy_gross_collected(policy: TLCPolicy) -> Decimal:
    total = ZERO
    for row in policy.installments.filter(is_paid=True):
        total += _d(row.total_due)
    return total.quantize(Decimal("0.01"))


def policy_installment_fees_collected(policy: TLCPolicy) -> Decimal:
    return _d(
        policy.installments.filter(is_paid=True).aggregate(total=Sum("installment_fee"))["total"]
    )


def calculate_tlc_return_premium(
    policy: TLCPolicy,
    inactive_date: date | None,
) -> Decimal:
    written = policy_written_premium(policy)
    if written <= ZERO or not inactive_date:
        return ZERO
    return calculate_unearned_commission(
        written,
        policy.effective_date,
        policy.expiration_date,
        inactive_date,
    )


def calculate_tlc_unearned_commission(
    policy: TLCPolicy,
    inactive_date: date | None,
) -> Decimal:
    expected = policy_expected_commission(policy)
    if expected <= ZERO or not inactive_date:
        return ZERO
    return calculate_unearned_commission(
        expected,
        policy.effective_date,
        policy.expiration_date,
        inactive_date,
    )


def written_premium_before_endorsement(
    policy: TLCPolicy,
    *,
    exclude_endorsement_id: int | None = None,
) -> Decimal:
    """Written premium before applying a new or edited endorsement."""
    total = policy_base_written_premium(policy)
    qs = policy.endorsements.all()
    if exclude_endorsement_id:
        qs = qs.exclude(pk=exclude_endorsement_id)
    prior = _d(qs.aggregate(total=Sum("premium_difference"))["total"])
    return (total + prior).quantize(Decimal("0.01"))


def prepare_endorsement_amounts(
    policy: TLCPolicy,
    *,
    new_written_premium: Decimal | None = None,
    premium_difference: Decimal | None = None,
    endorsement_fee: Decimal | None = None,
    commission_difference: Decimal | None = None,
    exclude_endorsement_id: int | None = None,
) -> dict[str, Decimal]:
    """Resolve before/after written premium and net adjustment from user input."""
    before = written_premium_before_endorsement(
        policy, exclude_endorsement_id=exclude_endorsement_id
    )
    fee = _d(endorsement_fee)
    new_written = _d(new_written_premium)

    if new_written > ZERO:
        after = new_written
        diff = (after - before).quantize(Decimal("0.01"))
    elif premium_difference is not None:
        diff = _d(premium_difference)
        after = (before + diff).quantize(Decimal("0.01"))
    else:
        diff = ZERO
        after = before

    commission_diff = _d(commission_difference)
    rate = _d(policy.commission_rate)
    if commission_diff == ZERO and rate > ZERO and diff != ZERO:
        commission_diff = (diff * rate / Decimal("100")).quantize(Decimal("0.01"))

    return {
        "written_premium_before": before,
        "written_premium_after": after,
        "premium_difference": diff,
        "endorsement_fee": fee,
        "commission_difference": commission_diff,
    }


def format_endorsement_timeline_description(
    amounts: dict[str, Decimal],
    *,
    notes: str = "",
) -> str:
    before = amounts["written_premium_before"]
    after = amounts["written_premium_after"]
    diff = amounts["premium_difference"]
    fee = amounts["endorsement_fee"]
    lines = [
        f"Written premium before: ${before:,.2f}",
        f"Written premium after endorsement: ${after:,.2f}",
    ]
    if diff < ZERO:
        lines.append(
            f"Premium decreased by ${abs(diff):,.2f} — endorsement reduced the policy total."
        )
    elif diff > ZERO:
        lines.append(
            f"Premium increased by ${diff:,.2f} — endorsement raised the policy total."
        )
    else:
        lines.append("No net written premium change.")
    if fee > ZERO:
        lines.append(f"Endorsement fee: ${fee:,.2f}.")
    if notes.strip():
        lines.append(notes.strip())
    return "\n".join(lines)


def sync_endorsement_balance(policy: TLCPolicy) -> Decimal:
    total = _d(
        policy.endorsements.aggregate(total=Sum("premium_difference"))["total"]
    )
    policy.endorsement_balance = total
    return total


def sync_policy_commission_amount(policy: TLCPolicy) -> Decimal:
    expected = policy_expected_commission(policy)
    policy.carrier_commission_amount = expected
    return expected


def sync_policy_collections(policy: TLCPolicy) -> Decimal:
    """Roll up customer collections from paid installments."""
    collected = policy_gross_collected(policy)
    policy.amount_collected_from_client = collected
    return collected


def void_unpaid_installments_after(policy: TLCPolicy, cutoff_date: date) -> int:
    """Zero out remaining unpaid installments when a policy is cancelled or suspended."""
    updated = 0
    for row in policy.installments.filter(is_paid=False):
        row.balance = ZERO
        suffix = "Voided — policy no longer in force"
        if suffix not in row.notes:
            row.notes = f"{row.notes} — {suffix}".strip(" —")
        row.save(update_fields=["balance", "notes"])
        updated += 1
    return updated


def apply_endorsement_accounting(policy: TLCPolicy, *, save: bool = True) -> None:
    sync_endorsement_balance(policy)
    sync_policy_commission_amount(policy)
    try:
        breakdown = policy.premium_breakdown
    except Exception:
        breakdown = None
    if breakdown is not None:
        breakdown.endorsement_charges = _d(
            policy.endorsements.aggregate(total=Sum("endorsement_fee"))["total"]
        )
        breakdown.save(update_fields=["endorsement_charges"])
    if save:
        policy.save(update_fields=["endorsement_balance", "carrier_commission_amount", "updated_at"])


def apply_cancellation_accounting(
    policy: TLCPolicy,
    cancellation_date: date,
    *,
    status: str = TLCPolicy.Status.CANCELLED,
    save: bool = True,
) -> dict:
    """Compute unearned commission / return premium and update policy totals."""
    unearned_commission = calculate_tlc_unearned_commission(policy, cancellation_date)
    return_premium = calculate_tlc_return_premium(policy, cancellation_date)
    earned_commission = policy_commission_earned(policy)

    policy.commission_chargeback = unearned_commission
    policy.status = status
    void_unpaid_installments_after(policy, cancellation_date)
    sync_policy_collections(policy)

    if save:
        policy.save(
            update_fields=[
                "commission_chargeback",
                "status",
                "amount_collected_from_client",
                "updated_at",
            ]
        )

    return {
        "unearned_commission": unearned_commission,
        "return_premium": return_premium,
        "earned_commission_at_cancel": earned_commission,
    }


def apply_reinstatement_accounting(policy: TLCPolicy, *, save: bool = True) -> None:
    policy.status = TLCPolicy.Status.ACTIVE
    sync_policy_collections(policy)
    if save:
        policy.save(update_fields=["status", "amount_collected_from_client", "updated_at"])


def sync_installment_accounting(policy: TLCPolicy, *, save: bool = True) -> None:
    """Called after any installment is created, updated, or marked paid."""
    sync_policy_collections(policy)
    if save:
        policy.save(update_fields=["amount_collected_from_client", "updated_at"])


def latest_cancellation(policy: TLCPolicy) -> TLCPolicyCancellation | None:
    return policy.cancellations.order_by("-cancellation_date", "-created_at").first()


def policy_inactive_date(policy: TLCPolicy) -> date | None:
    if policy.status in (TLCPolicy.Status.CANCELLED, TLCPolicy.Status.SUSPENDED):
        row = latest_cancellation(policy)
        if row:
            return row.cancellation_date
    return None


def build_accounting_snapshot(policy: TLCPolicy, *, today: date | None = None) -> dict:
    """Authoritative numbers for profitability and UI."""
    today = today or timezone.localdate()
    written = policy_written_premium(policy)
    base_written = policy_base_written_premium(policy)
    endorsement_premium = _d(policy.endorsement_balance)
    expected_commission = policy_expected_commission(policy)
    earned_commission = policy_commission_earned(policy)
    inactive = policy_inactive_date(policy)
    unearned_commission = (
        calculate_tlc_unearned_commission(policy, inactive) if inactive else ZERO
    )
    return_premium = calculate_tlc_return_premium(policy, inactive) if inactive else ZERO
    carrier_premium = max(written - return_premium, ZERO)
    chargeback = _d(policy.commission_chargeback)
    if inactive and chargeback == ZERO:
        chargeback = unearned_commission

    return {
        "today": today,
        "base_written_premium": base_written,
        "endorsement_premium_adjustments": endorsement_premium,
        "current_written_premium": written,
        "carrier_premium_due": carrier_premium,
        "return_premium": return_premium,
        "expected_commission": expected_commission,
        "earned_commission": earned_commission,
        "unearned_commission": unearned_commission,
        "commission_chargeback": chargeback,
        "pending_commission": max(expected_commission - earned_commission - chargeback, ZERO),
        "net_premium_collected": policy_net_premium_collected(policy),
        "gross_collected": policy_gross_collected(policy),
        "installment_fees_collected": policy_installment_fees_collected(policy),
        "inactive_date": inactive,
    }
