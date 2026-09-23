"""Views for the Defense Driving Course space."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .client_search import build_client_name_search_q
from .defense_driving_crm import (
    defense_driving_dashboard_stats,
    enrich_enrollment,
    ensure_default_packages,
    split_profits_for_package,
)
from .http import deny_access
from .models import (
    Client,
    DefenseDrivingEnrollment,
    DefenseDrivingPackage,
    OrganizationMembership,
    Space,
)
from .space_access import get_org_membership, require_space_access
from .space_important_docs import important_docs_context, user_can_manage_space_docs
from .views import _get_user_organizations


def _resolve_ddc_access(request, space_id=None, card=None):
    organizations = _get_user_organizations(request)
    if card is None:
        card = get_object_or_404(
            Space,
            id=space_id,
            organization__in=organizations,
            key="defense_driving",
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


def _ddc_url(card, tab=None):
    from django.urls import reverse

    url = reverse("inventory-detail", kwargs={"inventory_id": card.id})
    if tab:
        url += f"?tab={tab}"
    return url


def _redirect_ddc(card, tab=None, request=None):
    from .policies import redirect_back

    url = _ddc_url(card, tab)
    if request is not None:
        return redirect_back(request, url)
    return redirect(url)


def _parse_decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return default


def _user_can_manage_ddc(is_owner, membership):
    return is_owner or (membership and membership.can_deal_with_defense_driving)


def build_defense_driving_space_context(request, card, is_owner, membership):
    active_org = card.organization
    ensure_default_packages(active_org)
    stats = defense_driving_dashboard_stats(card)

    search = request.GET.get("q", "").strip()
    channel_filter = request.GET.get("channel", "").strip()
    status_filter = request.GET.get("status", "").strip()
    package_filter = request.GET.get("package", "").strip()

    enrollments_qs = (
        DefenseDrivingEnrollment.objects.filter(space=card)
        .select_related("client", "package", "added_by")
        .order_by("-created_at")
    )
    if search:
        enrollments_qs = enrollments_qs.filter(
            Q(enrollment_number__icontains=search)
            | Q(certificate_number__icontains=search)
            | Q(client__email__icontains=search)
            | Q(client__phone_number__icontains=search)
            | Q(client__driver_license__icontains=search)
            | Q(client__business_name__icontains=search)
            | build_client_name_search_q(search, prefix="client__")
        ).distinct()
    if channel_filter:
        enrollments_qs = enrollments_qs.filter(channel=channel_filter)
    if status_filter:
        enrollments_qs = enrollments_qs.filter(status=status_filter)
    if package_filter:
        enrollments_qs = enrollments_qs.filter(package_id=package_filter)

    page = Paginator(enrollments_qs, 15).get_page(request.GET.get("page", 1))
    for row in page:
        enrich_enrollment(row)

    can_manage = _user_can_manage_ddc(is_owner, membership)
    packages = DefenseDrivingPackage.objects.filter(organization=active_org).order_by(
        "sort_order", "name"
    )
    active_packages = packages.filter(is_active=True)

    docs_ctx = important_docs_context(
        card,
        can_manage=user_can_manage_space_docs(is_owner, membership, card),
        accent="#0d9488",
    )

    return {
        "card": card,
        "active_org": active_org,
        "is_owner": is_owner,
        "can_manage_defense_driving": can_manage,
        "stats": stats,
        "packages": packages,
        "active_packages": active_packages,
        "enrollments_page": page,
        "enrollments": page,
        "active_tab": request.GET.get("tab", "dashboard"),
        "search": search,
        "channel_filter": channel_filter,
        "status_filter": status_filter,
        "package_filter": package_filter,
        "channel_choices": DefenseDrivingEnrollment.ChannelChoices.choices,
        "status_choices": DefenseDrivingEnrollment.StatusChoices.choices,
        **docs_ctx,
    }


def _create_enrollment_from_request(request, card, client):
    package_id = request.POST.get("package_id", "").strip()
    package = DefenseDrivingPackage.objects.filter(
        id=package_id,
        organization=card.organization,
        is_active=True,
    ).first()
    if not package:
        return None, "Select a valid course package."

    channel = request.POST.get(
        "channel", DefenseDrivingEnrollment.ChannelChoices.DIRECT
    )
    if channel not in dict(DefenseDrivingEnrollment.ChannelChoices.choices):
        channel = DefenseDrivingEnrollment.ChannelChoices.DIRECT

    provider_profit = request.POST.get("provider_profit", "").strip()
    psb_profit = request.POST.get("psb_profit", "").strip()
    if provider_profit or psb_profit:
        provider_val = _parse_decimal(provider_profit)
        psb_val = _parse_decimal(psb_profit)
    else:
        provider_val, psb_val = split_profits_for_package(package)

    status = request.POST.get("status", DefenseDrivingEnrollment.StatusChoices.ACTIVE)
    if status not in dict(DefenseDrivingEnrollment.StatusChoices.choices):
        status = DefenseDrivingEnrollment.StatusChoices.ACTIVE

    enrollment = DefenseDrivingEnrollment.objects.create(
        organization=card.organization,
        space=card,
        client=client,
        package=package,
        channel=channel,
        status=status,
        start_date=request.POST.get("start_date") or None,
        completion_date=request.POST.get("completion_date") or None,
        certificate_number=request.POST.get("certificate_number", "").strip(),
        provider_profit=provider_val,
        psb_profit=psb_val,
        notes=request.POST.get("notes", "").strip(),
        added_by=request.user,
    )
    return enrollment, None


@login_required
@require_POST
def add_defense_driving_enrollment(request, space_id):
    card, is_owner, membership = _resolve_ddc_access(request, space_id=space_id)
    if not _user_can_manage_ddc(is_owner, membership):
        deny_access("You do not have permission to add Defense Driving enrollments.")

    client_id = request.POST.get("client_id")
    client = get_object_or_404(Client, id=client_id, organization=card.organization)
    created, error = _create_enrollment_from_request(request, card, client)
    if error:
        messages.error(request, error)
        return _redirect_ddc(card, tab="enrollments", request=request)

    messages.success(request, f"Defense Driving enrollment added for {client.name}.")
    return _redirect_ddc(card, tab="enrollments", request=request)


@login_required
@require_POST
def add_defense_driving_enrollment_from_client(request, client_id):
    from django.urls import reverse

    client = get_object_or_404(Client, id=client_id)
    get_org_membership(request.user, client.organization)

    card = Space.objects.filter(
        organization=client.organization, key="defense_driving"
    ).first()
    if not card:
        messages.error(request, "Defense Driving space is not set up for this PSB.")
        return redirect("client-detail", client_id=client.id)

    _, is_owner, membership = _resolve_ddc_access(request, card=card)
    if not _user_can_manage_ddc(is_owner, membership):
        deny_access("You do not have permission to add Defense Driving enrollments.")

    created, error = _create_enrollment_from_request(request, card, client)
    if error:
        messages.error(request, error)
        return redirect("client-detail", client_id=client.id)

    messages.success(
        request,
        f"Defense Driving enrollment added for {client.name} and synced to CRM.",
    )
    return redirect(reverse("inventory-detail", args=[card.id]) + "?tab=enrollments")


@login_required
@require_POST
def edit_defense_driving_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(
        DefenseDrivingEnrollment.objects.select_related("space", "package"),
        id=enrollment_id,
    )
    card, is_owner, m = _resolve_ddc_access(request, card=enrollment.space)
    if not _user_can_manage_ddc(is_owner, m):
        deny_access("You do not have permission to edit Defense Driving enrollments.")

    package_id = request.POST.get("package_id", "").strip()
    if package_id:
        package = DefenseDrivingPackage.objects.filter(
            id=package_id, organization=card.organization
        ).first()
        if package:
            enrollment.package = package

    status = request.POST.get("status", enrollment.status)
    if status in dict(DefenseDrivingEnrollment.StatusChoices.choices):
        enrollment.status = status

    channel = request.POST.get("channel", enrollment.channel)
    if channel in dict(DefenseDrivingEnrollment.ChannelChoices.choices):
        enrollment.channel = channel

    enrollment.start_date = request.POST.get("start_date") or None
    enrollment.completion_date = request.POST.get("completion_date") or None
    enrollment.certificate_number = request.POST.get("certificate_number", "").strip()
    enrollment.notes = request.POST.get("notes", "").strip()
    enrollment.provider_profit = _parse_decimal(
        request.POST.get("provider_profit"),
        enrollment.provider_profit,
    )
    enrollment.psb_profit = _parse_decimal(
        request.POST.get("psb_profit"),
        enrollment.psb_profit,
    )
    enrollment.save()
    messages.success(request, "Defense Driving enrollment updated.")
    return _redirect_ddc(card, tab="enrollments", request=request)


@login_required
@require_POST
def delete_defense_driving_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(
        DefenseDrivingEnrollment.objects.select_related("space", "client"),
        id=enrollment_id,
    )
    card, is_owner, m = _resolve_ddc_access(request, card=enrollment.space)
    if not _user_can_manage_ddc(is_owner, m):
        deny_access("You do not have permission to delete Defense Driving enrollments.")

    client_name = enrollment.client.name
    enrollment.delete()
    messages.success(request, f"Removed Defense Driving enrollment for {client_name}.")
    return _redirect_ddc(card, tab="enrollments", request=request)


@login_required
@require_POST
def save_defense_driving_package(request, space_id):
    card, is_owner, membership = _resolve_ddc_access(request, space_id=space_id)
    if not _user_can_manage_ddc(is_owner, membership):
        deny_access("You do not have permission to manage Defense Driving packages.")

    package_id = request.POST.get("package_id", "").strip()
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, "Package name is required.")
        return _redirect_ddc(card, tab="packages", request=request)

    price = _parse_decimal(request.POST.get("price"))
    provider_take = _parse_decimal(request.POST.get("provider_take"))
    if provider_take > price:
        provider_take = price
    sort_order = int(request.POST.get("sort_order") or 0)
    is_active = request.POST.get("is_active") == "on"

    if package_id:
        package = get_object_or_404(
            DefenseDrivingPackage,
            id=package_id,
            organization=card.organization,
        )
        package.name = name
        package.price = price
        package.provider_take = provider_take
        package.sort_order = sort_order
        package.is_active = is_active
        package.save()
        messages.success(request, f"Updated package “{name}”.")
    else:
        DefenseDrivingPackage.objects.create(
            organization=card.organization,
            name=name,
            price=price,
            provider_take=provider_take,
            sort_order=sort_order,
            is_active=is_active,
        )
        messages.success(request, f"Added package “{name}”.")

    return _redirect_ddc(card, tab="packages", request=request)


@login_required
@require_POST
def delete_defense_driving_package(request, package_id):
    package = get_object_or_404(DefenseDrivingPackage, id=package_id)
    card = Space.objects.filter(
        organization=package.organization, key="defense_driving"
    ).first()
    if not card:
        deny_access("Defense Driving space not found.")
    _, is_owner, membership = _resolve_ddc_access(request, card=card)
    if not is_owner:
        deny_access("Only PSB owners can remove course packages.")

    if package.enrollments.exists():
        package.is_active = False
        package.save(update_fields=["is_active", "updated_at"])
        messages.success(
            request,
            f"Package “{package.name}” has enrollments — deactivated instead of deleted.",
        )
    else:
        name = package.name
        package.delete()
        messages.success(request, f"Removed package “{name}”.")
    return _redirect_ddc(card, tab="packages", request=request)
