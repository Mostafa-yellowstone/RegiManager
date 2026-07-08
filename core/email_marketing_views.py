"""Email Marketing: list cards, encapsulated CRM, HTML campaigns, bulk send."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .access import organizations_for_user
from .email_marketing_import import parse_contact_import_file
from .email_marketing_permissions import can_manage_email_marketing
from .email_marketing_personalize import render_campaign_html
from .email_marketing_tasks import send_email_campaign_batch
from .http import deny_access
from .models import (
    EmailCampaign,
    EmailCampaignBatch,
    EmailCampaignRecipient,
    EmailMarketingAsset,
    EmailMarketingContact,
    EmailMarketingList,
    OrganizationMembership,
)
from .us_states import US_STATES


def _membership(user, organization):
    return OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
    ).first()


def _resolve_org(request):
    organizations = organizations_for_user(request)
    active_org_id = request.session.get("active_org_id")
    if active_org_id:
        org = organizations.filter(id=active_org_id).first()
    else:
        org = organizations.first()
    return org, organizations


def _require_marketing_access(request, organization):
    membership = _membership(request.user, organization)
    if not can_manage_email_marketing(request.user, organization, membership=membership):
        deny_access("You do not have permission to manage email marketing.")
    return membership


def _filter_contacts(queryset, request):
    q = (request.GET.get("q") or request.POST.get("q") or "").strip()
    state = (request.GET.get("state") or request.POST.get("state") or "").strip().upper()
    city = (request.GET.get("city") or request.POST.get("city") or "").strip()
    zip_code = (request.GET.get("zip_code") or request.POST.get("zip_code") or "").strip()
    has_email = (request.GET.get("has_email") or request.POST.get("has_email") or "").strip()

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
            | Q(city__icontains=q)
        )
    if state:
        queryset = queryset.filter(state__iexact=state)
    if city:
        queryset = queryset.filter(city__icontains=city)
    if zip_code:
        queryset = queryset.filter(zip_code__icontains=zip_code)
    if has_email == "1":
        queryset = queryset.exclude(email="").exclude(email__isnull=True)
    return queryset


@login_required
def email_marketing_home(request):
    org, organizations = _resolve_org(request)
    if not org:
        return render(request, "core/email_marketing/no_org.html")

    _require_marketing_access(request, org)
    lists = EmailMarketingList.objects.filter(organization=org).prefetch_related("contacts", "campaigns")

    if request.method == "POST" and request.POST.get("action") == "create_list":
        name = (request.POST.get("name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        accent_color = (request.POST.get("accent_color") or "#2563eb").strip()
        if not accent_color.startswith("#") or len(accent_color) != 7:
            accent_color = "#2563eb"
        if name:
            if EmailMarketingList.objects.filter(organization=org, name=name).exists():
                messages.error(request, f'A list named "{name}" already exists for this organization.')
            else:
                try:
                    EmailMarketingList.objects.create(
                        organization=org,
                        name=name,
                        description=description,
                        accent_color=accent_color,
                        created_by=request.user,
                    )
                    messages.success(request, f'Created marketing list "{name}".')
                except IntegrityError:
                    messages.error(request, f'A list named "{name}" already exists for this organization.')
                except Exception:
                    messages.error(request, "Could not create the list. Please try again.")
        else:
            messages.error(request, "List name is required.")
        return redirect("email-marketing-home")

    return render(
        request,
        "core/email_marketing/home.html",
        {
            "active_org": org,
            "marketing_lists": lists,
            "organizations": organizations,
        },
    )


@login_required
def email_marketing_workspace(request, list_id):
    org, organizations = _resolve_org(request)
    if not org:
        return render(request, "core/email_marketing/no_org.html")

    _require_marketing_access(request, org)
    marketing_list = get_object_or_404(EmailMarketingList, pk=list_id, organization=org)
    tab = (request.GET.get("tab") or "crm").strip()
    campaign_id = request.GET.get("campaign")

    contacts_qs = _filter_contacts(marketing_list.contacts.all(), request)
    paginator = Paginator(contacts_qs, 15)
    contacts_page = paginator.get_page(request.GET.get("page"))

    campaigns = marketing_list.campaigns.all()
    active_campaign = None
    if campaign_id:
        active_campaign = campaigns.filter(pk=campaign_id).first()
    if not active_campaign:
        active_campaign = campaigns.filter(status=EmailCampaign.Status.DRAFT).first()
    if not active_campaign:
        active_campaign = campaigns.first()

    batches = []
    if active_campaign:
        batches = active_campaign.batches.all()[:20]

    assets = marketing_list.assets.all()[:24]
    preview_contacts = marketing_list.contacts.exclude(email="").order_by("name")[:50]
    preview_html = ""
    if active_campaign:
        sample_contact = contacts_qs.exclude(email="").first()
        preview_html = render_campaign_html(
            active_campaign.html_content,
            active_campaign.css_content,
            sample_contact,
        )

    return render(
        request,
        "core/email_marketing/workspace.html",
        {
            "active_org": org,
            "organizations": organizations,
            "marketing_list": marketing_list,
            "tab": tab,
            "contacts_page": contacts_page,
            "campaigns": campaigns,
            "active_campaign": active_campaign,
            "batches": batches,
            "assets": assets,
            "preview_contacts": preview_contacts,
            "preview_html": preview_html,
            "us_states": US_STATES,
            "filter_q": request.GET.get("q", ""),
            "filter_state": request.GET.get("state", ""),
            "filter_city": request.GET.get("city", ""),
            "filter_zip": request.GET.get("zip_code", ""),
            "filter_has_email": request.GET.get("has_email", ""),
        },
    )


@login_required
@require_POST
def email_marketing_save_contact(request, list_id):
    org, _ = _resolve_org(request)
    _require_marketing_access(request, org)
    marketing_list = get_object_or_404(EmailMarketingList, pk=list_id, organization=org)

    contact_id = request.POST.get("contact_id")
    fields = {
        "name": (request.POST.get("name") or "").strip(),
        "address_line1": (request.POST.get("address_line1") or "").strip(),
        "address_line2": (request.POST.get("address_line2") or "").strip(),
        "address_line3": (request.POST.get("address_line3") or "").strip(),
        "city": (request.POST.get("city") or "").strip(),
        "state": (request.POST.get("state") or "").strip().upper()[:2],
        "zip_code": (request.POST.get("zip_code") or "").strip(),
        "phone": (request.POST.get("phone") or "").strip(),
        "email": (request.POST.get("email") or "").strip(),
        "website": (request.POST.get("website") or "").strip(),
        "notes": (request.POST.get("notes") or "").strip(),
    }
    if not fields["name"]:
        messages.error(request, "Contact name is required.")
        return redirect(f"{reverse('email-marketing-workspace', args=[list_id])}?tab=crm")

    if contact_id:
        contact = get_object_or_404(EmailMarketingContact, pk=contact_id, marketing_list=marketing_list)
        for key, value in fields.items():
            setattr(contact, key, value)
        contact.save()
        messages.success(request, "Contact updated.")
    else:
        EmailMarketingContact.objects.create(organization=org, marketing_list=marketing_list, **fields)
        messages.success(request, "Contact added.")

    return redirect(f"{reverse('email-marketing-workspace', args=[list_id])}?tab=crm")


@login_required
@require_POST
def email_marketing_delete_contact(request, list_id, contact_id):
    org, _ = _resolve_org(request)
    _require_marketing_access(request, org)
    marketing_list = get_object_or_404(EmailMarketingList, pk=list_id, organization=org)
    contact = get_object_or_404(EmailMarketingContact, pk=contact_id, marketing_list=marketing_list)
    contact.delete()
    messages.success(request, "Contact deleted.")
    return redirect(f"{reverse('email-marketing-workspace', args=[list_id])}?tab=crm")


@login_required
@require_POST
def email_marketing_import_contacts(request, list_id):
    org, _ = _resolve_org(request)
    _require_marketing_access(request, org)
    marketing_list = get_object_or_404(EmailMarketingList, pk=list_id, organization=org)
    upload = request.FILES.get("import_file")
    if not upload:
        messages.error(request, "Choose a CSV or Excel file to import.")
        return redirect(f"{reverse('email-marketing-workspace', args=[list_id])}?tab=crm")

    try:
        result = parse_contact_import_file(upload)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('email-marketing-workspace', args=[list_id])}?tab=crm")

    if not result.contacts:
        if result.headers:
            mapped_pairs = [
                f"{header} → {field}"
                for header, field in result.column_mapping.items()
            ]
            mapped_text = ", ".join(mapped_pairs) if mapped_pairs else "no recognizable columns"
            messages.error(
                request,
                f"Imported 0 contacts from {result.total_rows} row(s). "
                f"File columns: {', '.join(result.headers)}. "
                f"Matched: {mapped_text}. "
                f"Include at least a Name, Email, or Phone column.",
            )
        else:
            messages.error(request, "Imported 0 contacts. The file looks empty or is missing a header row.")
        return redirect(f"{reverse('email-marketing-workspace', args=[list_id])}?tab=crm")

    created = 0
    with transaction.atomic():
        for row in result.contacts:
            EmailMarketingContact.objects.create(
                organization=org,
                marketing_list=marketing_list,
                **row,
            )
            created += 1
    messages.success(
        request,
        f"Imported {created} contact(s) from {result.total_rows} row(s)"
        + (f" ({result.skipped_rows} skipped)." if result.skipped_rows else "."),
    )
    return redirect(f"{reverse('email-marketing-workspace', args=[list_id])}?tab=crm")


@login_required
@require_POST
def email_marketing_save_campaign(request, list_id):
    org, _ = _resolve_org(request)
    _require_marketing_access(request, org)
    marketing_list = get_object_or_404(EmailMarketingList, pk=list_id, organization=org)

    campaign_id = request.POST.get("campaign_id")
    name = (request.POST.get("name") or "").strip() or "Untitled Campaign"
    subject = (request.POST.get("subject") or "").strip()
    html_content = request.POST.get("html_content") or ""
    css_content = request.POST.get("css_content") or ""

    if campaign_id:
        campaign = get_object_or_404(EmailCampaign, pk=campaign_id, marketing_list=marketing_list)
        campaign.name = name
        campaign.subject = subject
        campaign.html_content = html_content
        campaign.css_content = css_content
        campaign.save()
    else:
        campaign = EmailCampaign.objects.create(
            organization=org,
            marketing_list=marketing_list,
            name=name,
            subject=subject,
            html_content=html_content,
            css_content=css_content,
            created_by=request.user,
        )

    messages.success(request, f'Campaign "{campaign.name}" saved.')
    return redirect(
        f"{reverse('email-marketing-workspace', args=[list_id])}?tab=campaigns&campaign={campaign.id}"
    )


@login_required
@require_POST
def email_marketing_send_campaign(request, list_id, campaign_id):
    org, _ = _resolve_org(request)
    _require_marketing_access(request, org)
    marketing_list = get_object_or_404(EmailMarketingList, pk=list_id, organization=org)
    campaign = get_object_or_404(EmailCampaign, pk=campaign_id, marketing_list=marketing_list)

    if not (campaign.subject or "").strip():
        messages.error(request, "Campaign subject is required before sending.")
        return redirect(
            f"{reverse('email-marketing-workspace', args=[list_id])}?tab=campaigns&campaign={campaign.id}"
        )

    contacts = _filter_contacts(marketing_list.contacts.all(), request).exclude(email="")
    selected_ids = request.POST.getlist("contact_ids")
    if selected_ids:
        contacts = contacts.filter(id__in=selected_ids)

    contacts = list(contacts.distinct())
    if not contacts:
        messages.error(request, "No contacts with email match your filters.")
        return redirect(
            f"{reverse('email-marketing-workspace', args=[list_id])}?tab=campaigns&campaign={campaign.id}"
        )

    filter_snapshot = {
        "q": request.POST.get("q", ""),
        "state": request.POST.get("state", ""),
        "city": request.POST.get("city", ""),
        "zip_code": request.POST.get("zip_code", ""),
        "has_email": request.POST.get("has_email", ""),
        "selected_ids": selected_ids,
    }

    with transaction.atomic():
        batch = EmailCampaignBatch.objects.create(
            campaign=campaign,
            sent_by=request.user,
            filter_snapshot=filter_snapshot,
            recipient_count=len(contacts),
        )
        EmailCampaignRecipient.objects.bulk_create([
            EmailCampaignRecipient(
                batch=batch,
                campaign=campaign,
                contact=contact,
                email=contact.email,
            )
            for contact in contacts
        ])

    send_email_campaign_batch.delay(batch.id)
    messages.success(request, f"Queued {len(contacts)} email(s) for delivery.")
    return redirect(
        f"{reverse('email-marketing-workspace', args=[list_id])}?tab=history&campaign={campaign.id}"
    )


@login_required
@require_POST
def email_marketing_upload_asset(request, list_id):
    org, _ = _resolve_org(request)
    _require_marketing_access(request, org)
    marketing_list = get_object_or_404(EmailMarketingList, pk=list_id, organization=org)
    image = request.FILES.get("image")
    if not image:
        return JsonResponse({"status": "error", "message": "No image uploaded."}, status=400)

    asset = EmailMarketingAsset.objects.create(
        organization=org,
        marketing_list=marketing_list,
        image=image,
        label=(request.POST.get("label") or image.name)[:120],
        uploaded_by=request.user,
    )
    return JsonResponse(
        {
            "status": "success",
            "url": asset.image.url,
            "label": asset.label,
            "id": asset.id,
        }
    )


@login_required
@require_GET
def email_marketing_preview_campaign(request, list_id, campaign_id):
    org, _ = _resolve_org(request)
    _require_marketing_access(request, org)
    marketing_list = get_object_or_404(EmailMarketingList, pk=list_id, organization=org)
    campaign = get_object_or_404(EmailCampaign, pk=campaign_id, marketing_list=marketing_list)

    contact_id = request.GET.get("contact_id")
    contact = None
    if contact_id:
        contact = marketing_list.contacts.filter(pk=contact_id).first()
    if not contact:
        contact = marketing_list.contacts.exclude(email="").first()

    html_content = request.GET.get("html_content", campaign.html_content)
    css_content = request.GET.get("css_content", campaign.css_content)
    rendered = render_campaign_html(html_content, css_content, contact)
    return JsonResponse({"html": rendered})


@login_required
@require_POST
def email_marketing_delete_list(request, list_id):
    org, _ = _resolve_org(request)
    _require_marketing_access(request, org)
    marketing_list = get_object_or_404(EmailMarketingList, pk=list_id, organization=org)
    name = marketing_list.name
    marketing_list.delete()
    messages.success(request, f'Deleted marketing list "{name}".')
    return redirect("email-marketing-home")
