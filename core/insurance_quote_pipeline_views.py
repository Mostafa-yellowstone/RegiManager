"""Fundamental Quote Pipeline views for Insurance Space."""

from __future__ import annotations

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import organizations_for_user
from .http import deny_access
from .insurance_quote_distribution import (
    assign_lead,
    auto_distribute_lead,
    distribution_status,
    get_or_create_distribution_config,
    insurance_agent_pool,
    ny_work_date,
)
from .insurance_quote_permissions import (
    can_create_quote_leads,
    can_delete_quote_lead,
    can_edit_quote_lead,
    can_manage_quote_distribution,
    can_receive_quote_distribution,
    can_update_assigned_lead,
    can_view_quote_pipeline,
    membership_for_org,
)
from .insurance_quote_pipeline_models import (
    InsuranceAgentOffDay,
    InsuranceQuoteLead,
)
from .insurance_targets_metrics import insurance_type_catalog
from .models import InsuranceCompany, Organization, OrganizationMembership, Space
from .policies import redirect_back


def _active_org(request) -> Organization | None:
    orgs = organizations_for_user(request)
    active_id = request.session.get("active_org_id")
    if active_id:
        org = orgs.filter(id=active_id).first()
        if org:
            return org
    return orgs.first()


def _insurance_space(org: Organization) -> Space | None:
    return Space.objects.filter(organization=org, key="insurance").first()


def _redirect_pipeline(request, org: Organization):
    space = _insurance_space(org)
    if space:
        return redirect(f"/dashboard/inventory/{space.id}/?tab=quote-pipeline")
    return redirect_back(request, "dashboard")


def build_quote_pipeline_context(request, organization, membership):
    """Context fragment for the Insurance Space Quote Pipeline tab."""
    leads_qs = (
        InsuranceQuoteLead.objects.filter(organization=organization)
        .select_related("assigned_to__user", "created_by", "agent_task")
        .prefetch_related("recommended_companies")
        .order_by("-created_at")
    )
    is_leader = can_manage_quote_distribution(
        request.user, organization, membership=membership
    )
    if not is_leader and membership is not None:
        leads_qs = leads_qs.filter(assigned_to=membership)

    leads = list(leads_qs[:200])
    stages = [
        {"key": key, "label": label, "leads": [l for l in leads if l.stage == key]}
        for key, label in InsuranceQuoteLead.Stage.choices
        if key
        in {
            InsuranceQuoteLead.Stage.NEW,
            InsuranceQuoteLead.Stage.ASSIGNED,
            InsuranceQuoteLead.Stage.QUOTING,
            InsuranceQuoteLead.Stage.QUOTED,
            InsuranceQuoteLead.Stage.WON,
            InsuranceQuoteLead.Stage.LOST,
        }
    ]
    unassigned = [l for l in leads if not l.assigned_to_id]
    status = distribution_status(organization)
    companies = list(
        InsuranceCompany.objects.filter(organization=organization).order_by("name")
    )
    type_options = insurance_type_catalog(organization)
    agents = insurance_agent_pool(organization)
    off_days = list(
        InsuranceAgentOffDay.objects.filter(
            organization=organization,
            off_date__gte=ny_work_date(),
        )
        .select_related("membership__user")
        .order_by("off_date")[:60]
    )
    return {
        "organization": organization,
        "quote_leads": leads,
        "quote_stages": stages,
        "quote_unassigned": unassigned,
        "quote_kpis": {
            "total": len(leads),
            "unassigned": len(unassigned),
            "quoting": sum(
                1 for l in leads if l.stage == InsuranceQuoteLead.Stage.QUOTING
            ),
            "won": sum(1 for l in leads if l.stage == InsuranceQuoteLead.Stage.WON),
        },
        "quote_distribution": status,
        "quote_companies": companies,
        "quote_type_options": type_options,
        "quote_agents": agents,
        "quote_off_days": off_days,
        "can_create_quote_leads": can_create_quote_leads(
            request.user, organization, membership=membership
        ),
        "can_manage_quote_distribution": is_leader,
        "can_view_quote_pipeline": can_view_quote_pipeline(
            request.user, organization, membership=membership
        ),
        "quote_stage_choices": InsuranceQuoteLead.Stage.choices,
        "can_edit_quote_leads": can_create_quote_leads(
            request.user, organization, membership=membership
        )
        or is_leader,
        "can_delete_quote_leads": is_leader,
    }


@login_required
@require_POST
def create_quote_lead(request):
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    membership = membership_for_org(request.user, org)
    if not can_create_quote_leads(request.user, org, membership=membership):
        deny_access("You cannot create quote leads.")

    client_name = (request.POST.get("client_name") or "").strip()
    phone = (request.POST.get("phone") or "").strip()
    if not client_name or not phone:
        messages.error(request, "Client name and phone are required.")
        return _redirect_pipeline(request, org)

    lead = InsuranceQuoteLead.objects.create(
        organization=org,
        created_by=request.user,
        client_name=client_name,
        phone=phone,
        email=(request.POST.get("email") or "").strip(),
        insurance_type=(request.POST.get("insurance_type") or "").strip(),
        has_prior=request.POST.get("has_prior") in {"1", "true", "on", "yes"},
        is_experienced=request.POST.get("is_experienced") in {"1", "true", "on", "yes"},
        has_accident=request.POST.get("has_accident") in {"1", "true", "on", "yes"},
        notes=(request.POST.get("notes") or "").strip(),
        stage=InsuranceQuoteLead.Stage.NEW,
        assignment_mode=InsuranceQuoteLead.AssignmentMode.UNASSIGNED,
    )
    company_ids = request.POST.getlist("recommended_companies")
    if company_ids:
        companies = InsuranceCompany.objects.filter(
            organization=org, id__in=company_ids
        )
        lead.recommended_companies.set(companies)

    manual_agent_id = (request.POST.get("assigned_to") or "").strip()
    if manual_agent_id and can_manage_quote_distribution(
        request.user, org, membership=membership
    ):
        agent = get_object_or_404(
            OrganizationMembership,
            id=manual_agent_id,
            organization=org,
            is_active=True,
        )
        if can_receive_quote_distribution(agent):
            assign_lead(
                lead,
                agent,
                mode=InsuranceQuoteLead.AssignmentMode.MANUAL,
                actor=request.user,
            )
            messages.success(request, f"Lead created and assigned to {agent.user.get_full_name() or agent.user.username}.")
        else:
            messages.warning(request, "Lead created but assignee is not an insurance agent.")
    else:
        auto_distribute_lead(lead, actor=request.user)
        lead.refresh_from_db()
        if lead.assigned_to_id:
            messages.success(
                request,
                f"Lead created and auto-assigned to {lead.assigned_to.user.get_full_name() or lead.assigned_to.user.username}.",
            )
        else:
            messages.success(
                request,
                "Lead created and waiting in the unassigned queue (auto-distribution paused or no eligible agents).",
            )

    from .realtime import publish_org_quote_event

    lead.refresh_from_db()
    publish_org_quote_event(
        org.id,
        "quote_pipeline.changed",
        {
            "lead_id": lead.id,
            "stage": lead.stage,
            "assigned_to_id": lead.assigned_to_id,
            "reason": "created",
        },
    )
    return _redirect_pipeline(request, org)


@login_required
@require_POST
def assign_quote_lead(request, lead_id: int):
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    membership = membership_for_org(request.user, org)
    if not can_manage_quote_distribution(request.user, org, membership=membership):
        deny_access("Owner or manager access required to assign leads.")

    lead = get_object_or_404(InsuranceQuoteLead, id=lead_id, organization=org)
    agent_id = request.POST.get("assigned_to")
    agent = get_object_or_404(
        OrganizationMembership,
        id=agent_id,
        organization=org,
        is_active=True,
    )
    if not can_receive_quote_distribution(agent):
        messages.error(request, "Leads can only be distributed to insurance agents.")
        return _redirect_pipeline(request, org)

    assign_lead(
        lead,
        agent,
        mode=InsuranceQuoteLead.AssignmentMode.MANUAL,
        actor=request.user,
    )
    messages.success(request, "Lead assigned.")
    return _redirect_pipeline(request, org)


@login_required
@require_POST
def update_quote_lead_stage(request, lead_id: int):
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    membership = membership_for_org(request.user, org)
    lead = get_object_or_404(InsuranceQuoteLead, id=lead_id, organization=org)
    if not can_update_assigned_lead(request.user, lead, membership=membership):
        deny_access("You cannot update this lead.")

    stage = (request.POST.get("stage") or "").strip()
    valid = {c.value for c in InsuranceQuoteLead.Stage}
    if stage not in valid:
        messages.error(request, "Invalid stage.")
        return _redirect_pipeline(request, org)

    lead.stage = stage
    note = request.POST.get("notes")
    if note is not None and note.strip():
        lead.notes = (lead.notes + "\n" if lead.notes else "") + note.strip()
    lead.save(update_fields=["stage", "notes", "updated_at"])

    if lead.agent_task_id and stage in {
        InsuranceQuoteLead.Stage.QUOTING,
        InsuranceQuoteLead.Stage.QUOTED,
        InsuranceQuoteLead.Stage.WON,
        InsuranceQuoteLead.Stage.LOST,
    }:
        task = lead.agent_task
        status_map = {
            InsuranceQuoteLead.Stage.QUOTING: "in_progress",
            InsuranceQuoteLead.Stage.QUOTED: "waiting",
            InsuranceQuoteLead.Stage.WON: "done",
            InsuranceQuoteLead.Stage.LOST: "done",
        }
        try:
            task.set_status(
                status_map[stage],
                note=f"Lead moved to {lead.get_stage_display()}",
            )
        except Exception:
            pass

    from .realtime import publish_org_quote_event

    publish_org_quote_event(
        org.id,
        "quote_pipeline.changed",
        {
            "lead_id": lead.id,
            "stage": lead.stage,
            "assigned_to_id": lead.assigned_to_id,
            "reason": "stage_updated",
        },
    )

    messages.success(request, "Lead updated.")
    return _redirect_pipeline(request, org)


def _apply_lead_fields(request, lead, org):
    client_name = (request.POST.get("client_name") or "").strip()
    phone = (request.POST.get("phone") or "").strip()
    if not client_name or not phone:
        return False, "Client name and phone are required."

    lead.client_name = client_name
    lead.phone = phone
    lead.email = (request.POST.get("email") or "").strip()
    lead.insurance_type = (request.POST.get("insurance_type") or "").strip()
    lead.has_prior = request.POST.get("has_prior") in {"1", "true", "on", "yes"}
    lead.is_experienced = request.POST.get("is_experienced") in {"1", "true", "on", "yes"}
    lead.has_accident = request.POST.get("has_accident") in {"1", "true", "on", "yes"}
    lead.notes = (request.POST.get("notes") or "").strip()

    stage = (request.POST.get("stage") or "").strip()
    valid_stages = {c.value for c in InsuranceQuoteLead.Stage}
    if stage in valid_stages:
        lead.stage = stage

    lead.save()
    company_ids = request.POST.getlist("recommended_companies")
    companies = InsuranceCompany.objects.filter(organization=org, id__in=company_ids)
    lead.recommended_companies.set(companies)

    if lead.agent_task_id:
        from .insurance_quote_distribution import _lead_task_description, _lead_task_title

        task = lead.agent_task
        task.title = _lead_task_title(lead)
        task.description = _lead_task_description(lead)
        task.save(update_fields=["title", "description", "updated_at"])
    return True, ""


@login_required
@require_POST
def edit_quote_lead(request, lead_id: int):
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    membership = membership_for_org(request.user, org)
    lead = get_object_or_404(InsuranceQuoteLead, id=lead_id, organization=org)
    if not can_edit_quote_lead(request.user, lead, membership=membership):
        deny_access("You cannot edit this lead.")

    ok, err = _apply_lead_fields(request, lead, org)
    if not ok:
        messages.error(request, err)
        return _redirect_pipeline(request, org)

    # Optional reassignment for owners/managers.
    if can_manage_quote_distribution(request.user, org, membership=membership):
        manual_agent_id = (request.POST.get("assigned_to") or "").strip()
        if manual_agent_id:
            agent = OrganizationMembership.objects.filter(
                id=manual_agent_id,
                organization=org,
                is_active=True,
            ).first()
            if agent and can_receive_quote_distribution(agent):
                if lead.assigned_to_id != agent.id:
                    assign_lead(
                        lead,
                        agent,
                        mode=InsuranceQuoteLead.AssignmentMode.MANUAL,
                        actor=request.user,
                    )

    from .realtime import publish_org_quote_event

    lead.refresh_from_db()
    publish_org_quote_event(
        org.id,
        "quote_pipeline.changed",
        {
            "lead_id": lead.id,
            "stage": lead.stage,
            "assigned_to_id": lead.assigned_to_id,
            "reason": "edited",
        },
    )
    messages.success(request, "Lead saved.")
    return _redirect_pipeline(request, org)


@login_required
@require_POST
def delete_quote_lead(request, lead_id: int):
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    membership = membership_for_org(request.user, org)
    lead = get_object_or_404(InsuranceQuoteLead, id=lead_id, organization=org)
    if not can_delete_quote_lead(request.user, lead, membership=membership):
        deny_access("Owner or manager access required to delete leads.")

    lead_id_val = lead.id
    task = lead.agent_task
    lead.agent_task = None
    lead.save(update_fields=["agent_task", "updated_at"])
    lead.delete()
    if task is not None:
        task.delete()

    from .realtime import publish_org_quote_event

    publish_org_quote_event(
        org.id,
        "quote_pipeline.changed",
        {
            "lead_id": lead_id_val,
            "stage": "",
            "assigned_to_id": None,
            "reason": "deleted",
        },
    )
    messages.success(request, "Lead removed.")
    return _redirect_pipeline(request, org)


@login_required
@require_POST
def save_quote_distribution_config(request):
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    membership = membership_for_org(request.user, org)
    if not can_manage_quote_distribution(request.user, org, membership=membership):
        deny_access("Owner or manager access required.")

    config = get_or_create_distribution_config(org)
    config.is_auto_enabled = request.POST.get("is_auto_enabled") in {
        "1",
        "true",
        "on",
        "yes",
    }
    config.skip_sundays = request.POST.get("skip_sundays") in {
        "1",
        "true",
        "on",
        "yes",
    }
    config.require_attendance_present = request.POST.get(
        "require_attendance_present"
    ) in {"1", "true", "on", "yes"}
    config.save()
    messages.success(request, "Distribution settings saved.")
    return _redirect_pipeline(request, org)


@login_required
@require_POST
def add_insurance_agent_off_day(request):
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    membership = membership_for_org(request.user, org)
    if not can_manage_quote_distribution(request.user, org, membership=membership):
        deny_access("Owner or manager access required.")

    agent_id = request.POST.get("membership_id")
    off_raw = (request.POST.get("off_date") or "").strip()
    reason = (request.POST.get("reason") or "").strip()
    agent = get_object_or_404(
        OrganizationMembership,
        id=agent_id,
        organization=org,
        is_active=True,
    )
    if not can_receive_quote_distribution(agent):
        messages.error(request, "Off days apply to insurance agents only.")
        return _redirect_pipeline(request, org)
    try:
        off_date = datetime.strptime(off_raw, "%Y-%m-%d").date()
    except ValueError:
        messages.error(request, "Invalid off date.")
        return _redirect_pipeline(request, org)

    InsuranceAgentOffDay.objects.update_or_create(
        membership=agent,
        off_date=off_date,
        defaults={
            "organization": org,
            "reason": reason,
            "created_by": request.user,
        },
    )
    messages.success(request, "Off day saved — agent excluded from auto-distribution that day.")
    return _redirect_pipeline(request, org)


@login_required
@require_POST
def delete_insurance_agent_off_day(request, off_day_id: int):
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    membership = membership_for_org(request.user, org)
    if not can_manage_quote_distribution(request.user, org, membership=membership):
        deny_access("Owner or manager access required.")
    off = get_object_or_404(InsuranceAgentOffDay, id=off_day_id, organization=org)
    off.delete()
    messages.success(request, "Off day removed.")
    return _redirect_pipeline(request, org)
