"""Insurance policy detail, DEC import, and document upload views."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import organizations_for_user
from .http import deny_access
from .insurance_permissions import (
    can_edit_insurance_policy,
    can_manage_insurance_finance,
    is_org_owner,
    membership_for_org,
)
from .role_permissions import is_owner_or_manager_role
from .insurance_policy_schedule import summarize_insurance_schedule
from .models import (
    InsurancePolicy,
    InsurancePolicyDocument,
    InsurancePolicyInstallment,
    Space,
)
from .policies import redirect_back


def _user_orgs(request):
    return organizations_for_user(request)


def _insurance_space_for_org(org):
    return Space.objects.filter(organization=org, key="insurance").first()


def _can_access_insurance(request, org) -> bool:
    membership = membership_for_org(request.user, org)
    if is_org_owner(request.user, org, membership):
        return True
    if membership and is_owner_or_manager_role(membership.role):
        return True
    return bool(membership and membership.is_active and membership.can_deal_with_insurance)


def _redirect_insurance_space(org, request=None):
    return redirect("insurance-policies")


@login_required
def insurance_policy_detail(request, policy_id):
    organizations = _user_orgs(request)
    policy = get_object_or_404(
        InsurancePolicy.objects.select_related(
            "client", "insurance_company", "added_by", "organization"
        ),
        id=policy_id,
        organization__in=organizations,
    )
    if not _can_access_insurance(request, policy.organization):
        deny_access("You do not have access to this insurance policy.")

    schedule = summarize_insurance_schedule(policy)
    documents = list(policy.documents.all()[:50])
    policy_vehicles = list(policy.policy_vehicles.all())
    policy_drivers = list(policy.policy_drivers.all())
    space = _insurance_space_for_org(policy.organization)
    membership = membership_for_org(request.user, policy.organization)
    is_owner = is_org_owner(request.user, policy.organization, membership)
    can_edit_policy = can_edit_insurance_policy(
        request.user, policy, membership=membership
    )

    overview_named_insured = (
        policy.named_insured
        or (policy.client.name if policy.client_id else "")
        or "—"
    )
    overview_address = policy.insured_address or (
        getattr(policy.client, "full_address", "") if policy.client_id else ""
    ) or "—"

    from .insurance_producers import build_policy_ledger

    policy.producer_ledger = build_policy_ledger(policy) if policy.producer_id else None

    from .insurance_renewal_models import InsuranceRenewal
    from .insurance_renewals import renewal_history

    renewal_card = (
        InsuranceRenewal.objects.filter(policy=policy).select_related("assigned_to", "new_policy").first()
    )
    renewal_chain = renewal_history(policy)
    renewal_days_left = (
        (renewal_card.expiration_date - timezone.localdate()).days if renewal_card else None
    )

    from .insurance_desk import coverage_form_rows
    from .insurance_desk_models import InsurancePolicyTransaction
    from .insurance_standard_forms import FORMS
    from .models import Vehicle

    return render(
        request,
        "core/insurance_policy_detail.html",
        {
            "policy": policy,
            "organization": policy.organization,
            "insurance_space": space,
            "schedule": schedule,
            "installments": schedule["installments"],
            "documents": documents,
            "policy_vehicles": policy_vehicles,
            "policy_drivers": policy_drivers,
            "overview_named_insured": overview_named_insured,
            "overview_address": overview_address,
            "is_owner": is_owner,
            "can_edit_policy": can_edit_policy,
            "can_manage_finance": can_manage_insurance_finance(
                request.user,
                policy.organization,
                membership=membership,
                is_owner=is_owner,
            ),
            "renewal_card": renewal_card,
            "renewal_chain": renewal_chain if len(renewal_chain) > 1 else [],
            "renewal_days_left": renewal_days_left,
            "renewal_days_overdue": -renewal_days_left if renewal_days_left and renewal_days_left < 0 else 0,
            "coverage_rows": coverage_form_rows(policy),
            "vehicle_coverages": list(policy.coverages.filter(vehicle__isnull=False).select_related("vehicle")),
            "policy_transactions": list(policy.transactions.all()[:30]),
            "transaction_kinds": InsurancePolicyTransaction.Kind.choices,
            "cancel_reasons": InsurancePolicyTransaction.CancelReason.choices,
            "requested_by_choices": InsurancePolicyTransaction.RequestedBy.choices,
            "policy_claims": list(policy.claims.prefetch_related("photos")[:20]),
            "policy_certificates": list(policy.certificates.select_related("holder")[:20]),
            "standard_forms": FORMS,
            "issued_forms": list(policy.issued_forms.all()[:20]),
            "dmv_vehicles": list(Vehicle.objects.filter(client=policy.client).order_by("-id")[:30]) if policy.client_id else [],
            "photo_inspection_choices": InsurancePolicy.PhotoInspection.choices,
        },
    )


@login_required
@require_POST
def import_insurance_dec_page(request, space_id):
    """Create a new insurance policy by importing an Integon/NYAIP DEC PDF."""
    space = get_object_or_404(Space, id=space_id, key="insurance")
    organizations = _user_orgs(request)
    if space.organization_id not in set(organizations.values_list("id", flat=True)):
        deny_access("Access denied.")
    if not _can_access_insurance(request, space.organization):
        messages.error(request, "You do not have permission to import insurance policies.")
        return redirect("insurance-policies")

    upload = request.FILES.get("dec_page")
    if not upload:
        messages.error(request, "Please choose a declaration page PDF.")
        return redirect("insurance-policies")
    if not upload.name.lower().endswith(".pdf"):
        messages.error(request, "Declaration page must be a PDF file.")
        return redirect("insurance-policies")

    from .insurance_dec_import import (
        DecPageParseError,
        create_policy_from_parsed_dec,
        parse_insurance_dec_page,
    )
    from .client_matching import DuplicateClientError

    try:
        parsed = parse_insurance_dec_page(upload)
    except DecPageParseError as exc:
        messages.error(request, str(exc))
        return redirect("insurance-policies")

    if InsurancePolicy.objects.filter(
        organization=space.organization,
        policy_number=parsed.policy_number,
    ).exists():
        messages.error(
            request,
            f"Policy {parsed.policy_number} already exists. Open it and use "
            f'"Update from Dec Page" on the policy detail.',
        )
        return redirect("insurance-policies")

    upload.seek(0)
    try:
        policy = create_policy_from_parsed_dec(
            organization=space.organization,
            parsed=parsed,
            user=request.user,
            dec_file=upload,
        )
    except DuplicateClientError as exc:
        messages.error(request, exc.message)
        return redirect("insurance-policies")
    except DecPageParseError as exc:
        messages.error(request, str(exc))
        return redirect("insurance-policies")

    if parsed.parse_warnings:
        messages.warning(request, "; ".join(parsed.parse_warnings))
    messages.success(
        request,
        f"Imported {policy.policy_number} from DEC"
        + (f" — {parsed.named_insured}" if parsed.named_insured else "")
        + ".",
    )
    return redirect("insurance-policy-detail", policy_id=policy.id)


@login_required
@require_POST
def import_insurance_dec_to_policy(request, policy_id):
    """Refresh an existing insurance policy from a DEC PDF (always stores the file)."""
    organizations = _user_orgs(request)
    policy = get_object_or_404(
        InsurancePolicy,
        id=policy_id,
        organization__in=organizations,
    )
    if not _can_access_insurance(request, policy.organization):
        deny_access("Permission denied.")
    membership = membership_for_org(request.user, policy.organization)
    if not can_edit_insurance_policy(request.user, policy, membership=membership):
        messages.error(request, "You can only update policies you added.")
        return redirect(reverse("insurance-policy-detail", args=[policy.id]))

    upload = request.FILES.get("dec_page")
    detail_url = reverse("insurance-policy-detail", args=[policy.id])
    if not upload:
        messages.error(request, "Please choose a declaration page PDF.")
        return redirect(detail_url)
    if not upload.name.lower().endswith(".pdf"):
        messages.error(request, "Declaration page must be a PDF file.")
        return redirect(detail_url)

    from .insurance_dec_import import (
        DecPageParseError,
        apply_parsed_dec_to_insurance_policy,
        parse_insurance_dec_page,
    )

    try:
        parsed = parse_insurance_dec_page(upload)
    except DecPageParseError as exc:
        # Still store the PDF so it can be viewed on the detail page.
        upload.seek(0)
        InsurancePolicyDocument.objects.create(
            policy=policy,
            document_type=InsurancePolicyDocument.DocumentType.DECLARATION_PAGE,
            title=f"Declaration Page — {upload.name}",
            file=upload,
            uploaded_by=request.user,
        )
        messages.warning(
            request,
            f"DEC PDF saved, but fields were not auto-updated: {exc}",
        )
        return redirect(detail_url)

    if parsed.policy_number and parsed.policy_number.upper() != policy.policy_number.upper():
        messages.error(
            request,
            f"DEC policy number ({parsed.policy_number}) does not match this policy "
            f"({policy.policy_number}).",
        )
        return redirect(detail_url)

    upload.seek(0)
    apply_parsed_dec_to_insurance_policy(
        policy,
        parsed,
        user=request.user,
        dec_file=upload,
        replace_schedule=True,
    )
    if parsed.parse_warnings:
        messages.warning(request, "; ".join(parsed.parse_warnings))
    messages.success(request, f"Updated {policy.policy_number} from declaration page.")
    return redirect(detail_url)


@login_required
@require_POST
def upload_insurance_policy_document(request, policy_id):
    organizations = _user_orgs(request)
    policy = get_object_or_404(
        InsurancePolicy,
        id=policy_id,
        organization__in=organizations,
    )
    if not _can_access_insurance(request, policy.organization):
        deny_access("Permission denied.")

    detail_url = reverse("insurance-policy-detail", args=[policy.id])
    upload = request.FILES.get("document")
    if not upload:
        messages.error(request, "Please select a file to upload.")
        return redirect(detail_url)

    doc_type = request.POST.get("document_type") or InsurancePolicyDocument.DocumentType.OTHER
    valid_types = {c.value for c in InsurancePolicyDocument.DocumentType}
    if doc_type not in valid_types:
        doc_type = InsurancePolicyDocument.DocumentType.OTHER
    title = (request.POST.get("title") or "").strip() or upload.name

    InsurancePolicyDocument.objects.create(
        policy=policy,
        document_type=doc_type,
        title=title[:200],
        file=upload,
        uploaded_by=request.user,
    )
    messages.success(request, "Document uploaded.")
    return redirect(detail_url)


@login_required
@require_POST
def toggle_insurance_installment_paid(request, installment_id):
    organizations = _user_orgs(request)
    row = get_object_or_404(
        InsurancePolicyInstallment.objects.select_related("policy"),
        id=installment_id,
        policy__organization__in=organizations,
    )
    if not _can_access_insurance(request, row.policy.organization):
        deny_access("Permission denied.")
    row.is_paid = not row.is_paid
    row.save(update_fields=["is_paid"])
    messages.success(
        request,
        f"Marked {row.display_number} as {'paid' if row.is_paid else 'unpaid'}.",
    )
    return redirect_back(request, reverse("insurance-policy-detail", args=[row.policy_id]))
