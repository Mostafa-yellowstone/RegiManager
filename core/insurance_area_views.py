"""The Insurance area (/insurance/): one page per section, outside Spaces."""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, QueryDict
from django.shortcuts import render
from django.urls import reverse

from .http import deny_access
from .insurance_permissions import can_manage_insurance_finance
from .models import OrganizationMembership, Space
from .products import (
    active_membership,
    active_organization_for,
    can_use_insurance,
    can_use_psb_portal,
    insurance_brand_name,
    insurance_space_for,
)

# Old Spaces tab keys -> Insurance area URL names.
TAB_URL_NAMES = {
    "home": "insurance-home",
    "insurance": "insurance-policies",
    "policies": "insurance-policies",
    "quote-pipeline": "insurance-pipeline",
    "companies": "insurance-companies",
    "banking": "insurance-finance",
    "producers": "insurance-producers",
    "reporting": "insurance-reports",
    "esign": "insurance-esign",
    "targets": "insurance-targets",
    "daily-payments": "insurance-payments",
    "agents": "insurance-agents",
    "renewals": "insurance-renewals",
    "radar": "insurance-radar",
}

# Pages that need DMV data, shown only when the office also has the PSB portal.
PSB_DATA_TABS = frozenset({"radar"})

# (tab key, URL name, label, icon, finance managers only)
NAV_GROUPS = (
    ("Overview", (
        ("home", "insurance-home", "Home", "home", False),
    )),
    ("Sales", (
        ("quote-pipeline", "insurance-pipeline", "Quote Pipeline", "pipeline", False),
        ("insurance", "insurance-policies", "Policies", "policies", False),
        ("renewals", "insurance-renewals", "Renewals", "renewals", False),
        ("radar", "insurance-radar", "DMV Radar", "radar", False),
    )),
    ("Money", (
        ("daily-payments", "insurance-payments", "Daily Payments", "payments", False),
        ("banking", "insurance-finance", "Finance", "finance", True),
        ("companies", "insurance-companies", "Companies", "companies", True),
        ("producers", "insurance-producers", "Producers", "producers", True),
    )),
    ("Insights", (
        ("reporting", "insurance-reports", "Reports", "reports", False),
        ("targets", "insurance-targets", "Targets & Forecast", "targets", False),
        ("agents", "insurance-agents", "Agent Auditing", "agents", False),
    )),
    ("Tools", (
        ("esign", "insurance-esign", "E-Signature", "esign", False),
    )),
)

BOTTOM_BAR = ("home", "insurance", "daily-payments", "quote-pipeline")

# Context sections each page needs (see build_insurance_context).
PAGE_SECTIONS = {
    "home": set(),
    "insurance": {"policies"},
    "quote-pipeline": {"pipeline"},
    "daily-payments": {"payments"},
    "banking": {"finance"},
    "companies": {"companies"},
    "producers": {"producers"},
    "reporting": {"reports"},
    "targets": {"targets"},
    "agents": {"agents"},
    "esign": {"esign"},
    "renewals": set(),
    "radar": set(),
}


def insurance_url_for_tab(tab=None, query=None) -> str:
    """URL of the Insurance page for an old Spaces tab key, keeping the other query parameters."""
    url = reverse(TAB_URL_NAMES.get((tab or "").strip(), "insurance-home"))
    if isinstance(query, QueryDict):
        params = query.copy()
        params.pop("tab", None)
        encoded = params.urlencode()
    elif query:
        encoded = "&".join(p for p in query if p and not p.startswith("tab="))
    else:
        encoded = ""
    return f"{url}?{encoded}" if encoded else url


def _insurance_access(request):
    organization = active_organization_for(request)
    if organization is None:
        deny_access("Access denied.")
    membership = None if request.user.is_superuser else active_membership(request.user, organization)
    if not can_use_insurance(request.user, organization, membership):
        deny_access("You do not have access to Insurance.")
    is_owner = bool(
        request.user.is_superuser
        or (membership and membership.role == OrganizationMembership.Role.OWNER)
    )
    can_view_banking = can_manage_insurance_finance(
        request.user, organization, membership=membership, is_owner=is_owner
    )
    return organization, membership, is_owner, can_view_banking


def _knowledge_hub_for(organization, membership, is_owner):
    hub = Space.objects.filter(organization=organization, key="knowledge_hub").first()
    if hub is None or is_owner or membership is None:
        return hub
    if membership.can_view_spaces and membership.accessible_spaces.filter(id=hub.id).exists():
        return hub
    return None


def _nav_groups(current_tab, can_view_banking, has_dmv_data=False):
    groups = []
    for title, items in NAV_GROUPS:
        items = [i for i in items if has_dmv_data or i[0] not in PSB_DATA_TABS]
        links = [
            {
                "tab": tab,
                "url": reverse(url_name),
                "label": label,
                "icon": icon,
                "active": tab == current_tab,
            }
            for tab, url_name, label, icon, finance_only in items
            if can_view_banking or not finance_only
        ]
        if links:
            groups.append({"title": title, "links": links})
    return groups


def _render_page(request, tab, template, *, finance_only=False, extra=None, label=None):
    """Render an Insurance page; ``extra(organization, membership)`` may add context or return a response."""
    organization, membership, is_owner, can_view_banking = _insurance_access(request)
    if finance_only and not can_view_banking:
        deny_access("You do not have permission to view this page.")

    from .views import build_insurance_context

    card = insurance_space_for(organization)
    context = build_insurance_context(
        request, card, membership, is_owner, can_view_banking, sections=PAGE_SECTIONS[tab]
    )
    if isinstance(context, HttpResponse):
        return context
    if extra is not None:
        added = extra(organization, membership)
        if isinstance(added, HttpResponse):
            return added
        context.update(added)

    groups = _nav_groups(tab, can_view_banking, has_dmv_data=organization.has_psb_portal)
    links_by_tab = {link["tab"]: link for group in groups for link in group["links"]}
    context.update(
        {
            "insurance_tab": tab,
            "insurance_name": insurance_brand_name(organization),
            "insurance_nav_groups": groups,
            "insurance_bottom_links": [links_by_tab[t] for t in BOTTOM_BAR if t in links_by_tab],
            "insurance_page_label": label or links_by_tab.get(tab, {}).get("label", ""),
            "insurance_knowledge_hub": _knowledge_hub_for(organization, membership, is_owner),
            "insurance_has_psb": can_use_psb_portal(request.user, organization, membership),
        }
    )
    return render(request, template, context)


SEARCH_LIMIT = 6


@login_required
def insurance_search(request):
    """Ctrl+K search: clients, policies, vehicles (plate / VIN), payments and companies."""
    from django.db.models import CharField, Q, Value
    from django.db.models.functions import Concat
    from django.http import JsonResponse

    from .models import Client, DailyPaymentTransaction, InsuranceCompany, InsurancePolicy, Vehicle

    organization, membership, is_owner, can_view_banking = _insurance_access(request)
    q = " ".join((request.GET.get("q") or "").split())[:80]
    if len(q) < 2:
        return JsonResponse({"q": q, "groups": []})
    digits = "".join(ch for ch in q if ch.isdigit())

    full_name = Concat("first_name", Value(" "), "last_name", output_field=CharField())
    client_match = Q(full_name__icontains=q) | Q(email__icontains=q)
    if len(digits) >= 4:
        client_match |= Q(phone_number__contains=digits)
    clients = (
        Client.objects.filter(organization=organization)
        .annotate(full_name=full_name)
        .filter(client_match)
        .order_by("first_name", "last_name")[:SEARCH_LIMIT]
    )

    client_name = Concat("client__first_name", Value(" "), "client__last_name", output_field=CharField())
    policies = (
        InsurancePolicy.objects.filter(organization=organization)
        .annotate(client_name=client_name)
        .filter(
            Q(policy_number__icontains=q)
            | Q(named_insured__icontains=q)
            | Q(client_name__icontains=q)
            | Q(plate_number__iexact=q)
            | Q(vin__icontains=q)
        )
        .select_related("client", "insurance_company")
        .order_by("-created_at")[:SEARCH_LIMIT]
    )

    vehicles = (
        Vehicle.objects.filter(client__organization=organization)
        .filter(Q(plate_number__iexact=q) | Q(vin__icontains=q))
        .select_related("client")[:SEARCH_LIMIT]
        if len(q) >= 3
        else []
    )

    payment_match = Q(policy_number__icontains=q) | Q(client_name__icontains=q)
    if q.lstrip("#").isdigit():
        payment_match |= Q(id=int(q.lstrip("#")))
    payments = (
        DailyPaymentTransaction.objects.filter(organization=organization)
        .annotate(client_name=client_name)
        .filter(payment_match)
        .select_related("client")
        .order_by("-transaction_date", "-id")[:SEARCH_LIMIT]
    )

    groups = []

    def add(title, items):
        if items:
            groups.append({"title": title, "items": items})

    add("Clients", [
        {
            "label": c.full_name,
            "meta": " · ".join(filter(None, [c.phone_number, c.email or ""])),
            "url": reverse("client-detail", args=[c.id]),
        }
        for c in clients
    ])
    add("Policies", [
        {
            "label": p.policy_number or "(no policy #)",
            "meta": " · ".join(filter(None, [
                p.named_insured or p.client_name,
                p.insurance_company.name if p.insurance_company else "",
                p.get_status_display(),
            ])),
            "url": reverse("insurance-policy-detail", args=[p.id]),
        }
        for p in policies
    ])
    add("Vehicles", [
        {
            "label": " ".join(filter(None, [v.plate_number, str(v.year or ""), v.make, v.model])) or v.vin,
            "meta": f"VIN {v.vin} · {v.client.first_name} {v.client.last_name}",
            "url": reverse("client-detail", args=[v.client_id]),
        }
        for v in vehicles
    ])
    add("Payments", [
        {
            "label": f"#{t.id} · ${t.amount:,.2f}",
            "meta": " · ".join(filter(None, [
                t.transaction_date.strftime("%b %d, %Y"), t.client_name, t.policy_number,
            ])),
            "url": reverse("insurance-payments") + "?" + urlencode({
                "daily_date": t.transaction_date.isoformat(),
                "daily_q": t.policy_number or t.client_name,
            }),
        }
        for t in payments
    ])
    if can_view_banking:
        add("Companies", [
            {"label": c.name, "meta": "Insurance company", "url": reverse("insurance-company-detail", args=[c.id])}
            for c in InsuranceCompany.objects.filter(organization=organization, name__icontains=q)
            .order_by("name")[:SEARCH_LIMIT]
        ])
    return JsonResponse({"q": q, "groups": groups})


@login_required
def insurance_home(request):
    from .insurance_radar import radar_summary
    from .insurance_renewals import is_renewal_manager, today_board

    def extra(organization, membership):
        manager = is_renewal_manager(request.user, membership)
        mine = request.GET.get("scope") == "mine" if manager else True
        from .insurance_desk import desk_today

        return {
            "today": today_board(organization, request.user, mine=mine),
            "today_is_manager": manager,
            "today_radar": radar_summary(organization, request.user, manager=manager and not mine),
            "desk": desk_today(organization, request.user, mine=mine if manager else True),
        }

    return _render_page(request, "home", "core/insurance_area/home.html", extra=extra)


@login_required
def insurance_pipeline(request):
    return _render_page(request, "quote-pipeline", "core/insurance_area/pipeline.html")


@login_required
def insurance_policies(request):
    return _render_page(request, "insurance", "core/insurance_area/policies.html")


@login_required
def insurance_payments(request):
    return _render_page(request, "daily-payments", "core/insurance_area/payments.html")


@login_required
def insurance_finance(request):
    from .insurance_desk import recent_statements
    from .models import InsuranceCompany

    def extra(organization, membership):
        return {
            "commission_statements": recent_statements(organization),
            "statement_companies": InsuranceCompany.objects.filter(organization=organization).order_by("name"),
        }

    return _render_page(request, "banking", "core/insurance_area/finance.html", finance_only=True, extra=extra)


@login_required
def insurance_companies(request):
    return _render_page(request, "companies", "core/insurance_area/companies.html", finance_only=True)


@login_required
def insurance_producers(request):
    return _render_page(request, "producers", "core/insurance_area/producers.html", finance_only=True)


@login_required
def insurance_reports(request):
    return _render_page(request, "reporting", "core/insurance_area/reports.html")


@login_required
def insurance_targets(request):
    return _render_page(request, "targets", "core/insurance_area/targets.html")


@login_required
def insurance_agents(request):
    return _render_page(request, "agents", "core/insurance_area/agents.html")


@login_required
def insurance_esign(request):
    return _render_page(request, "esign", "core/insurance_area/esign.html")
