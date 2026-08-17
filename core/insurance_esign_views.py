"""Insurance Space Acrobat-style e-signature views."""

from __future__ import annotations

import json
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import organizations_for_user
from .http import deny_access
from .insurance_esign_models import InsuranceESignEnvelope, new_signer_token
from .insurance_esign_pdf import stamp_envelope_pdf
from .insurance_permissions import is_org_owner, membership_for_org
from .models import Space

MAX_PDF_BYTES = 15 * 1024 * 1024

def _send_esign_request_email(envelope, sign_url: str) -> tuple[bool, str]:
    to_email = (envelope.signer_email or "").strip()
    if not to_email:
        return False, "Enter the signer email address."
    try:
        validate_email(to_email)
    except ValidationError:
        return False, "That signer email address is not valid."
    agency = envelope.organization.name
    subject = f"Please sign: {envelope.title}"[:180]
    text_body = (
        f"Hello {envelope.signer_name or ''}\n\n"
        f"{agency} asked you to electronically sign “{envelope.title}”.\n\n"
        f"Open this link, click each signature box, then Finish & sign:\n{sign_url}\n"
    )
    html_body = render_to_string(
        "core/emails/esign_request.html",
        {
            "signer_name": envelope.signer_name,
            "agency_name": agency,
            "document_title": envelope.title,
            "sign_url": sign_url,
        },
    )
    try:
        message = EmailMultiAlternatives(
            subject,
            text_body,
            settings.DEFAULT_FROM_EMAIL,
            [to_email],
        )
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
        return True, f"Sent to {to_email}."
    except Exception:
        return False, "Could not send the email. Check mail settings, or share the copied link."


def _redirect_esign_tab(org, request=None):
    from django.urls import reverse

    from .policies import redirect_back

    space = Space.objects.filter(organization=org, key="insurance").first()
    if space:
        url = reverse("inventory-detail", kwargs={"inventory_id": space.id}) + "?tab=esign"
        if request is not None:
            return redirect_back(request, url)
        return redirect(url)
    return redirect("spaces-home")


def _org(request):
    orgs = organizations_for_user(request)
    active_id = request.session.get("active_org_id")
    org = orgs.filter(id=active_id).first() if active_id else orgs.first()
    if org is None:
        deny_access("Organization required.")
    return org


def _can_access_insurance(request, org) -> bool:
    membership = membership_for_org(request.user, org)
    if is_org_owner(request.user, org, membership):
        return True
    return bool(membership and membership.is_active and membership.can_deal_with_insurance)


def _require_insurance(request, org):
    if not _can_access_insurance(request, org):
        deny_access("You do not have access to Insurance Space e-signature.")


def _envelope_for_user(request, envelope_id):
    org = _org(request)
    _require_insurance(request, org)
    return get_object_or_404(
        InsuranceESignEnvelope,
        id=envelope_id,
        organization=org,
    )


def _client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return (forwarded or request.META.get("REMOTE_ADDR") or "")[:45]


def _saved_signature_data_url(request, org) -> str:
    membership = membership_for_org(request.user, org)
    if not membership or not membership.signature:
        return ""
    try:
        import base64

        with membership.signature.open("rb") as handle:
            payload = base64.b64encode(handle.read()).decode("ascii")
        return f"data:image/png;base64,{payload}"
    except Exception:
        return ""


def build_esign_tab_context(org):
    envelopes = list(
        InsuranceESignEnvelope.objects.filter(organization=org)
        .select_related("created_by", "signed_by")[:80]
    )
    return {
        "esign_envelopes": envelopes,
        "esign_draft_count": sum(1 for row in envelopes if row.status == InsuranceESignEnvelope.Status.DRAFT),
        "esign_awaiting_count": sum(1 for row in envelopes if row.status == InsuranceESignEnvelope.Status.AWAITING),
        "esign_signed_count": sum(1 for row in envelopes if row.status == InsuranceESignEnvelope.Status.SIGNED),
    }


@login_required
@require_POST
def upload_esign_document(request):
    org = _org(request)
    _require_insurance(request, org)
    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "Choose a PDF to sign.")
        return _redirect_esign_tab(org, request=request)
    name = get_valid_filename(os.path.basename(upload.name or "document.pdf"))
    if not name.lower().endswith(".pdf"):
        messages.error(request, "E-signature only accepts PDF files.")
        return _redirect_esign_tab(org, request=request)
    if upload.size and upload.size > MAX_PDF_BYTES:
        messages.error(request, "That PDF is larger than 15 MB.")
        return _redirect_esign_tab(org, request=request)
    header = upload.read(5)
    upload.seek(0)
    if header != b"%PDF-":
        messages.error(request, "That file is not a valid PDF.")
        return _redirect_esign_tab(org, request=request)
    title = (request.POST.get("title") or "").strip() or os.path.splitext(name)[0]
    envelope = InsuranceESignEnvelope.objects.create(
        organization=org,
        title=title[:200],
        original_file=upload,
        created_by=request.user,
        signer_token=new_signer_token(),
    )
    messages.success(request, "PDF ready. Place signature fields like Acrobat Fill & Sign.")
    return redirect("insurance-esign-editor", envelope_id=envelope.id)


@login_required
def esign_editor(request, envelope_id):
    envelope = _envelope_for_user(request, envelope_id)
    if envelope.status == InsuranceESignEnvelope.Status.VOID:
        messages.error(request, "This envelope was voided.")
        return _redirect_esign_tab(envelope.organization, request=request)
    space = Space.objects.filter(organization=envelope.organization, key="insurance").first()
    return render(
        request,
        "core/insurance_esign_editor.html",
        {
            "envelope": envelope,
            "is_public": False,
            "is_signed": envelope.status == InsuranceESignEnvelope.Status.SIGNED,
            "insurance_space": space,
            "saved_signature_data_url": _saved_signature_data_url(request, envelope.organization),
            "request_sign_url": request.build_absolute_uri(
                f"/sign/{envelope.signer_token}/"
            ),
        },
    )


@login_required
@require_GET
def esign_original_file(request, envelope_id):
    envelope = _envelope_for_user(request, envelope_id)
    if not envelope.original_file:
        raise Http404()
    filename = os.path.basename(envelope.original_file.name) or "document.pdf"
    return FileResponse(envelope.original_file.open("rb"), content_type="application/pdf", filename=filename)


@login_required
@require_GET
def esign_signed_file(request, envelope_id):
    envelope = _envelope_for_user(request, envelope_id)
    if not envelope.signed_file:
        raise Http404()
    filename = os.path.basename(envelope.signed_file.name) or f"signed-{envelope.id}.pdf"
    return FileResponse(
        envelope.signed_file.open("rb"),
        as_attachment=True,
        content_type="application/pdf",
        filename=filename,
    )


def _parse_fields(raw) -> list[dict]:
    if isinstance(raw, list):
        payload = raw
    else:
        try:
            payload = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
    if not isinstance(payload, list):
        return []
    cleaned = []
    for item in payload[:40]:
        if not isinstance(item, dict):
            continue
        cleaned.append({
            "id": str(item.get("id") or "")[:40],
            "type": str(item.get("type") or "signature")[:20],
            "page": item.get("page") or 1,
            "x": item.get("x") or 0,
            "y": item.get("y") or 0,
            "w": item.get("w") or 0.2,
            "h": item.get("h") or 0.06,
            "text": str(item.get("text") or "")[:120],
            "image": str(item.get("image") or "")[:900000],
        })
    return cleaned


def _fields_without_images(fields: list[dict]) -> list[dict]:
    slim = []
    for field in fields:
        row = dict(field)
        row.pop("image", None)
        slim.append(row)
    return slim


def _complete_envelope(envelope, fields, *, signer_name, signer_email, request, signed_user=None):
    envelope.signer_name = (signer_name or envelope.signer_name or "")[:160]
    envelope.signer_email = (signer_email or envelope.signer_email or "")[:254]
    envelope.signed_ip = _client_ip(request)
    envelope.signed_user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:300]
    envelope.signed_by = signed_user
    envelope.signed_at = timezone.now()
    envelope.fields_json = _fields_without_images(fields)
    envelope.audit_json = list(envelope.audit_json or []) + [{
        "event": "signed",
        "at": timezone.localtime().isoformat(),
        "ip": envelope.signed_ip,
        "signer": envelope.signer_name,
    }]
    stamped = stamp_envelope_pdf(envelope, fields)
    envelope.signed_file.save(stamped.name, stamped, save=False)
    envelope.status = InsuranceESignEnvelope.Status.SIGNED
    envelope.save()


@login_required
@require_POST
def apply_esign_document(request, envelope_id):
    envelope = _envelope_for_user(request, envelope_id)
    if envelope.status == InsuranceESignEnvelope.Status.SIGNED:
        return JsonResponse({"ok": True, "redirect": str(request.path)})
    if envelope.status == InsuranceESignEnvelope.Status.VOID:
        return JsonResponse({"ok": False, "error": "This envelope was voided."}, status=400)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid signing data."}, status=400)
    fields = _parse_fields(payload.get("fields"))
    if not fields:
        return JsonResponse({"ok": False, "error": "Place at least one signature or date field."}, status=400)
    signer_name = (payload.get("signer_name") or request.user.get_full_name() or request.user.username).strip()
    signer_email = (payload.get("signer_email") or getattr(request.user, "email", "") or "").strip()
    try:
        _complete_envelope(
            envelope,
            fields,
            signer_name=signer_name,
            signer_email=signer_email,
            request=request,
            signed_user=request.user,
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)[:180] or "Could not stamp this PDF."}, status=400)
    space = Space.objects.filter(organization=envelope.organization, key="insurance").first()
    return JsonResponse({
        "ok": True,
        "download": reverse("insurance-esign-signed", args=[envelope.id]),
        "redirect": (reverse("inventory-detail", kwargs={"inventory_id": space.id}) + "?tab=esign") if space else "/",
    })


@login_required
@require_POST
def request_esign_signature(request, envelope_id):
    envelope = _envelope_for_user(request, envelope_id)
    if envelope.status == InsuranceESignEnvelope.Status.SIGNED:
        messages.info(request, "This document is already signed.")
        return redirect("insurance-esign-editor", envelope_id=envelope.id)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = request.POST
    fields = _parse_fields(payload.get("fields") if isinstance(payload, dict) else request.POST.get("fields"))
    if fields:
        envelope.fields_json = _fields_without_images(fields)
    envelope.signer_name = str(payload.get("signer_name") or request.POST.get("signer_name") or envelope.signer_name)[:160]
    envelope.signer_email = str(payload.get("signer_email") or request.POST.get("signer_email") or envelope.signer_email)[:254]
    if not (envelope.signer_email or "").strip():
        return JsonResponse({"ok": False, "error": "Enter the signer email address to send the request."}, status=400)
    envelope.status = InsuranceESignEnvelope.Status.AWAITING
    envelope.save()
    link = request.build_absolute_uri(reverse("public-esign-sign", args=[envelope.signer_token]))
    emailed, mail_status = _send_esign_request_email(envelope, link)
    envelope.audit_json = list(envelope.audit_json or []) + [{
        "event": "sent",
        "at": timezone.localtime().isoformat(),
        "signer": envelope.signer_name,
        "email": envelope.signer_email,
        "emailed": emailed,
        "mail_status": mail_status,
    }]
    envelope.save(update_fields=["audit_json", "updated_at"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in (request.content_type or ""):
        if not emailed:
            return JsonResponse({"ok": False, "error": mail_status, "link": link, "emailed": False}, status=400)
        return JsonResponse({"ok": True, "link": link, "emailed": True, "message": mail_status})
    if emailed:
        messages.success(request, f"{mail_status} Link: {link}")
    else:
        messages.error(request, mail_status)
    return redirect("insurance-esign-editor", envelope_id=envelope.id)


@login_required
@require_POST
def void_esign_document(request, envelope_id):
    envelope = _envelope_for_user(request, envelope_id)
    envelope.status = InsuranceESignEnvelope.Status.VOID
    envelope.save(update_fields=["status", "updated_at"])
    messages.success(request, "Envelope voided.")
    return _redirect_esign_tab(envelope.organization, request=request)


@require_http_methods(["GET", "POST"])
def public_esign_sign(request, token):
    envelope = get_object_or_404(
        InsuranceESignEnvelope,
        signer_token=token,
    )
    if envelope.status == InsuranceESignEnvelope.Status.VOID:
        return render(request, "core/insurance_esign_public.html", {"missing": True, "message": "This signing link is no longer valid."})
    if envelope.status == InsuranceESignEnvelope.Status.SIGNED:
        return render(
            request,
            "core/insurance_esign_public.html",
            {"envelope": envelope, "already_signed": True},
        )
    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid signing data."}, status=400)
        fields = _parse_fields(payload.get("fields")) or list(envelope.fields_json or [])
        # Merge images from the posted payload onto stored field positions.
        posted_by_id = {str(item.get("id")): item for item in _parse_fields(payload.get("fields"))}
        merged = []
        source = fields if fields else list(envelope.fields_json or [])
        for stored in source:
            row = dict(stored)
            posted = posted_by_id.get(str(row.get("id")))
            if posted:
                if posted.get("image"):
                    row["image"] = posted["image"]
                if posted.get("text"):
                    row["text"] = posted["text"]
            merged.append(row)
        signer_name = (payload.get("signer_name") or envelope.signer_name or "").strip()
        if not signer_name:
            return JsonResponse({"ok": False, "error": "Enter your full name to complete signing."}, status=400)
        has_mark = any(row.get("image") or (row.get("type") in {"signature", "initials"} and row.get("text")) for row in merged)
        if not has_mark:
            return JsonResponse({"ok": False, "error": "Click each signature field and sign before finishing."}, status=400)
        try:
            _complete_envelope(
                envelope,
                merged,
                signer_name=signer_name,
                signer_email=payload.get("signer_email") or envelope.signer_email,
                request=request,
                signed_user=request.user if request.user.is_authenticated else None,
            )
        except Exception:
            return JsonResponse({"ok": False, "error": "Could not complete this signature."}, status=400)
        return JsonResponse({"ok": True})
    return render(
        request,
        "core/insurance_esign_editor.html",
        {
            "envelope": envelope,
            "is_public": True,
            "is_signed": False,
            "saved_signature_data_url": "",
            "request_sign_url": "",
        },
    )


@require_GET
def public_esign_file(request, token):
    envelope = get_object_or_404(InsuranceESignEnvelope, signer_token=token)
    if envelope.status in {InsuranceESignEnvelope.Status.VOID}:
        raise Http404()
    target = envelope.signed_file if envelope.status == InsuranceESignEnvelope.Status.SIGNED and envelope.signed_file else envelope.original_file
    if not target:
        raise Http404()
    return FileResponse(target.open("rb"), content_type="application/pdf", filename="document.pdf")
