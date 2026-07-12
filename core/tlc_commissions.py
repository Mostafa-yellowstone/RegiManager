"""Carrier commission rule resolution for TLC policies."""

from __future__ import annotations

from decimal import Decimal

from .tlc_models import TLCCarrierCommissionRule, TLCPolicy

ZERO = Decimal("0.00")


def resolve_commission_rule(organization_id: int, carrier: str, policy_type: str) -> TLCCarrierCommissionRule | None:
    carrier_key = (carrier or "").strip()
    if not carrier_key:
        return None
    rules = TLCCarrierCommissionRule.objects.filter(
        organization_id=organization_id,
        carrier__iexact=carrier_key,
        is_active=True,
    )
    exact = rules.filter(policy_type=policy_type).first()
    if exact:
        return exact
    return rules.filter(policy_type="").first()


def apply_commission_rule_to_policy(policy: TLCPolicy, *, premium=None, save: bool = True) -> bool:
    """Apply matching carrier rule to policy commission fields. Returns True if a rule matched."""
    rule = resolve_commission_rule(policy.organization_id, policy.carrier, policy.policy_type)
    if not rule:
        return False
    policy.commission_rate = rule.commission_rate
    if policy.policy_type == TLCPolicy.PolicyType.RENEWAL and rule.renewal_commission_rate:
        policy.renewal_commission_rate = rule.renewal_commission_rate
    if premium is None:
        try:
            premium = policy.premium_breakdown.total_written_premium
        except Exception:
            premium = ZERO
    premium = Decimal(str(premium or ZERO))
    policy.carrier_commission_amount = (
        premium * (Decimal(str(rule.commission_rate)) / Decimal("100"))
    ).quantize(Decimal("0.01"))
    if save:
        policy.save(update_fields=["commission_rate", "renewal_commission_rate", "carrier_commission_amount", "updated_at"])
    return True
