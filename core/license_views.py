"""Licenses space: state folders, license records, and document uploads."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .agency_licenses import US_STATE_NAMES, US_STATES, license_status, parse_reminder_days
from .http import deny_access
from .models import AgencyLicense, AgencyLicenseDocument, AgencyLicenseFolder, OrganizationMembership, Space
from .space_access import require_space_access
from .views import _get_user_organizations


def _resolve(request, space_id=None, card=None):
    organizations = _get_user_organizations(request)
    if card is None:
        card = get_object_or_404(Space, id=space_id, organization__in=organizations, key="licenses")
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


def _url(card, folder_id=None, license_id=None):
    from django.urls import reverse

    url = reverse("inventory-detail", kwargs={"inventory_id": card.id})
    params = []
    if folder_id:
        params.append(f"folder={folder_id}")
    if license_id:
        params.append(f"license={license_id}")
    if params:
        url += "?" + "&".join(params)
    return url


def build_licenses_space_context(request, card, is_owner, membership):
    folders = list(AgencyLicenseFolder.objects.filter(space=card))
    used_codes = {folder.state_code for folder in folders}
    folder_id = (request.GET.get("folder") or "").strip()
    license_id = (request.GET.get("license") or "").strip()
    selected_folder = None
    selected_license = None
    licenses = []
    if folder_id.isdigit():
        selected_folder = next((folder for folder in folders if folder.id == int(folder_id)), None)
    if selected_folder:
        licenses = list(
            AgencyLicense.objects.filter(folder=selected_folder).prefetch_related("documents")
        )
        for row in licenses:
            row.renewal = license_status(row)
        if license_id.isdigit():
            selected_license = next((row for row in licenses if row.id == int(license_id)), None)
    all_licenses = AgencyLicense.objects.filter(space=card, is_active=True)
    due_count = 0
    for lic in all_licenses:
        if license_status(lic)["needs_alert"]:
            due_count += 1
    return {
        "card": card,
        "is_owner": is_owner,
        "can_manage_licenses": bool(is_owner or membership),
        "folders": folders,
        "available_states": [pair for pair in US_STATES if pair[0] not in used_codes],
        "selected_folder": selected_folder,
        "licenses": licenses,
        "selected_license": selected_license,
        "due_count": due_count,
        "license_count": all_licenses.count(),
    }


@login_required
@require_POST
def save_license_folder(request, space_id):
    card, is_owner, membership = _resolve(request, space_id=space_id)
    if not (is_owner or membership):
        deny_access("You cannot manage licenses.")
    code = (request.POST.get("state_code") or "").strip().upper()
    name = US_STATE_NAMES.get(code)
    if not name:
        messages.error(request, "Choose a US state.")
        return redirect(_url(card))
    AgencyLicenseFolder.objects.get_or_create(
        organization=card.organization,
        state_code=code,
        defaults={"space": card, "state_name": name},
    )
    messages.success(request, f"{name} added.")
    folder = AgencyLicenseFolder.objects.get(organization=card.organization, state_code=code)
    return redirect(_url(card, folder_id=folder.id))


@login_required
@require_POST
def save_agency_license(request, space_id):
    card, is_owner, membership = _resolve(request, space_id=space_id)
    if not (is_owner or membership):
        deny_access("You cannot manage licenses.")
    folder_id = (request.POST.get("folder_id") or "").strip()
    folder = get_object_or_404(AgencyLicenseFolder, id=folder_id, space=card)
    title = (request.POST.get("title") or "").strip()
    if not title:
        messages.error(request, "License name is required.")
        return redirect(_url(card, folder_id=folder.id))
    from datetime import datetime

    raw_date = (request.POST.get("expiration_date") or "").strip()
    expiration = None
    if raw_date:
        try:
            expiration = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            expiration = None
    offsets = parse_reminder_days(request.POST.get("reminder_days"))
    reminder = ",".join(str(day) for day in sorted(offsets, reverse=True))
    license_id = (request.POST.get("license_id") or "").strip()
    if license_id.isdigit():
        lic = get_object_or_404(AgencyLicense, id=int(license_id), folder=folder)
    else:
        lic = AgencyLicense(organization=card.organization, space=card, folder=folder, created_by=request.user)
    lic.title = title[:180]
    lic.license_number = (request.POST.get("license_number") or "").strip()[:80]
    lic.holder_name = (request.POST.get("holder_name") or "").strip()[:180]
    lic.expiration_date = expiration
    lic.reminder_days = reminder
    lic.notes = (request.POST.get("notes") or "").strip()
    lic.is_active = request.POST.get("is_active") != "off"
    lic.save()
    from .agency_licenses import sync_agency_license_alerts

    sync_agency_license_alerts(lic)
    messages.success(request, "License saved.")
    return redirect(_url(card, folder_id=folder.id, license_id=lic.id))


@login_required
@require_POST
def delete_agency_license(request, license_id):
    lic = get_object_or_404(AgencyLicense.objects.select_related("space", "folder"), id=license_id)
    card, is_owner, membership = _resolve(request, card=lic.space)
    if not (is_owner or membership):
        deny_access("You cannot manage licenses.")
    folder_id = lic.folder_id
    lic.delete()
    messages.success(request, "License removed.")
    return redirect(_url(card, folder_id=folder_id))


@login_required
@require_POST
def upload_agency_license_document(request, license_id):
    lic = get_object_or_404(AgencyLicense.objects.select_related("space", "folder"), id=license_id)
    card, is_owner, membership = _resolve(request, card=lic.space)
    if not (is_owner or membership):
        deny_access("You cannot manage licenses.")
    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "Choose a file or photo to upload.")
        return redirect(_url(card, folder_id=lic.folder_id, license_id=lic.id))
    title = (request.POST.get("title") or upload.name or "License document").strip()[:180]
    AgencyLicenseDocument.objects.create(
        organization=lic.organization,
        license=lic,
        title=title,
        file=upload,
        uploaded_by=request.user,
    )
    messages.success(request, "Document uploaded.")
    return redirect(_url(card, folder_id=lic.folder_id, license_id=lic.id))


@login_required
@require_POST
def delete_agency_license_document(request, document_id):
    doc = get_object_or_404(
        AgencyLicenseDocument.objects.select_related("license", "license__space", "license__folder"),
        id=document_id,
    )
    lic = doc.license
    card, is_owner, membership = _resolve(request, card=lic.space)
    if not (is_owner or membership):
        deny_access("You cannot manage licenses.")
    doc.file.delete(save=False)
    doc.delete()
    messages.success(request, "Document removed.")
    return redirect(_url(card, folder_id=lic.folder_id, license_id=lic.id))
