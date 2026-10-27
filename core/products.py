"""Which products (PSB portal, Insurance) an office has and which of them a member may open.

Offices switch products on in Django admin (Organization.has_psb_portal / has_insurance);
members get per-product access (OrganizationMembership.can_use_psb_portal / can_use_insurance).
Owners and superusers get every product their office has.
"""

from __future__ import annotations

from .models import OrganizationMembership, Space

INSURANCE_SPACE_DEFAULTS = {"label": "Insurance", "description": "Insurance CRM and Financial space"}


def active_membership(user, organization):
    if not getattr(user, "is_authenticated", False) or organization is None:
        return None
    return OrganizationMembership.objects.filter(
        user=user, organization=organization, is_active=True, organization__is_active=True
    ).first()


def _is_owner(membership) -> bool:
    return bool(membership and membership.role == OrganizationMembership.Role.OWNER)


def can_use_insurance(user, organization, membership=None) -> bool:
    if organization is None or not organization.has_insurance:
        return False
    if getattr(user, "is_superuser", False):
        return True
    membership = membership or active_membership(user, organization)
    if membership is None:
        return False
    return _is_owner(membership) or bool(membership.can_use_insurance)


def can_use_psb_portal(user, organization, membership=None) -> bool:
    if organization is None or not organization.has_psb_portal:
        return False
    if getattr(user, "is_superuser", False):
        return True
    membership = membership or active_membership(user, organization)
    if membership is None:
        return False
    return _is_owner(membership) or bool(membership.can_use_psb_portal)


def insurance_space_for(organization) -> Space:
    """The office's Insurance space record (holds branding and links); created on first use."""
    space, _ = Space.objects.get_or_create(
        organization=organization, key="insurance", defaults=INSURANCE_SPACE_DEFAULTS
    )
    return space


def insurance_companion_spaces(organization) -> list[Space]:
    """Motor Club, TLC, and Defense Driving, created so the insurance menu can open them."""
    specs = (
        ("motorclub", "Motor Club", "Roadside assistance memberships — insurance upsell and partnerships"),
        ("tlc", "TLC", "TLC premiums, installments, and carrier payables"),
        ("defense_driving", "Defense Driving Course", "Defense driving enrollments, packages, and certificates"),
    )
    spaces = []
    for key, label, description in specs:
        space, _created = Space.objects.get_or_create(
            organization=organization,
            key=key,
            defaults={"label": label, "description": description},
        )
        spaces.append(space)
    return spaces


def insurance_brand_name(organization) -> str:
    if organization is None:
        return "Insurance"
    return (organization.insurance_intake_display_name or "").strip() or "Insurance"


def active_organization_for(request):
    """The office the user is working in: the session's active office, else their first one."""
    from .access import organizations_for_user

    organizations = organizations_for_user(request)
    active_id = request.session.get("active_org_id")
    if active_id:
        org = organizations.filter(id=active_id).first()
        if org:
            return org
    return organizations.first()


INSURANCE_PATH_PREFIXES = (
    "/insurance/",
    "/dashboard/spaces/insurance/",
    "/dashboard/spaces/banking/",
    "/dashboard/insurance-quotes/",
)

# Portal tools every office gets, whichever products it has.
SHARED_PATH_PREFIXES = (
    "/dashboard/notifications/",
    "/dashboard/agent-portal/",
    "/dashboard/email-marketing/",
    "/dashboard/site-news/",
    "/dashboard/psb/switch/",
    "/dashboard/clients/",
    "/dashboard/client-search/",
    "/dashboard/get-client-details/",
    "/dashboard/check-client-name/",
    "/dashboard/notes/",
    "/dashboard/spaces/knowledge-hub/",
    "/dashboard/agents/",
    "/dashboard/agent/",
    "/dashboard/contact-messages/",
)

SHARED_SPACE_KEYS = {"knowledge_hub"}

# Programs that live as their own spaces and also open from the insurance portal.
INSURANCE_COMPANION_SPACE_KEYS = frozenset({"motorclub", "tlc", "defense_driving"})
INSURANCE_COMPANION_PREFIXES = (
    "/dashboard/spaces/motorclub/",
    "/dashboard/spaces/defense-driving/",
    "/dashboard/spaces/tlc/",
)

INSURANCE = "insurance"
PSB = "psb"
SHARED = "shared"


def product_for_path(path: str) -> str | None:
    """insurance / psb / shared for portal pages; None for public pages, APIs, admin and assets."""
    if path.startswith(INSURANCE_PATH_PREFIXES):
        return INSURANCE
    if not path.startswith("/dashboard/"):
        return None
    if path.startswith(SHARED_PATH_PREFIXES) or path.startswith(INSURANCE_COMPANION_PREFIXES):
        return SHARED
    if path.startswith("/dashboard/inventory/"):
        parts = path.split("/")
        if len(parts) > 3 and parts[3].isdigit():
            key = Space.objects.filter(id=int(parts[3])).values_list("key", flat=True).first()
            if key == "insurance":
                return INSURANCE
            if key in SHARED_SPACE_KEYS or key in INSURANCE_COMPANION_SPACE_KEYS:
                return SHARED
    return PSB


def products_for(request, organization=None) -> dict:
    organization = organization if organization is not None else active_organization_for(request)
    membership = None if request.user.is_superuser else active_membership(request.user, organization)
    return {
        "organization": organization,
        "membership": membership,
        "insurance": can_use_insurance(request.user, organization, membership),
        "psb": can_use_psb_portal(request.user, organization, membership),
    }
