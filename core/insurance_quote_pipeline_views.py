"""Fundamental Quote Pipeline views for Insurance Space."""

from __future__ import annotations

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .access import organizations_for_user
from .http import deny_access
from .insurance_quote_distribution import (
    assign_lead,
    auto_distribute_lead,
    distribution_status,
    get_or_create_distribution_config,
    insurance_agent_pool,
    manual_assign_agent_pool,
    ny_work_date,
)
from .insurance_quote_permissions import (
    can_assign_quote_leads,
    can_create_quote_leads,
    can_delete_quote_lead,
    can_edit_quote_lead,
    can_manage_quote_distribution,
    can_receive_quote_distribution,
    can_update_assigned_lead,
    can_view_quote_lead_documents,
    can_view_quote_pipeline,
    membership_for_org,
)
from .insurance_quote_pipeline_models import (
    InsuranceAgentOffDay,
    InsuranceQuoteLead,
    InsuranceQuoteLeadDocument,
    InsuranceQuoteLeadDriver,
    InsuranceQuoteLeadVehicle,
)
from .insurance_targets_metrics import insurance_type_catalog
from .models import InsuranceCompany, Organization, OrganizationMembership, Space
from .policies import redirect_back
from .us_states import US_STATES, normalize_state_code


def _active_org(request) -> Organization | None:
    orgs = organizations_for_user(request)
    active_id = request.session.get("active_org_id")
    if active_id:
        org = orgs.filter(id=active_id).first()
        if org:
            return org
    return orgs.first()


def _board_stage_keys():
    return [
        InsuranceQuoteLead.Stage.ASSIGNED,
        InsuranceQuoteLead.Stage.QUOTING,
        InsuranceQuoteLead.Stage.QUOTED,
        InsuranceQuoteLead.Stage.WON,
        InsuranceQuoteLead.Stage.LOST,
    ]


def _normalize_board_stage(raw: str) -> str:
    """Map legacy 'new' into Assigned; ignore cancelled for board moves."""
    value = (raw or "").strip()
    if value in {"", InsuranceQuoteLead.Stage.NEW}:
        return InsuranceQuoteLead.Stage.ASSIGNED
    if value in {c.value for c in InsuranceQuoteLead.Stage}:
        if value == InsuranceQuoteLead.Stage.CANCELLED:
            return InsuranceQuoteLead.Stage.LOST
        return value
    return InsuranceQuoteLead.Stage.ASSIGNED


def _board_stage_choices():
    labels = dict(InsuranceQuoteLead.Stage.choices)
    return [(key, labels[key]) for key in _board_stage_keys()]


def _insurance_space(org: Organization) -> Space | None:
    return Space.objects.filter(organization=org, key="insurance").first()


def _safe_quote_next(request) -> str | None:
    nxt = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if nxt.startswith("/dashboard/insurance-quotes/"):
        return nxt
    return None


def _redirect_pipeline(request, org: Organization):
    nxt = _safe_quote_next(request)
    if nxt:
        return redirect(nxt)
    space = _insurance_space(org)
    if space:
        return redirect(f"/dashboard/inventory/{space.id}/?tab=quote-pipeline")
    return redirect_back(request, "dashboard")


def build_quote_pipeline_context(request, organization, membership):
    """Context fragment for the Insurance Space Quote Pipeline tab."""
    leads_qs = (
        InsuranceQuoteLead.objects.filter(organization=organization)
        .select_related("assigned_to__user", "created_by", "agent_task")
        .prefetch_related(
            "recommended_companies",
            "documents",
            "additional_drivers",
            "additional_vehicles",
        )
        .order_by("-created_at")
    )
    is_leader = can_manage_quote_distribution(
        request.user, organization, membership=membership
    )
    if not is_leader and membership is not None:
        leads_qs = leads_qs.filter(assigned_to=membership)

    leads = list(leads_qs[:200])
    # Board skips "New" — leads enter via distribution into Assigned.
    stage_keys = _board_stage_keys()
    stage_label_map = dict(InsuranceQuoteLead.Stage.choices)
    board_stage_choices = _board_stage_choices()
    stages = []
    for key in stage_keys:
        if key == InsuranceQuoteLead.Stage.ASSIGNED:
            stage_leads = [
                l
                for l in leads
                if l.stage in {
                    InsuranceQuoteLead.Stage.ASSIGNED,
                    InsuranceQuoteLead.Stage.NEW,
                }
            ]
        else:
            stage_leads = [l for l in leads if l.stage == key]
        stages.append({
            "key": key,
            "label": stage_label_map.get(key, key.title()),
            "leads": stage_leads,
            "latest_leads": stage_leads[:5],
            "total_count": len(stage_leads),
            "has_more": len(stage_leads) > 5,
            "more_count": max(0, len(stage_leads) - 5),
        })
    unassigned = [l for l in leads if not l.assigned_to_id]
    status = distribution_status(organization)
    companies = list(
        InsuranceCompany.objects.filter(organization=organization).order_by("name")
    )
    type_options = insurance_type_catalog(organization)
    agents = insurance_agent_pool(organization)
    assign_agents = manual_assign_agent_pool(organization)
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
        "quote_agents": assign_agents,
        "quote_auto_agents": agents,
        "quote_off_days": off_days,
        "can_create_quote_leads": can_create_quote_leads(
            request.user, organization, membership=membership
        ),
        "can_manage_quote_distribution": is_leader,
        "can_assign_quote_leads": can_assign_quote_leads(
            request.user, organization, membership=membership
        ),
        "can_view_quote_pipeline": can_view_quote_pipeline(
            request.user, organization, membership=membership
        ),
        "quote_stage_choices": board_stage_choices,
        "quote_vehicle_ownership_choices": InsuranceQuoteLead.VehicleOwnership.choices,
        "quote_coverage_type_choices": InsuranceQuoteLead.CoverageType.choices,
        "quote_heard_about_choices": InsuranceQuoteLead.HeardAbout.choices,
        "quote_us_states": US_STATES,
        "can_edit_quote_leads": can_create_quote_leads(
            request.user, organization, membership=membership
        )
        or is_leader,
        "can_delete_quote_leads": is_leader,
        "quote_pipeline_membership": membership,
    }


def _parse_vehicle_ownership(raw: str) -> str:
    value = (raw or "").strip()
    valid = {c.value for c in InsuranceQuoteLead.VehicleOwnership}
    return value if value in valid else ""


def _parse_coverage_type(raw: str) -> str:
    value = (raw or "").strip()
    valid = {c.value for c in InsuranceQuoteLead.CoverageType}
    return value if value in valid else ""


def _parse_heard_about(raw: str) -> str:
    value = (raw or "").strip()
    valid = {c.value for c in InsuranceQuoteLead.HeardAbout}
    return value if value in valid else ""


def _parse_date_of_birth(raw: str):
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_vehicle_year(raw: str) -> str:
    value = (raw or "").strip()
    if value.isdigit() and 1900 <= int(value) <= 2100:
        return value
    return ""


def _apply_car_and_dl_fields(request, lead: InsuranceQuoteLead) -> None:
    lead.vehicle_make = (request.POST.get("vehicle_make") or "").strip()[:80]
    lead.vehicle_model = (request.POST.get("vehicle_model") or "").strip()[:80]
    lead.vehicle_year = _parse_vehicle_year(request.POST.get("vehicle_year"))
    lead.vin = (request.POST.get("vin") or "").strip().upper()[:32]
    lead.dl_number = (request.POST.get("dl_number") or "").strip()[:40]
    lead.date_of_birth = _parse_date_of_birth(request.POST.get("date_of_birth"))


def _apply_address_fields(request, lead: InsuranceQuoteLead) -> None:
    lead.street_address = (request.POST.get("street_address") or "").strip()[:200]
    lead.apartment = (request.POST.get("apartment") or "").strip()[:50]
    lead.city = (request.POST.get("city") or "").strip()[:100]
    lead.state = normalize_state_code(request.POST.get("state") or "NY")
    lead.zip_code = (request.POST.get("zip_code") or "").strip()[:10]


def _save_additional_drivers(request, lead: InsuranceQuoteLead) -> int:
    """Replace additional drivers from parallel POST lists."""
    names = request.POST.getlist("extra_driver_name")
    dls = request.POST.getlist("extra_driver_dl")
    dobs = request.POST.getlist("extra_driver_dob")
    count = max(len(names), len(dls), len(dobs))
    lead.additional_drivers.all().delete()
    created = 0
    for idx in range(count):
        name = (names[idx] if idx < len(names) else "").strip()[:200]
        dl = (dls[idx] if idx < len(dls) else "").strip()[:40]
        dob = _parse_date_of_birth(dobs[idx] if idx < len(dobs) else "")
        if not name and not dl and not dob:
            continue
        InsuranceQuoteLeadDriver.objects.create(
            lead=lead,
            full_name=name,
            dl_number=dl,
            date_of_birth=dob,
            sort_order=created,
        )
        created += 1
    return created


def _save_additional_vehicles(request, lead: InsuranceQuoteLead) -> int:
    """Replace additional vehicles from parallel POST lists."""
    makes = request.POST.getlist("extra_vehicle_make")
    models_ = request.POST.getlist("extra_vehicle_model")
    years = request.POST.getlist("extra_vehicle_year")
    vins = request.POST.getlist("extra_vehicle_vin")
    count = max(len(makes), len(models_), len(years), len(vins))
    lead.additional_vehicles.all().delete()
    created = 0
    for idx in range(count):
        make = (makes[idx] if idx < len(makes) else "").strip()[:80]
        model = (models_[idx] if idx < len(models_) else "").strip()[:80]
        year = _parse_vehicle_year(years[idx] if idx < len(years) else "")
        vin = (vins[idx] if idx < len(vins) else "").strip().upper()[:32]
        if not make and not model and not year and not vin:
            continue
        InsuranceQuoteLeadVehicle.objects.create(
            lead=lead,
            make=make,
            model=model,
            year=year,
            vin=vin,
            sort_order=created,
        )
        created += 1
    return created


def _save_uploaded_documents(request, lead: InsuranceQuoteLead) -> int:
    files = request.FILES.getlist("documents")
    count = 0
    for uploaded in files:
        if not uploaded:
            continue
        InsuranceQuoteLeadDocument.objects.create(
            lead=lead,
            file=uploaded,
            original_name=getattr(uploaded, "name", "")[:255],
            uploaded_by=request.user,
        )
        count += 1
    return count


def _remove_documents(request, lead: InsuranceQuoteLead) -> int:
    raw_ids = request.POST.getlist("remove_documents")
    if not raw_ids:
        return 0
    ids = []
    for value in raw_ids:
        if str(value).isdigit():
            ids.append(int(value))
    if not ids:
        return 0
    removed = 0
    for doc in InsuranceQuoteLeadDocument.objects.filter(lead=lead, id__in=ids):
        if doc.file:
            doc.file.delete(save=False)
        doc.delete()
        removed += 1
    return removed


def _refresh_linked_task_description(lead: InsuranceQuoteLead) -> None:
    if not lead.agent_task_id:
        return
    from .insurance_quote_distribution import _lead_task_description, _lead_task_title

    task = lead.agent_task
    task.title = _lead_task_title(lead)
    task.description = _lead_task_description(lead)
    task.save(update_fields=["title", "description", "updated_at"])


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
        heard_about=_parse_heard_about(request.POST.get("heard_about")),
        street_address=(request.POST.get("street_address") or "").strip()[:200],
        apartment=(request.POST.get("apartment") or "").strip()[:50],
        city=(request.POST.get("city") or "").strip()[:100],
        state=normalize_state_code(request.POST.get("state") or "NY"),
        zip_code=(request.POST.get("zip_code") or "").strip()[:10],
        insurance_type=(request.POST.get("insurance_type") or "").strip(),
        has_prior=request.POST.get("has_prior") in {"1", "true", "on", "yes"},
        is_experienced=request.POST.get("is_experienced") in {"1", "true", "on", "yes"},
        has_accident=request.POST.get("has_accident") in {"1", "true", "on", "yes"},
        vehicle_ownership=_parse_vehicle_ownership(request.POST.get("vehicle_ownership")),
        coverage_type=_parse_coverage_type(request.POST.get("coverage_type")),
        vehicle_make=(request.POST.get("vehicle_make") or "").strip()[:80],
        vehicle_model=(request.POST.get("vehicle_model") or "").strip()[:80],
        vehicle_year=_parse_vehicle_year(request.POST.get("vehicle_year")),
        vin=(request.POST.get("vin") or "").strip().upper()[:32],
        dl_number=(request.POST.get("dl_number") or "").strip()[:40],
        date_of_birth=_parse_date_of_birth(request.POST.get("date_of_birth")),
        notes=(request.POST.get("notes") or "").strip(),
        stage=InsuranceQuoteLead.Stage.ASSIGNED,
        assignment_mode=InsuranceQuoteLead.AssignmentMode.UNASSIGNED,
    )
    company_ids = request.POST.getlist("recommended_companies")
    if company_ids:
        companies = InsuranceCompany.objects.filter(
            organization=org, id__in=company_ids
        )
        lead.recommended_companies.set(companies)

    _save_additional_drivers(request, lead)
    _save_additional_vehicles(request, lead)
    _save_uploaded_documents(request, lead)

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
        if agent.can_deal_with_insurance:
            assign_lead(
                lead,
                agent,
                mode=InsuranceQuoteLead.AssignmentMode.MANUAL,
                actor=request.user,
            )
            messages.success(request, f"Lead created and assigned to {agent.user.get_full_name() or agent.user.username}.")
        else:
            messages.warning(request, "Lead created but assignee cannot deal with insurance.")
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
    _refresh_linked_task_description(lead)
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
    if not agent.can_deal_with_insurance:
        messages.error(request, "Leads can only be assigned to insurance-capable team members.")
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
    stage = _normalize_board_stage(stage)
    valid = set(_board_stage_keys())
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
    lead.heard_about = _parse_heard_about(request.POST.get("heard_about"))
    _apply_address_fields(request, lead)
    lead.insurance_type = (request.POST.get("insurance_type") or "").strip()
    lead.has_prior = request.POST.get("has_prior") in {"1", "true", "on", "yes"}
    lead.is_experienced = request.POST.get("is_experienced") in {"1", "true", "on", "yes"}
    lead.has_accident = request.POST.get("has_accident") in {"1", "true", "on", "yes"}
    lead.vehicle_ownership = _parse_vehicle_ownership(request.POST.get("vehicle_ownership"))
    lead.coverage_type = _parse_coverage_type(request.POST.get("coverage_type"))
    _apply_car_and_dl_fields(request, lead)
    lead.notes = (request.POST.get("notes") or "").strip()

    stage = (request.POST.get("stage") or "").strip()
    if stage:
        lead.stage = _normalize_board_stage(stage)

    lead.save()
    company_ids = request.POST.getlist("recommended_companies")
    companies = InsuranceCompany.objects.filter(organization=org, id__in=company_ids)
    lead.recommended_companies.set(companies)

    _save_additional_drivers(request, lead)
    _save_additional_vehicles(request, lead)
    _remove_documents(request, lead)
    _save_uploaded_documents(request, lead)
    _refresh_linked_task_description(lead)
    return True, ""


@login_required
@require_GET
def download_quote_lead_document(request, document_id: int):
    doc = get_object_or_404(
        InsuranceQuoteLeadDocument.objects.select_related(
            "lead", "lead__assigned_to", "lead__organization"
        ),
        id=document_id,
    )
    lead = doc.lead
    org = lead.organization
    membership = membership_for_org(request.user, org)
    if not can_view_quote_lead_documents(request.user, lead, membership=membership):
        deny_access("You cannot view documents for this lead.")
    if not doc.file:
        raise Http404("File missing.")
    filename = doc.original_name or doc.file.name.rsplit("/", 1)[-1]
    response = FileResponse(doc.file.open("rb"), as_attachment=True, filename=filename)
    return response


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
            if agent and agent.can_deal_with_insurance:
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


@login_required
@require_GET
def quote_records(request):
    """Dedicated Quote Records page — searchable, filterable, paginated table."""
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    membership = membership_for_org(request.user, org)
    if not can_view_quote_pipeline(request.user, org, membership=membership):
        deny_access("You cannot view quote records.")

    ctx = build_quote_pipeline_context(request, org, membership)
    space = _insurance_space(org)

    q = (request.GET.get("q") or "").strip()
    stage = (request.GET.get("stage") or "all").strip()
    agent = (request.GET.get("agent") or "all").strip()
    insurance_type = (request.GET.get("type") or "all").strip()
    prior = request.GET.get("prior") in {"1", "true", "on"}
    accident = request.GET.get("accident") in {"1", "true", "on"}

    leads_qs = (
        InsuranceQuoteLead.objects.filter(organization=org)
        .select_related("assigned_to__user", "created_by")
        .prefetch_related(
            "recommended_companies",
            "documents",
            "additional_drivers",
            "additional_vehicles",
        )
        .order_by("-created_at")
    )
    is_leader = can_manage_quote_distribution(
        request.user, org, membership=membership
    )
    if not is_leader and membership is not None:
        leads_qs = leads_qs.filter(assigned_to=membership)

    valid_stages = set(_board_stage_keys())
    if stage in {InsuranceQuoteLead.Stage.ASSIGNED, InsuranceQuoteLead.Stage.NEW}:
        leads_qs = leads_qs.filter(
            stage__in=[
                InsuranceQuoteLead.Stage.ASSIGNED,
                InsuranceQuoteLead.Stage.NEW,
            ]
        )
        stage = InsuranceQuoteLead.Stage.ASSIGNED
    elif stage in valid_stages:
        leads_qs = leads_qs.filter(stage=stage)
    if agent == "unassigned":
        leads_qs = leads_qs.filter(assigned_to__isnull=True)
    elif agent.isdigit():
        leads_qs = leads_qs.filter(assigned_to_id=int(agent))
    if insurance_type and insurance_type != "all":
        leads_qs = leads_qs.filter(insurance_type=insurance_type)
    if prior:
        leads_qs = leads_qs.filter(has_prior=True)
    if accident:
        leads_qs = leads_qs.filter(has_accident=True)
    if q:
        leads_qs = leads_qs.filter(
            Q(client_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
            | Q(vin__icontains=q)
            | Q(vehicle_make__icontains=q)
            | Q(vehicle_model__icontains=q)
            | Q(city__icontains=q)
            | Q(notes__icontains=q)
        )

    paginator = Paginator(leads_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    records_url = reverse("quote-records")
    query = request.GET.copy()
    query.pop("page", None)
    query_string = query.urlencode()

    ctx.update(
        {
            "page_obj": page_obj,
            "filter_q": q,
            "filter_stage": stage if stage in valid_stages else "all",
            "filter_agent": agent,
            "filter_type": insurance_type,
            "filter_prior": prior,
            "filter_accident": accident,
            "insurance_space": space,
            "quote_form_next": (
                f"{records_url}?{query_string}" if query_string else records_url
            ),
            "records_query_string": query_string,
        }
    )
    return render(request, "core/insurance_quote_records.html", ctx)

