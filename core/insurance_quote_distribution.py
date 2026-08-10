"""Smart round-robin distribution for insurance quote leads."""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from .agent_portal_models import AgentAttendanceSession, AgentTask
from .agent_portal_services import PORTAL_TZ, current_work_date, portal_now
from .insurance_quote_permissions import can_receive_quote_distribution
from .insurance_quote_pipeline_models import (
    InsuranceAgentOffDay,
    InsuranceQuoteDistributionConfig,
    InsuranceQuoteLead,
)
from .models import Notification, OrganizationMembership


def get_or_create_distribution_config(organization) -> InsuranceQuoteDistributionConfig:
    config, _ = InsuranceQuoteDistributionConfig.objects.get_or_create(
        organization=organization
    )
    return config


def ny_work_date(now=None) -> date:
    return current_work_date(now or portal_now())


def is_sunday_ny(work_date: date | None = None) -> bool:
    d = work_date or ny_work_date()
    return d.weekday() == 6  # Sunday


def insurance_agent_pool(organization):
    qs = (
        OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            can_deal_with_insurance=True,
            user__is_active=True,
        )
        .select_related("user")
        .order_by("id")
    )
    return [m for m in qs if can_receive_quote_distribution(m)]


def agent_is_present(membership, work_date: date) -> bool:
    session = (
        AgentAttendanceSession.objects.filter(
            membership=membership,
            work_date=work_date,
        )
        .order_by("-opened_at")
        .first()
    )
    if session is None:
        return False
    # Present if checked in and not closed for the day.
    return session.closed_at is None


def agent_is_off(membership, work_date: date) -> bool:
    return InsuranceAgentOffDay.objects.filter(
        membership=membership,
        off_date=work_date,
    ).exists()


def eligible_agents_for_auto(
    organization,
    *,
    work_date: date | None = None,
    config: InsuranceQuoteDistributionConfig | None = None,
) -> list[OrganizationMembership]:
    work_date = work_date or ny_work_date()
    config = config or get_or_create_distribution_config(organization)
    agents = insurance_agent_pool(organization)
    eligible = []
    for agent in agents:
        if agent_is_off(agent, work_date):
            continue
        if config.require_attendance_present and not agent_is_present(agent, work_date):
            continue
        eligible.append(agent)
    return eligible


def pick_next_agent(
    organization,
    *,
    work_date: date | None = None,
    config: InsuranceQuoteDistributionConfig | None = None,
) -> OrganizationMembership | None:
    config = config or get_or_create_distribution_config(organization)
    eligible = eligible_agents_for_auto(
        organization, work_date=work_date, config=config
    )
    if not eligible:
        return None
    ids = [m.id for m in eligible]
    cursor = config.last_assigned_membership_id
    start_idx = 0
    if cursor in ids:
        start_idx = (ids.index(cursor) + 1) % len(ids)
    return eligible[start_idx]


def _type_label(insurance_type: str) -> str:
    return (insurance_type or "Insurance").replace("_", " ").title()


def _lead_task_title(lead: InsuranceQuoteLead) -> str:
    return f"Quote: {lead.client_name} · {_type_label(lead.insurance_type)}"[:200]


def _lead_task_description(lead: InsuranceQuoteLead) -> str:
    companies = ", ".join(c.name for c in lead.recommended_companies.all()[:8]) or "—"
    flags = []
    flags.append("Prior" if lead.has_prior else "No prior")
    flags.append("Experienced" if lead.is_experienced else "New to insurance")
    flags.append("Accident history" if lead.has_accident else "No accidents")
    parts = [
        f"Phone: {lead.phone}",
        f"Email: {lead.email or '—'}",
        f"Type: {_type_label(lead.insurance_type)}",
        f"Profile: {', '.join(flags)}",
        f"Recommended carriers: {companies}",
    ]
    if lead.notes:
        parts.append(f"Notes: {lead.notes[:500]}")
    return "\n".join(parts)


def _notify_quote_assigned(lead: InsuranceQuoteLead):
    if not lead.assigned_to_id or not lead.assigned_to.user_id:
        return
    Notification.objects.create(
        user=lead.assigned_to.user,
        organization=lead.organization,
        event_type="quote_lead_assigned",
        level=Notification.Level.INFO,
        title="New quote lead assigned",
        message=_lead_task_title(lead)[:200],
    )


@transaction.atomic
def assign_lead(
    lead: InsuranceQuoteLead,
    membership: OrganizationMembership,
    *,
    mode: str,
    actor=None,
) -> InsuranceQuoteLead:
    lead.assigned_to = membership
    lead.assigned_at = timezone.now()
    lead.assignment_mode = mode
    if lead.stage in {
        InsuranceQuoteLead.Stage.NEW,
        "",
    }:
        lead.stage = InsuranceQuoteLead.Stage.ASSIGNED

    if lead.agent_task_id:
        task = lead.agent_task
        task.assigned_to = membership
        task.title = _lead_task_title(lead)
        task.description = _lead_task_description(lead)
        task.save(update_fields=["assigned_to", "title", "description", "updated_at"])
    else:
        task = AgentTask.objects.create(
            organization=lead.organization,
            assigned_to=membership,
            created_by=actor,
            title=_lead_task_title(lead),
            description=_lead_task_description(lead),
            status=AgentTask.Status.TODO,
            is_done=False,
        )
        lead.agent_task = task

    lead.save(
        update_fields=[
            "assigned_to",
            "assigned_at",
            "assignment_mode",
            "stage",
            "agent_task",
            "updated_at",
        ]
    )
    _notify_quote_assigned(lead)

    config = get_or_create_distribution_config(lead.organization)
    config.last_assigned_membership = membership
    config.save(update_fields=["last_assigned_membership", "updated_at"])
    return lead


def auto_distribute_lead(
    lead: InsuranceQuoteLead,
    *,
    actor=None,
    work_date: date | None = None,
) -> InsuranceQuoteLead:
    """Attempt auto assignment. Leaves unassigned on Sunday / no eligible agents."""
    work_date = work_date or ny_work_date()
    config = get_or_create_distribution_config(lead.organization)

    if not config.is_auto_enabled:
        return lead
    if config.skip_sundays and is_sunday_ny(work_date):
        return lead

    agent = pick_next_agent(
        lead.organization, work_date=work_date, config=config
    )
    if agent is None:
        return lead
    return assign_lead(
        lead,
        agent,
        mode=InsuranceQuoteLead.AssignmentMode.AUTO,
        actor=actor,
    )


def distribution_status(organization, *, work_date: date | None = None) -> dict:
    work_date = work_date or ny_work_date()
    config = get_or_create_distribution_config(organization)
    pool = insurance_agent_pool(organization)
    eligible = eligible_agents_for_auto(
        organization, work_date=work_date, config=config
    )
    sunday = is_sunday_ny(work_date)
    auto_paused = (not config.is_auto_enabled) or (
        config.skip_sundays and sunday
    )
    return {
        "work_date": work_date,
        "is_sunday": sunday,
        "auto_paused": auto_paused,
        "config": config,
        "pool_count": len(pool),
        "eligible_count": len(eligible),
        "eligible": eligible,
        "pool": pool,
    }
