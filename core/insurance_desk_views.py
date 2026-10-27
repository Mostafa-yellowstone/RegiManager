"""Public quote portal and the insurance desk actions (coverages, bind, claims, certificates)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .http import deny_access
from .insurance_desk import (
    add_vehicle_coverage,
    bind_quote_option,
    holder_for,
    import_commission_csv,
    issue_certificate,
    issue_compensation_disclosure,
    issue_standard_form,
    issue_temporary_id_card,
    notify_client,
    open_claim,
    record_transaction,
    save_policy_coverages,
)
from .insurance_desk_models import (
    InsuranceCertificate,
    InsuranceClaim,
    InsuranceClaimPhoto,
    InsuranceDriverIncident,
    InsurancePolicyTransaction,
    InsuranceQuoteOption,
)
from .insurance_permissions import can_manage_insurance_finance
from .insurance_policy_views import _can_access_insurance, _user_orgs
from .insurance_quote_distribution import auto_distribute_lead
from .insurance_quote_permissions import can_update_assigned_lead, is_owner_or_manager, membership_for_org
from .insurance_quote_pipeline_models import (
    InsuranceQuoteLead,
    InsuranceQuoteLeadDocument,
    InsuranceQuoteLeadDriver,
    InsuranceQuoteLeadVehicle,
)
from .models import InsuranceCompany, InsurancePolicy, InsurancePolicyDriver, InsurancePolicyVehicle, Organization, Vehicle
from .products import insurance_brand_name
from .us_states import normalize_state_code


def _policy_or_deny(request, policy_id) -> InsurancePolicy:
    policy = get_object_or_404(
        InsurancePolicy.objects.select_related("organization", "client", "insurance_company"),
        id=policy_id,
        organization__in=_user_orgs(request),
    )
    if not _can_access_insurance(request, policy.organization):
        deny_access("You do not have access to this insurance policy.")
    return policy


_INTAKE_UPLOADS = (
    ("driver_license", "Driver license"),
    ("driver_2_license", "Driver license — second driver"),
    ("driver_3_license", "Driver license — third driver"),
    ("driver_4_license", "Driver license — fourth driver"),
    ("vehicle_document", "Registration or title"),
    ("vehicle_2_document", "Registration or title — second vehicle"),
    ("vehicle_3_document", "Registration or title — third vehicle"),
    ("vehicle_4_document", "Registration or title — fourth vehicle"),
)


def _intake_file_ok(uploaded) -> bool:
    name = (getattr(uploaded, "name", "") or "").lower()
    content = (getattr(uploaded, "content_type", "") or "").lower()
    allowed = content.startswith("image/") or content == "application/pdf" or name.endswith(
        (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif", ".pdf")
    )
    size = getattr(uploaded, "size", 0) or 0
    return bool(allowed and size and size <= 12 * 1024 * 1024)


def _save_intake_uploads(request, lead) -> None:
    for field, label in _INTAKE_UPLOADS:
        uploaded = request.FILES.get(field)
        if not uploaded or not _intake_file_ok(uploaded):
            continue
        filename = (getattr(uploaded, "name", "") or "upload").replace("\\", "/").rsplit("/", 1)[-1]
        InsuranceQuoteLeadDocument.objects.create(
            lead=lead,
            file=uploaded,
            original_name=f"{label} — {filename}"[:255],
            uploaded_by=None,
        )


AUTO_QUOTE_LINES = frozenset({"auto_personal", "motor_cycle", "dealer_plates"})
COMMERCIAL_QUOTE_LINES = frozenset({
    "commercial_auto",
    "trucking",
    "contractors",
    "landscaping",
    "business_owners_policy",
    "general_liability",
    "workers_compensation",
    "disability",
})
QUOTE_LINE_LABELS = {"auto": "Auto", "commercial": "Commercial"}


def quote_line_for_type(insurance_type: str) -> str:
    value = (insurance_type or "").strip().lower()
    if value in AUTO_QUOTE_LINES:
        return "auto"
    if value in COMMERCIAL_QUOTE_LINES:
        return "commercial"
    return ""


def _parse_date(raw):
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return timezone.datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@require_http_methods(["GET", "POST"])
def public_insurance_intake(request, portal_token):
    organization = get_object_or_404(Organization, portal_token=portal_token, is_active=True)
    if not organization.has_insurance or not organization.is_public_insurance_intake_enabled:
        return render(
            request,
            "core/public_insurance_intake_disabled.html",
            {"organization": organization, "brand_name": insurance_brand_name(organization)},
        )
    if request.method == "GET":
        return render(
            request,
            "core/public_insurance_intake.html",
            {
                "organization": organization,
                "brand_name": insurance_brand_name(organization),
                "tagline": organization.insurance_intake_tagline,
                "insurance_types": InsurancePolicy.INSURANCE_TYPE_CHOICES,
            },
        )

    name = (request.POST.get("client_name") or "").strip()
    phone = (request.POST.get("phone") or "").strip()
    if not name or not phone:
        messages.error(request, "Name and phone are required.")
        return redirect("public-insurance-intake", portal_token=portal_token)

    requested = (request.POST.get("requested_limits") or "").strip()
    notes = (request.POST.get("notes") or "").strip()
    if requested:
        notes = f"Requested coverages: {requested}\n{notes}".strip()
    lead = InsuranceQuoteLead.objects.create(
        organization=organization,
        client_name=name[:200],
        phone=phone[:30],
        email=(request.POST.get("email") or "").strip(),
        street_address=(request.POST.get("street_address") or "").strip()[:200],
        apartment=(request.POST.get("apartment") or "").strip()[:50],
        city=(request.POST.get("city") or "").strip()[:100],
        state=normalize_state_code(request.POST.get("state") or "NY"),
        zip_code=(request.POST.get("zip_code") or "").strip()[:10],
        insurance_type=(request.POST.get("insurance_type") or "").strip()[:40],
        has_prior=request.POST.get("has_prior") == "on",
        has_accident=request.POST.get("has_accident") == "on",
        is_experienced=request.POST.get("is_experienced") == "on",
        coverage_type=(request.POST.get("coverage_type") or "").strip()[:20],
        vehicle_year=(request.POST.get("vehicle_year") or "").strip()[:4],
        vehicle_make=(request.POST.get("vehicle_make") or "").strip()[:80],
        vehicle_model=(request.POST.get("vehicle_model") or "").strip()[:80],
        vin=(request.POST.get("vin") or "").strip().upper()[:32],
        dl_number=(request.POST.get("dl_number") or "").strip()[:40],
        date_of_birth=_parse_date(request.POST.get("date_of_birth")),
        heard_about=(request.POST.get("heard_about") or "").strip()[:40],
        notes=notes,
        stage=InsuranceQuoteLead.Stage.ASSIGNED,
    )
    for index in range(2, 5):
        driver_name = (request.POST.get(f"driver_{index}_name") or "").strip()
        if not driver_name:
            continue
        InsuranceQuoteLeadDriver.objects.create(
            lead=lead,
            full_name=driver_name[:200],
            dl_number=(request.POST.get(f"driver_{index}_dl") or "").strip()[:40],
            date_of_birth=_parse_date(request.POST.get(f"driver_{index}_dob")),
            sort_order=index,
        )
    for index in range(2, 5):
        make = (request.POST.get(f"vehicle_{index}_make") or "").strip()
        vin = (request.POST.get(f"vehicle_{index}_vin") or "").strip().upper()
        if not make and not vin:
            continue
        InsuranceQuoteLeadVehicle.objects.create(
            lead=lead,
            year=(request.POST.get(f"vehicle_{index}_year") or "").strip()[:4],
            make=make[:80],
            model=(request.POST.get(f"vehicle_{index}_model") or "").strip()[:80],
            vin=vin[:32],
            sort_order=index,
        )
    _save_intake_uploads(request, lead)
    try:
        auto_distribute_lead(lead)
    except Exception:
        pass
    try:
        from .insurance_quote_crm import sync_quote_lead_to_crm

        sync_quote_lead_to_crm(lead)
    except Exception:
        pass
    return render(
        request,
        "core/public_insurance_intake_success.html",
        {
            "organization": organization,
            "brand_name": insurance_brand_name(organization),
            "lead": lead,
        },
    )


@login_required
def quote_worksheet(request, lead_id):
    from . import insurance_area_views

    def extra(organization, membership):
        lead = get_object_or_404(
            InsuranceQuoteLead.objects.prefetch_related("options__company", "additional_drivers", "additional_vehicles"),
            id=lead_id,
            organization=organization,
        )
        if not can_update_assigned_lead(request.user, lead, membership=membership):
            deny_access("You cannot update this lead.")
        companies = list(InsuranceCompany.objects.filter(organization=organization).order_by("name"))
        can_pick = is_owner_or_manager(membership, user=request.user)
        if request.method == "POST" and request.POST.get("desk_action") == "quote_carriers":
            if not can_pick:
                deny_access("Only an owner or manager can choose the carriers the team sees.")
            line = (request.POST.get("quote_line") or "").strip()
            if line not in QUOTE_LINE_LABELS:
                messages.error(request, "Choose Auto or Commercial.")
                return redirect("insurance-quote-worksheet", lead_id=lead.id)
            chosen = {int(value) for value in request.POST.getlist("company_ids") if value.isdigit()}
            field = "quote_for_auto" if line == "auto" else "quote_for_commercial"
            for company in companies:
                setattr(company, field, company.id in chosen)
                company.save(update_fields=[field])
            messages.success(request, f"{QUOTE_LINE_LABELS[line]} carriers saved for the team.")
            return redirect(f"{reverse('insurance-quote-worksheet', args=[lead.id])}?line={line}")
        lead_line = quote_line_for_type(lead.insurance_type)
        requested = (request.GET.get("line") or "").strip()
        picker_line = requested if requested in QUOTE_LINE_LABELS else (lead_line or "auto")
        field = "quote_for_auto" if lead_line == "auto" else "quote_for_commercial"
        shown = [company for company in companies if lead_line and getattr(company, field)]
        options = list(lead.options.select_related("company"))
        cheapest_id = min(options, key=lambda option: option.term_premium).id if options else None
        return {
            "lead": lead,
            "quote_options": options,
            "cheapest_id": cheapest_id,
            "quote_companies": shown,
            "all_quote_companies": companies,
            "quote_line": lead_line,
            "quote_line_label": QUOTE_LINE_LABELS.get(lead_line, ""),
            "picker_line": picker_line,
            "picker_line_label": QUOTE_LINE_LABELS[picker_line],
            "can_pick_carriers": can_pick,
        }

    return insurance_area_views._render_page(
        request,
        "quote-pipeline",
        "core/insurance_area/quote_worksheet.html",
        extra=extra,
        label="Compare quotes",
    )


@login_required
@require_POST
def add_quote_option(request, lead_id):
    lead = get_object_or_404(InsuranceQuoteLead, id=lead_id, organization__in=_user_orgs(request))
    membership = membership_for_org(request.user, lead.organization)
    if not can_update_assigned_lead(request.user, lead, membership=membership):
        deny_access("You cannot update this lead.")
    company = None
    company_id = (request.POST.get("company") or "").strip()
    if company_id.isdigit():
        company = InsuranceCompany.objects.filter(organization=lead.organization, id=int(company_id)).first()
    carrier_name = (request.POST.get("carrier_name") or "").strip()
    if company is None and not carrier_name:
        messages.error(request, "Choose a carrier or type a carrier name.")
        return redirect("insurance-quote-worksheet", lead_id=lead.id)
    premium = request.POST.get("term_premium") or "0"
    try:
        from decimal import Decimal

        term_premium = Decimal(premium)
    except Exception:
        messages.error(request, "Enter a term premium.")
        return redirect("insurance-quote-worksheet", lead_id=lead.id)

    def money(key):
        raw = (request.POST.get(key) or "").strip()
        if not raw:
            return None
        from decimal import Decimal

        try:
            return Decimal(raw)
        except Exception:
            return None

    InsuranceQuoteOption.objects.create(
        lead=lead,
        company=company,
        carrier_name=carrier_name[:120],
        term_premium=term_premium,
        down_payment=money("down_payment"),
        term_months=int(request.POST.get("term_months") or 6) if str(request.POST.get("term_months") or "6").isdigit() else 6,
        bi_limit=(request.POST.get("bi_limit") or "").strip()[:40],
        pd_limit=(request.POST.get("pd_limit") or "").strip()[:40],
        pip_limit=(request.POST.get("pip_limit") or "").strip()[:40],
        um_limit=(request.POST.get("um_limit") or "").strip()[:40],
        comp_deductible=money("comp_deductible"),
        coll_deductible=money("coll_deductible"),
        note=(request.POST.get("note") or "").strip()[:500],
        decision=request.POST.get("decision")
        if request.POST.get("decision") in dict(InsuranceQuoteOption.Decision.choices)
        else InsuranceQuoteOption.Decision.PENDING,
        created_by=request.user,
    )
    if lead.stage == InsuranceQuoteLead.Stage.ASSIGNED:
        lead.stage = InsuranceQuoteLead.Stage.QUOTED
        lead.save(update_fields=["stage", "updated_at"])
    messages.success(request, "Carrier quote saved.")
    return redirect("insurance-quote-worksheet", lead_id=lead.id)


@login_required
def rating_packet(request, lead_id):
    from .insurance_standard_forms import rating_packet_pdf

    lead = get_object_or_404(
        InsuranceQuoteLead.objects.prefetch_related("additional_drivers", "additional_vehicles"),
        id=lead_id,
        organization__in=_user_orgs(request),
    )
    membership = membership_for_org(request.user, lead.organization)
    if not can_update_assigned_lead(request.user, lead, membership=membership):
        deny_access("You cannot update this lead.")
    pdf = rating_packet_pdf(lead)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="rating-packet-{lead.id}.pdf"'
    return response


@login_required
@require_POST
def bind_quote_option_view(request, option_id):
    option = get_object_or_404(
        InsuranceQuoteOption.objects.select_related("lead", "lead__organization", "company"),
        id=option_id,
        lead__organization__in=_user_orgs(request),
    )
    membership = membership_for_org(request.user, option.lead.organization)
    if not can_update_assigned_lead(request.user, option.lead, membership=membership):
        deny_access("You cannot update this lead.")
    try:
        policy = bind_quote_option(option, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("insurance-quote-worksheet", lead_id=option.lead_id)
    messages.success(request, f"Bound {option.carrier_label} on {policy.policy_number}.")
    return redirect("insurance-policy-detail", policy_id=policy.id)


@login_required
@require_POST
def save_policy_desk(request, policy_id):
    policy = _policy_or_deny(request, policy_id)
    action = (request.POST.get("desk_action") or "").strip()
    if action == "coverages":
        save_policy_coverages(policy, request.POST)
        messages.success(request, "Coverages saved.")
    elif action == "vehicle_coverage":
        vehicle = get_object_or_404(InsurancePolicyVehicle, id=request.POST.get("vehicle"), policy=policy)
        from .insurance_desk import _money

        add_vehicle_coverage(
            policy,
            vehicle,
            (request.POST.get("code") or "").strip(),
            request.POST.get("limit_text") or "",
            _money(request.POST.get("deductible")),
        )
        messages.success(request, "Vehicle coverage saved.")
    elif action == "transaction":
        kind = request.POST.get("kind") or ""
        if kind not in dict(InsurancePolicyTransaction.Kind.choices):
            messages.error(request, "Choose a transaction type.")
            return redirect("insurance-policy-detail", policy_id=policy.id)
        from .insurance_desk import _money

        record_transaction(
            policy,
            kind=kind,
            user=request.user,
            effective_date=_parse_date(request.POST.get("effective_date")) or timezone.localdate(),
            new_premium=_money(request.POST.get("new_premium")),
            reason=(request.POST.get("reason") or "").strip(),
            requested_by=(request.POST.get("requested_by") or "").strip(),
            notice_date=_parse_date(request.POST.get("notice_date")),
            note=(request.POST.get("note") or "").strip(),
        )
        messages.success(request, "Transaction recorded.")
    elif action == "confirm_coverages":
        policy.coverages_need_review = False
        policy.save(update_fields=["coverages_need_review", "updated_at"])
        messages.success(request, "Coverages confirmed against the declaration.")
    elif action == "id_card":
        issue_temporary_id_card(policy, request.user, force=True)
        messages.success(request, "Temporary ID card is on the policy documents.")
    elif action == "disclosure":
        issue_compensation_disclosure(policy, request.user)
        messages.success(request, "Compensation disclosure filed on the policy.")
    elif action == "photo":
        status = (request.POST.get("photo_inspection_status") or "").strip()
        allowed = {key for key, _label in InsurancePolicy.PhotoInspection.choices}
        policy.photo_inspection_status = status if status in allowed else ""
        policy.photo_inspection_on = _parse_date(request.POST.get("photo_inspection_on"))
        policy.save(update_fields=["photo_inspection_status", "photo_inspection_on", "updated_at"])
        messages.success(request, "Photo inspection updated.")
    elif action == "driver":
        driver = get_object_or_404(InsurancePolicyDriver, id=request.POST.get("driver"), policy=policy)
        driver.date_of_birth = _parse_date(request.POST.get("date_of_birth"))
        driver.license_number = (request.POST.get("license_number") or "").strip()[:40]
        license_state = (request.POST.get("license_state") or "").strip()
        driver.license_state = normalize_state_code(license_state)[:2] if license_state else ""
        driver.relationship = (request.POST.get("relationship") or "").strip()[:40]
        driver.is_excluded = request.POST.get("is_excluded") == "on"
        driver.sr22_required = request.POST.get("sr22_required") == "on"
        sr22_state = (request.POST.get("sr22_state") or "").strip()
        driver.sr22_state = normalize_state_code(sr22_state)[:2] if sr22_state else ""
        driver.sr22_filed_on = _parse_date(request.POST.get("sr22_filed_on"))
        driver.save()
        messages.success(request, f"{driver.name} updated.")
    elif action == "incident":
        driver = get_object_or_404(InsurancePolicyDriver, id=request.POST.get("driver"), policy=policy)
        kind = request.POST.get("kind") or InsuranceDriverIncident.Kind.ACCIDENT
        if kind not in dict(InsuranceDriverIncident.Kind.choices):
            kind = InsuranceDriverIncident.Kind.ACCIDENT
        InsuranceDriverIncident.objects.create(
            driver=driver,
            kind=kind,
            occurred_on=_parse_date(request.POST.get("occurred_on")),
            description=(request.POST.get("description") or "").strip()[:300],
        )
        messages.success(request, "Incident added to the driver.")
    elif action == "lienholder":
        vehicle = get_object_or_404(InsurancePolicyVehicle, id=request.POST.get("vehicle"), policy=policy)
        dmv_id = (request.POST.get("dmv_vehicle") or "").strip()
        dmv = None
        if dmv_id.isdigit():
            dmv = Vehicle.objects.filter(id=int(dmv_id), client=policy.client).first()
        vehicle.dmv_vehicle = dmv
        vehicle.lienholder_name = (request.POST.get("lienholder_name") or (dmv.lienholder_name if dmv else "") or "").strip()[:200]
        vehicle.lienholder_address = (
            request.POST.get("lienholder_address") or (dmv.lienholder_address if dmv else "") or ""
        ).strip()[:300]
        vehicle.save(update_fields=["dmv_vehicle", "lienholder_name", "lienholder_address"])
        messages.success(request, "Lienholder saved.")
    elif action == "claim":
        loss = _parse_date(request.POST.get("loss_date")) or timezone.localdate()
        vehicle = None
        vehicle_id = (request.POST.get("vehicle") or "").strip()
        if vehicle_id.isdigit():
            vehicle = InsurancePolicyVehicle.objects.filter(id=int(vehicle_id), policy=policy).first()
        claim = open_claim(
            policy,
            loss_date=loss,
            description=(request.POST.get("description") or "").strip(),
            other_party=request.POST.get("other_party") or "",
            police_report=request.POST.get("police_report") or "",
            vehicle=vehicle,
            user=request.user,
        )
        claim.carrier_claim_number = (request.POST.get("carrier_claim_number") or "").strip()[:80]
        status = (request.POST.get("status") or "").strip()
        if status in dict(InsuranceClaim.Status.choices):
            claim.status = status
        claim.save(update_fields=["carrier_claim_number", "status", "updated_at"])
        for upload in request.FILES.getlist("photos"):
            InsuranceClaimPhoto.objects.create(claim=claim, file=upload)
        messages.success(request, "Claim filed on the policy.")
    elif action == "claim_status":
        claim = get_object_or_404(InsuranceClaim, id=request.POST.get("claim"), policy=policy)
        status = (request.POST.get("status") or "").strip()
        if status in dict(InsuranceClaim.Status.choices):
            claim.status = status
        claim.carrier_claim_number = (request.POST.get("carrier_claim_number") or claim.carrier_claim_number).strip()[:80]
        claim.save(update_fields=["status", "carrier_claim_number", "updated_at"])
        messages.success(request, "Claim updated.")
    elif action == "certificate":
        name = (request.POST.get("holder_name") or "").strip()
        if not name:
            messages.error(request, "Certificate holder name is required.")
            return redirect("insurance-policy-detail", policy_id=policy.id)
        holder = holder_for(policy.organization, name, request.POST.get("holder_address") or "")
        certificate = InsuranceCertificate.objects.create(
            policy=policy,
            holder=holder,
            additional_insured=request.POST.get("additional_insured") == "on",
            waiver_of_subrogation=request.POST.get("waiver_of_subrogation") == "on",
            description=(request.POST.get("description") or "").strip()[:500],
            created_by=request.user,
        )
        issue_certificate(certificate, request.user)
        messages.success(request, f"Certificate issued for {holder.name}.")
    elif action == "form":
        from .insurance_standard_forms import FORM_KEYS

        form_key = (request.POST.get("form_key") or "").strip()
        if form_key not in FORM_KEYS:
            messages.error(request, "Choose a form.")
            return redirect("insurance-policy-detail", policy_id=policy.id)
        issued = issue_standard_form(
            policy,
            form_key,
            request.user,
            {
                "holder_name": request.POST.get("holder_name") or "",
                "holder_address": request.POST.get("holder_address") or "",
                "description": request.POST.get("description") or "",
                "loss_date": request.POST.get("loss_date") or "",
                "other_party": request.POST.get("other_party") or "",
                "police_report": request.POST.get("police_report") or "",
                "requested_by": request.POST.get("requested_by") or "",
                "effective_date": request.POST.get("effective_date") or "",
                "additional_insured": request.POST.get("additional_insured") == "on",
                "waiver": request.POST.get("waiver_of_subrogation") == "on",
            },
        )
        messages.success(request, f"{issued.title} is on the policy documents.")
    elif action == "message":
        note = notify_client(policy, request.user, request.POST.get("body") or "")
        if note.startswith("Write") or note.startswith("Saved in the client app. Email"):
            messages.warning(request, note)
        else:
            messages.success(request, note)
    else:
        messages.error(request, "Unknown desk action.")
    return redirect("insurance-policy-detail", policy_id=policy.id)


@login_required
@require_POST
def cancel_policy_nonpay(request, policy_id):
    policy = _policy_or_deny(request, policy_id)
    record_transaction(
        policy,
        kind=InsurancePolicyTransaction.Kind.CANCELLATION,
        user=request.user,
        effective_date=timezone.localdate(),
        reason=InsurancePolicyTransaction.CancelReason.NON_PAY,
        requested_by=InsurancePolicyTransaction.RequestedBy.CARRIER,
        notice_date=timezone.localdate(),
        note="Started from a missed installment on Today.",
    )
    messages.success(request, f"{policy.policy_number} marked cancelled for non-pay.")
    return redirect("insurance-policy-detail", policy_id=policy.id)


@login_required
@require_POST
def import_commission_statement(request):
    organizations = _user_orgs(request)
    org_id = request.POST.get("organization")
    organization = get_object_or_404(organizations, id=org_id)
    membership = membership_for_org(request.user, organization)
    if not can_manage_insurance_finance(request.user, organization, membership=membership):
        deny_access("You do not have permission to import commission statements.")
    upload = request.FILES.get("statement")
    if upload is None:
        messages.error(request, "Choose a statement file. A CSV row is policy number, amount paid.")
        return redirect("insurance-finance")
    company = None
    company_id = (request.POST.get("company") or "").strip()
    if company_id.isdigit():
        company = InsuranceCompany.objects.filter(organization=organization, id=int(company_id)).first()
    statement = import_commission_csv(
        organization,
        upload,
        request.user,
        company=company,
        statement_date=_parse_date(request.POST.get("statement_date")),
    )
    if statement is None:
        messages.error(
            request,
            "No policy amounts were found. Use a CSV of policy number and amount, or a text PDF. A scanned PDF needs a CSV export.",
        )
        return redirect("insurance-finance")
    matched = statement.lines.exclude(status="unmatched").count()
    messages.success(
        request,
        f"Statement imported. {matched} of {statement.lines.count()} rows matched a policy.",
    )
    return redirect("insurance-finance")
