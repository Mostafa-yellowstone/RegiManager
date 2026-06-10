"""Helpers for rendering insurance policy cards with consistent styling."""

from decimal import Decimal


TYPE_CARD_STYLES = {
    "auto_personal": ("linear-gradient(135deg, #1e3a8a 0%, #2563eb 45%, #06b6d4 100%)", "#dbeafe"),
    "motor_cycle": ("linear-gradient(135deg, #7c2d12 0%, #ea580c 55%, #fbbf24 100%)", "#ffedd5"),
    "commercial_auto": ("linear-gradient(135deg, #312e81 0%, #4f46e5 50%, #818cf8 100%)", "#e0e7ff"),
    "trucking": ("linear-gradient(135deg, #1e293b 0%, #475569 50%, #64748b 100%)", "#e2e8f0"),
    "contractors": ("linear-gradient(135deg, #92400e 0%, #d97706 55%, #f59e0b 100%)", "#fef3c7"),
    "landscaping": ("linear-gradient(135deg, #14532d 0%, #16a34a 55%, #4ade80 100%)", "#dcfce7"),
    "dealer_plates": ("linear-gradient(135deg, #581c87 0%, #9333ea 55%, #c084fc 100%)", "#f3e8ff"),
    "home_owners": ("linear-gradient(135deg, #064e3b 0%, #059669 50%, #34d399 100%)", "#d1fae5"),
    "ho3": ("linear-gradient(135deg, #134e4a 0%, #0d9488 55%, #2dd4bf 100%)", "#ccfbf1"),
    "ho4": ("linear-gradient(135deg, #155e75 0%, #0891b2 55%, #67e8f9 100%)", "#cffafe"),
    "ho6": ("linear-gradient(135deg, #1e40af 0%, #3b82f6 55%, #93c5fd 100%)", "#dbeafe"),
    "dwelling": ("linear-gradient(135deg, #365314 0%, #65a30d 55%, #a3e635 100%)", "#ecfccb"),
    "umbrella": ("linear-gradient(135deg, #1d4ed8 0%, #6366f1 55%, #a5b4fc 100%)", "#e0e7ff"),
    "business_owners_policy": ("linear-gradient(135deg, #4c1d95 0%, #7c3aed 55%, #a78bfa 100%)", "#ede9fe"),
    "general_liability": ("linear-gradient(135deg, #0f172a 0%, #334155 55%, #64748b 100%)", "#f1f5f9"),
}


def _user_colors(username):
    h = sum(ord(c) for c in username) * 37 % 360
    return f"hsl({h}, 75%, 93%)", f"hsl({h}, 80%, 25%)"


def get_policy_card_style(policy):
    insurance_type = getattr(policy, "insurance_type", "") or ""
    if insurance_type in TYPE_CARD_STYLES:
        return TYPE_CARD_STYLES[insurance_type]

    stage = getattr(policy, "stage", "")
    status = getattr(policy, "status", "")

    if stage in ("quote", "endorsement_quote"):
        return (
            "linear-gradient(135deg, #312e81 0%, #6366f1 50%, #c4b5fd 100%)",
            "#ede9fe",
        )
    if status == "inactive":
        return (
            "linear-gradient(135deg, #7f1d1d 0%, #dc2626 55%, #f87171 100%)",
            "#fee2e2",
        )
    if status == "pending":
        return (
            "linear-gradient(135deg, #92400e 0%, #f59e0b 55%, #fcd34d 100%)",
            "#fef3c7",
        )
    if status == "rejected":
        return (
            "linear-gradient(135deg, #374151 0%, #6b7280 55%, #9ca3af 100%)",
            "#f3f4f6",
        )
    return (
        "linear-gradient(135deg, #0f766e 0%, #14b8a6 45%, #22d3ee 100%)",
        "#ccfbf1",
    )


def enrich_policy_for_display(policy, unearned_commission=None):
    gradient, accent = get_policy_card_style(policy)
    policy.card_gradient = gradient
    policy.card_accent = accent
    policy.card_pattern_hue = (policy.id * 47) % 360

    if unearned_commission is not None:
        policy.unearned_commission = unearned_commission
    elif not hasattr(policy, "unearned_commission"):
        policy.unearned_commission = Decimal("0")

    added_by = getattr(policy, "added_by", None)
    if added_by:
        bg, text = _user_colors(added_by.username)
        policy.agent_bg_color = bg
        policy.agent_text_color = text


def enrich_policies_for_display(policies, unearned_map=None):
    unearned_map = unearned_map or {}
    for policy in policies:
        enrich_policy_for_display(policy, unearned_map.get(policy.id))
