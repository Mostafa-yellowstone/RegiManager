"""Public intake portal and staff approval workflows."""

import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .access import organizations_for_user
from .forms import ClientIntakeForm
from .models import (
    Client,
    ClientIntake,
    ClientNote,
    CustomServiceType,
    Organization,
    Referral,
    ServiceDocument,
    Vehicle,
)
from .ratelimit import client_ip


def _check_intake_post_rate(request):
    import sys

    from django.conf import settings

    if settings.DEBUG or "test" in sys.argv:
        return True
    raw = f"intake_post:{client_ip(request)}"
    cache_key = "rl:" + hashlib.sha256(raw.encode()).hexdigest()[:32]
    count = cache.get(cache_key, 0)
    if count >= 5:
        return False
    cache.set(cache_key, count + 1, timeout=60)
    return True


@ensure_csrf_cookie
def public_intake_portal(request, portal_token=None):
    """Unified intake portal. Shows the form when a valid token is provided."""
    token = portal_token or request.GET.get("portal_token")
    if not token:
        return render(request, "core/public_intake_start.html")

    organization = get_object_or_404(Organization, portal_token=token, is_active=True)
    if not organization.is_public_intake_enabled:
        return render(
            request,
            "core/public_intake_disabled.html",
            {"organization": organization},
        )

    standard_services = [
        {"key": "registration_title", "label": "New Registration & Title"},
        {"key": "title_only", "label": "Title Only (No Plates)"},
        {"key": "transfer", "label": "Transfer Plates"},
        {"key": "renewal", "label": "Registration Renewal"},
        {"key": "duplicate_title", "label": "Duplicate Title"},
        {"key": "plate_surrender", "label": "Plate Surrender"},
    ]
    custom_services = CustomServiceType.objects.filter(organization=organization)

    if request.method == "POST":
        if not _check_intake_post_rate(request):
            messages.error(request, "Too many submissions. Please wait a minute and try again.")
            form = ClientIntakeForm(request.POST, request.FILES, organization=organization)
        else:
            form = ClientIntakeForm(request.POST, request.FILES, organization=organization)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        intake = form.save(commit=False)
                        intake.organization = organization
                        intake.requested_services = request.POST.getlist("services")
                        form.apply_partner_and_note_to_instance(intake, request.POST)
                        intake.save()
                    return redirect(f"/intake/success/?portal_token={token}")
                except Exception:
                    messages.error(
                        request,
                        "An error occurred while saving your application. Please try again.",
                    )
    else:
        form = ClientIntakeForm(organization=organization)

    dealer_partners = Referral.objects.filter(organization=organization).order_by("name")

    return render(
        request,
        "core/public_intake_form.html",
        {
            "form": form,
            "organization": organization,
            "standard_services": standard_services,
            "custom_services": custom_services,
            "portal_token": token,
            "dealer_partners": dealer_partners,
            "vehicle_types": Vehicle.VEHICLE_TYPES,
            "body_types": Vehicle.BODY_TYPES,
            "fuel_types": Vehicle.FUEL_TYPES,
        },
    )


def public_intake_success(request):
    """Confirmation page after successful submission."""
    token = request.GET.get("portal_token")
    organization = None
    if token:
        organization = Organization.objects.filter(portal_token=token).first()
    return render(request, "core/public_intake_success.html", {"organization": organization})


@login_required
@require_POST
def approve_intake(request, intake_id):
    from .intake_approval import (
        find_existing_client_for_intake,
        intake_vehicle_for_client,
        vehicle_defaults_from_intake,
    )
    from .intake_referral import apply_intake_referral_to_client

    with transaction.atomic():
        intake = get_object_or_404(
            ClientIntake.objects.select_for_update(),
            id=intake_id,
            organization__in=organizations_for_user(request),
        )

        if intake.status != ClientIntake.Status.PENDING:
            messages.error(request, "This intake is already being processed or has been completed.")
            return redirect("dashboard")

        client = find_existing_client_for_intake(intake)
        existing_vehicle = intake_vehicle_for_client(intake, client) if client else None

        if existing_vehicle and client:
            intake.status = ClientIntake.Status.REJECTED
            intake.processed_by = request.user
            intake.processed_at = timezone.now()
            if not intake.additional_data:
                intake.additional_data = {}
            intake.additional_data["rejection_reason"] = (
                "Exact duplicate of existing vehicle in client profile."
            )
            intake.save()
            messages.warning(
                request,
                f"Intake rejected: VIN {intake.vin} already exists for {client.name}.",
            )
            return redirect("dashboard")

        intake.status = ClientIntake.Status.APPROVED
        intake.processed_by = request.user
        intake.processed_at = timezone.now()
        intake.save()

        if not client:
            client = Client.objects.create(
                organization=intake.organization,
                first_name=intake.first_name,
                last_name=intake.last_name,
                dob=intake.dob,
                middle_name=intake.middle_name,
                email=intake.email,
                phone_number=intake.phone_number,
                gender=intake.gender,
                driver_license=intake.driver_license,
                building_no=intake.building_no,
                street_address=intake.street_address,
                apartment=intake.apartment,
                city=intake.city,
                state=intake.state,
                zip_code=intake.zip_code,
                county=intake.county,
                residence_building_no=intake.residence_building_no
                if not intake.residence_address_same
                else "",
                residence_street_address=intake.residence_street_address
                if not intake.residence_address_same
                else "",
                residence_apartment=intake.residence_apartment
                if not intake.residence_address_same
                else "",
                residence_city=intake.residence_city if not intake.residence_address_same else "",
                residence_zip_code=intake.residence_zip_code
                if not intake.residence_address_same
                else "",
                residence_county=intake.residence_county
                if not intake.residence_address_same
                else "",
                is_commercial=intake.is_commercial,
                business_name=intake.business_name,
                business_ein=intake.business_ein,
                source=intake.source,
            )
        else:
            client.source = intake.source
            client.save(update_fields=["source"])

        apply_intake_referral_to_client(intake, client)

        note_text = (intake.intake_note or "").strip()
        if note_text:
            ClientNote.objects.create(
                client=client,
                content=f"[Intake portal] {note_text}",
                created_by=request.user,
            )

        vehicle, _v_created = Vehicle.objects.update_or_create(
            client=client,
            vin=intake.vin,
            defaults=vehicle_defaults_from_intake(intake),
        )

        if intake.insurance_id_card:
            import os

            intake.insurance_id_card.open("rb")
            try:
                file_bytes = intake.insurance_id_card.read()
            finally:
                intake.insurance_id_card.close()
            filename = os.path.basename(intake.insurance_id_card.name)
            doc = ServiceDocument(
                vehicle=vehicle,
                document_type="insurance_id",
            )
            doc.file.save(filename, ContentFile(file_bytes), save=True)

    messages.success(
        request,
        f"Intake approved! Client and vehicle profile created for {client.name}. "
        f"Start a transaction from the profile whenever ready.",
    )
    return redirect("client-detail", client_id=client.id)


@login_required
@require_POST
def reject_intake(request, intake_id):
    intake = get_object_or_404(
        ClientIntake,
        id=intake_id,
        organization__in=organizations_for_user(request),
    )
    intake.status = ClientIntake.Status.REJECTED
    intake.processed_at = timezone.now()
    intake.processed_by = request.user
    intake.save()
    messages.warning(request, "Intake submission has been rejected.")
    return redirect("dashboard")
