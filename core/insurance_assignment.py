"""Round-robin insurance policy assignment pipeline."""

from datetime import date

from django.db import transaction
from django.db.models import Prefetch

from .models import (
    InsuranceAgentHoliday,
    InsuranceAgentRotation,
    InsuranceDistributionConfig,
    InsuranceDistributionState,
    OrganizationMembership,
)


def get_distribution_config(organization):
    config, _ = InsuranceDistributionConfig.objects.get_or_create(
        organization=organization,
    )
    return config


def get_or_create_rotation(membership):
    rotation, _ = InsuranceAgentRotation.objects.get_or_create(membership=membership)
    return rotation


def _membership_queryset(organization, *, only_insurance_agents=True):
    qs = OrganizationMembership.objects.filter(
        organization=organization,
        is_active=True,
        user__is_active=True,
    ).select_related("user").prefetch_related(
        Prefetch(
            "insurance_rotation__holidays",
            queryset=InsuranceAgentHoliday.objects.order_by("-start_date"),
        )
    )
    if only_insurance_agents:
        qs = qs.filter(can_deal_with_insurance=True)
    return qs.order_by("id")


def is_on_holiday(rotation, on_date=None):
    on_date = on_date or date.today()
    for holiday in rotation.holidays.all():
        if holiday.start_date <= on_date <= holiday.end_date:
            return True
    return False


def is_available_for_pipeline(membership, on_date=None):
    on_date = on_date or date.today()
    rotation = getattr(membership, "insurance_rotation", None)
    if rotation is None:
        rotation = get_or_create_rotation(membership)
    if not rotation.in_pipeline or not rotation.is_present:
        return False
    return not is_on_holiday(rotation, on_date)


def get_eligible_pipeline_memberships(organization, on_date=None):
    config = get_distribution_config(organization)
    memberships = list(
        _membership_queryset(
            organization,
            only_insurance_agents=config.only_insurance_agents,
        )
    )
    return [m for m in memberships if is_available_for_pipeline(m, on_date)]


def pick_next_membership(organization, on_date=None):
    """Return the next membership in the pipeline, or None if unavailable."""
    eligible = get_eligible_pipeline_memberships(organization, on_date)
    if not eligible:
        return None

    state, _ = InsuranceDistributionState.objects.get_or_create(organization=organization)
    if not state.last_membership_id:
        return eligible[0]

    eligible_ids = [m.id for m in eligible]
    if state.last_membership_id not in eligible_ids:
        return eligible[0]

    last_index = eligible_ids.index(state.last_membership_id)
    next_index = (last_index + 1) % len(eligible)
    return eligible[next_index]


@transaction.atomic
def advance_pipeline(organization, membership):
    """Record that this membership received the latest auto-assigned policy."""
    state, _ = InsuranceDistributionState.objects.select_for_update().get_or_create(
        organization=organization,
    )
    state.last_membership = membership
    state.save(update_fields=["last_membership", "updated_at"])


def pick_next_agent_user(organization, on_date=None):
    membership = pick_next_membership(organization, on_date)
    return membership.user if membership else None


def validate_manual_agent(organization, user_id, *, only_insurance_agents=True):
    if not user_id:
        return None
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    qs = OrganizationMembership.objects.filter(
        organization=organization,
        user_id=user_id,
        is_active=True,
        user__is_active=True,
    )
    if only_insurance_agents:
        config = get_distribution_config(organization)
        if config.only_insurance_agents:
            qs = qs.filter(can_deal_with_insurance=True)
    membership = qs.select_related("user").first()
    return membership.user if membership else None


def resolve_policy_agent(
    organization,
    request_user,
    *,
    manual_agent_id=None,
    allow_manual=False,
    skip_distribution=False,
    on_date=None,
):
    """
    Decide who should be set as InsurancePolicy.added_by.

    Manual override (owner) wins when allowed. Otherwise round-robin when enabled.
    Falls back to the user who submitted the form.
    """
    config = get_distribution_config(organization)

    if allow_manual and config.allow_manual_override and manual_agent_id:
        manual_user = validate_manual_agent(
            organization,
            manual_agent_id,
            only_insurance_agents=config.only_insurance_agents,
        )
        if manual_user:
            return manual_user, "manual"

    if not skip_distribution and config.is_enabled:
        membership = pick_next_membership(organization, on_date)
        if membership:
            advance_pipeline(organization, membership)
            return membership.user, "pipeline"

    return request_user, "creator"


def build_pipeline_roster(organization, on_date=None):
    """Return pipeline rows for the Insurance Space UI."""
    on_date = on_date or date.today()
    config = get_distribution_config(organization)
    memberships = list(
        _membership_queryset(
            organization,
            only_insurance_agents=config.only_insurance_agents,
        )
    )

    next_membership = (
        pick_next_membership(organization, on_date) if config.is_enabled else None
    )

    rows = []
    for position, membership in enumerate(memberships, start=1):
        rotation = getattr(membership, "insurance_rotation", None)
        if rotation is None:
            rotation = get_or_create_rotation(membership)
        holidays = list(rotation.holidays.all()[:3])
        available = is_available_for_pipeline(membership, on_date)
        rows.append({
            "position": position,
            "membership": membership,
            "user": membership.user,
            "rotation": rotation,
            "holidays": holidays,
            "is_available": available,
            "is_next": bool(
                next_membership
                and next_membership.id == membership.id
                and available
            ),
        })
    return rows
