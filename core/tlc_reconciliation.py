"""Carrier statement reconciliation for TLC policies."""

from __future__ import annotations

from decimal import Decimal

from .tlc_models import TLCCarrierStatement, TLCCarrierStatementLine, TLCPolicy

ZERO = Decimal("0.00")


def _d(value) -> Decimal:
    return Decimal(str(value or ZERO)).quantize(Decimal("0.01"))


def reconcile_statement_line(line: TLCCarrierStatementLine) -> dict:
    """Match a statement line to an in-system policy and compute variances."""
    org_id = line.statement.organization_id
    policy = line.policy
    if not policy and line.policy_number:
        policy = TLCPolicy.objects.filter(
            organization_id=org_id,
            policy_number__iexact=line.policy_number.strip(),
        ).select_related("premium_breakdown").first()
        if policy:
            line.policy = policy
            line.save(update_fields=["policy"])

    if not policy:
        line.is_matched = False
        line.variance_notes = "No matching TLC policy in system."
        line.save(update_fields=["is_matched", "variance_notes"])
        return {"matched": False, "notes": line.variance_notes}

    written = ZERO
    if hasattr(policy, "premium_breakdown") and policy.premium_breakdown:
        written = _d(policy.premium_breakdown.total_written_premium)
    expected_commission = _d(policy.carrier_commission_amount)
    remitted = _d(policy.amount_remitted_to_carrier)

    premium_var = _d(line.premium_amount) - written
    commission_var = _d(line.commission_amount) - expected_commission
    remit_var = _d(line.remitted_amount) - remitted

    matched = premium_var == ZERO and commission_var == ZERO and remit_var == ZERO
    line.is_matched = matched
    if matched:
        line.variance_notes = "Matched."
    else:
        line.variance_notes = (
            f"Premium Δ {premium_var}, Commission Δ {commission_var}, Remit Δ {remit_var}"
        )
    line.save(update_fields=["is_matched", "variance_notes", "policy"])

    return {
        "matched": matched,
        "policy_id": policy.id,
        "premium_variance": str(premium_var),
        "commission_variance": str(commission_var),
        "remittance_variance": str(remit_var),
        "notes": line.variance_notes,
    }


def reconcile_statement(statement: TLCCarrierStatement) -> dict:
    results = []
    matched = 0
    for line in statement.lines.all():
        result = reconcile_statement_line(line)
        results.append(result)
        if result.get("matched"):
            matched += 1
    statement.is_reconciled = matched == statement.lines.count() and statement.lines.exists()
    statement.save(update_fields=["is_reconciled"])
    return {
        "statement_id": statement.id,
        "lines": len(results),
        "matched": matched,
        "is_reconciled": statement.is_reconciled,
        "details": results,
    }
