"""First-class PSB roles and their default permission packs.

Enforcement still uses OrganizationMembership.can_* flags; assigning a role
applies the matching pack. Owners retain full access via role checks.
"""

from __future__ import annotations

from .models import OrganizationMembership

Role = OrganizationMembership.Role

# Boolean flags controlled by role packs (advanced UI may still override).
ROLE_FLAG_FIELDS = (
    "can_view_reports",
    "can_view_net_profit",
    "can_manage_referrals",
    "can_trigger_automation",
    "can_view_spaces",
    "can_deal_with_insurance",
    "can_deal_with_motorclub",
    "can_deal_with_tlc",
    "can_assign_agent_tasks",
    "can_delete_receipt",
    "can_delete_vehicle",
    "can_issue_refund",
    "can_view_commission",
    "can_view_banking",
    "can_manage_news",
    "can_manage_knowledge_hub",
    "can_manage_documents",
    "can_manage_email_marketing",
    "can_view_regiconnect",
    "can_manage_regiconnect",
)

_FALSE_PACK = {field: False for field in ROLE_FLAG_FIELDS}

ROLE_PACKS: dict[str, dict[str, bool]] = {
    Role.OWNER: {field: True for field in ROLE_FLAG_FIELDS},
    Role.MANAGER: {
        **_FALSE_PACK,
        "can_view_reports": True,
        "can_view_net_profit": True,
        "can_manage_referrals": True,
        "can_view_spaces": True,
        "can_assign_agent_tasks": True,
        "can_manage_news": True,
        "can_manage_knowledge_hub": True,
        "can_manage_email_marketing": True,
        "can_view_regiconnect": True,
        "can_manage_regiconnect": True,
        "can_delete_receipt": True,
        "can_delete_vehicle": True,
        "can_issue_refund": True,
        # Pack B: Finance/Reports overview only — no banking edits
        "can_view_banking": False,
        "can_deal_with_insurance": False,
    },
    Role.ACCOUNTANT: {
        **_FALSE_PACK,
        "can_view_reports": True,
        "can_view_net_profit": True,
        "can_view_banking": True,
        "can_view_commission": True,
        "can_manage_referrals": True,
        "can_view_spaces": True,
        "can_deal_with_insurance": False,
        "can_assign_agent_tasks": False,
        "can_view_regiconnect": True,
        "can_manage_regiconnect": False,
    },
    Role.INSURANCE_AGENT: {
        **_FALSE_PACK,
        "can_deal_with_insurance": True,
        "can_view_spaces": True,
        "can_deal_with_motorclub": True,
        "can_deal_with_tlc": True,
        "can_view_banking": False,
        "can_assign_agent_tasks": False,
        "can_view_regiconnect": True,
        "can_manage_regiconnect": False,
    },
    Role.AGENT: {
        **_FALSE_PACK,
        "can_view_spaces": True,
        "can_delete_receipt": False,
        "can_deal_with_insurance": False,
        "can_view_banking": False,
    },
}

# Legacy DB value "member" treated as Agent until remapped.
LEGACY_MEMBER = "member"

ASSIGNABLE_ROLES = (
    Role.OWNER,
    Role.MANAGER,
    Role.ACCOUNTANT,
    Role.INSURANCE_AGENT,
    Role.AGENT,
)


def normalize_role(role: str | None) -> str:
    if not role:
        return Role.AGENT
    value = str(role).strip().lower()
    if value == LEGACY_MEMBER:
        return Role.AGENT
    if value in dict(Role.choices):
        return value
    return Role.AGENT


def is_owner_role(role: str | None) -> bool:
    return normalize_role(role) == Role.OWNER


def is_owner_or_manager_role(role: str | None) -> bool:
    return normalize_role(role) in {Role.OWNER, Role.MANAGER}


def is_insurance_agent_role(membership: OrganizationMembership | None) -> bool:
    if membership is None:
        return False
    role = normalize_role(membership.role)
    if role == Role.INSURANCE_AGENT:
        return True
    return bool(membership.can_deal_with_insurance and role != Role.OWNER)


def pack_for_role(role: str | None) -> dict[str, bool]:
    role = normalize_role(role)
    return dict(ROLE_PACKS.get(role, ROLE_PACKS[Role.AGENT]))


def apply_role_permission_pack(
    membership: OrganizationMembership,
    *,
    save: bool = True,
) -> OrganizationMembership:
    """Set can_* flags from the membership's current role."""
    pack = pack_for_role(membership.role)
    for field, value in pack.items():
        setattr(membership, field, value)
    if save:
        membership.save(update_fields=[*ROLE_FLAG_FIELDS, "role"])
    return membership


def role_label(role: str | None) -> str:
    role = normalize_role(role)
    return dict(Role.choices).get(role, "Agent")


def nav_role_label(memberships) -> str:
    """Pick the strongest active role label for the top nav."""
    roles = {normalize_role(m.role) for m in memberships}
    for candidate in (
        Role.OWNER,
        Role.MANAGER,
        Role.ACCOUNTANT,
        Role.INSURANCE_AGENT,
        Role.AGENT,
    ):
        if candidate in roles:
            return f"PSB {role_label(candidate)}"
    return "PSB Agent"
