"""Move a policy's open work to its new agent after the policy's agent changes."""

from __future__ import annotations

from django.db import transaction

from .insurance_quote_pipeline_models import InsuranceQuoteLead
from .insurance_radar_models import InsuranceRadarItem
from .insurance_renewal_models import InsuranceRenewal, InsuranceRenewalEvent
from .models import OrganizationMembership

CLOSED_LEAD_STAGES = (InsuranceQuoteLead.Stage.WON, InsuranceQuoteLead.Stage.LOST)


def _agent_name(user) -> str:
    if user is None:
        return "nobody"
    return user.get_full_name() or user.username


@transaction.atomic
def sync_policy_agent(policy, actor=None) -> dict:
    """Give the policy's open renewals, radar items and quote leads to ``policy.added_by``."""
    from .insurance_quote_distribution import assign_lead
    from .insurance_radar import assign as assign_radar_items

    agent = policy.added_by
    counts = {"renewals": 0, "radar": 0, "quotes": 0}

    renewals = list(
        InsuranceRenewal.objects.filter(policy=policy, stage__in=InsuranceRenewal.OPEN_STAGES).exclude(
            assigned_to=agent
        )
    )
    for renewal in renewals:
        renewal.assigned_to = agent
        renewal.save(update_fields=["assigned_to", "updated_at"])
        InsuranceRenewalEvent.objects.create(
            renewal=renewal,
            kind=InsuranceRenewalEvent.Kind.ASSIGN,
            note=f"Policy agent changed to {_agent_name(agent)}",
            user=actor,
        )
    counts["renewals"] = len(renewals)

    radar_items = list(InsuranceRadarItem.objects.filter(policy=policy, status=InsuranceRadarItem.Status.OPEN))
    if radar_items:
        counts["radar"] = assign_radar_items(radar_items, agent, actor or agent)

    membership = (
        OrganizationMembership.objects.filter(
            organization_id=policy.organization_id, user=agent, is_active=True
        ).first()
        if agent
        else None
    )
    leads = InsuranceQuoteLead.objects.filter(crm_policy=policy).exclude(assigned_to=membership)
    for lead in leads.select_related("assigned_to", "agent_task"):
        if membership is not None and lead.stage not in CLOSED_LEAD_STAGES:
            assign_lead(lead, membership, mode=InsuranceQuoteLead.AssignmentMode.MANUAL, actor=actor)
        else:
            lead.assigned_to = membership
            lead.save(update_fields=["assigned_to", "updated_at"])
        counts["quotes"] += 1
    return counts
