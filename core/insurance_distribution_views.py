"""Views for insurance policy round-robin distribution."""

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .http import deny_access
from .insurance_assignment import get_or_create_rotation
from .models import (
    InsuranceAgentHoliday,
    InsuranceDistributionConfig,
    OrganizationMembership,
)
from .views import _get_insurance_space_id, _get_user_organizations


def _resolve_insurance_org(request):
    organizations = _get_user_organizations(request)
    active_org_id = request.session.get("active_org_id")
    active_org = None
    if active_org_id:
        active_org = organizations.filter(id=active_org_id).first()
    if not active_org and organizations.count() == 1:
        active_org = organizations.first()
    if not active_org:
        deny_access("Select a PSB location first.")
    return active_org


def _user_membership(request, organization):
    if request.user.is_superuser:
        return None
    membership = OrganizationMembership.objects.filter(
        user=request.user,
        organization=organization,
        is_active=True,
        organization__is_active=True,
    ).first()
    if not membership:
        deny_access("Access denied.")
    return membership


def _is_org_owner(request, organization, membership=None):
    if request.user.is_superuser:
        return True
    return bool(
        membership
        and membership.role == OrganizationMembership.Role.OWNER
    )


def _redirect_insurance(organization, tab="agents"):
    from django.urls import reverse

    space_id = _get_insurance_space_id(organization)
    if space_id:
        return redirect(reverse("inventory-detail", args=[space_id]) + f"?tab={tab}")
    return redirect("spaces-home")


@login_required
@require_POST
def save_insurance_distribution_config(request):
    organization = _resolve_insurance_org(request)
    if not (request.user.is_superuser or request.user.is_staff):
        deny_access("Distribution pipeline settings are managed in Django Admin.")
    _user_membership(request, organization)

    config, _ = InsuranceDistributionConfig.objects.get_or_create(organization=organization)
    config.is_enabled = request.POST.get("is_enabled") == "on"
    config.only_insurance_agents = request.POST.get("only_insurance_agents") == "on"
    config.allow_manual_override = request.POST.get("allow_manual_override") == "on"
    config.save()

    messages.success(request, "Insurance distribution pipeline settings saved.")
    return _redirect_insurance(organization, tab="agents")


@login_required
@require_POST
def update_insurance_agent_rotation(request, membership_id):
    organization = _resolve_insurance_org(request)
    membership = _user_membership(request, organization)
    target = get_object_or_404(
        OrganizationMembership,
        id=membership_id,
        organization=organization,
        is_active=True,
    )

    is_self = target.user_id == request.user.id
    is_platform_admin = request.user.is_superuser or request.user.is_staff
    if not is_self and not is_platform_admin:
        deny_access("You can only update your own pipeline availability.")

    rotation = get_or_create_rotation(target)
    rotation.in_pipeline = request.POST.get("in_pipeline") == "on"
    rotation.is_present = request.POST.get("is_present") == "on"
    rotation.save()

    messages.success(
        request,
        f"Pipeline availability updated for {target.user.get_full_name() or target.user.username}.",
    )
    return redirect("insurance-agent-detail", user_id=target.user_id)


@login_required
@require_POST
def add_insurance_agent_holiday(request, membership_id):
    organization = _resolve_insurance_org(request)
    membership = _user_membership(request, organization)
    target = get_object_or_404(
        OrganizationMembership,
        id=membership_id,
        organization=organization,
        is_active=True,
    )

    is_self = target.user_id == request.user.id
    is_platform_admin = request.user.is_superuser or request.user.is_staff
    if not is_self and not is_platform_admin:
        deny_access("You can only manage your own holidays.")

    start_raw = request.POST.get("start_date", "").strip()
    end_raw = request.POST.get("end_date", "").strip()
    reason = request.POST.get("reason", "").strip()

    try:
        start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
    except ValueError:
        messages.error(request, "Enter valid start and end dates for the holiday.")
        return redirect("insurance-agent-detail", user_id=target.user_id)

    if end_date < start_date:
        messages.error(request, "Holiday end date must be on or after the start date.")
        return redirect("insurance-agent-detail", user_id=target.user_id)

    rotation = get_or_create_rotation(target)
    InsuranceAgentHoliday.objects.create(
        rotation=rotation,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    messages.success(request, "Holiday added — you are out of the pipeline for those dates.")
    return redirect("insurance-agent-detail", user_id=target.user_id)


@login_required
@require_POST
def delete_insurance_agent_holiday(request, holiday_id):
    organization = _resolve_insurance_org(request)
    membership = _user_membership(request, organization)
    holiday = get_object_or_404(
        InsuranceAgentHoliday.objects.select_related("rotation__membership"),
        id=holiday_id,
        rotation__membership__organization=organization,
    )
    target = holiday.rotation.membership

    is_self = target.user_id == request.user.id
    is_platform_admin = request.user.is_superuser or request.user.is_staff
    if not is_self and not is_platform_admin:
        deny_access("You can only remove your own holidays.")

    holiday.delete()
    messages.success(request, "Holiday removed from the pipeline.")
    return redirect("insurance-agent-detail", user_id=target.user_id)
