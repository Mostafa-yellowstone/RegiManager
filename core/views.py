from decimal import Decimal
import csv
import io
import json
import os
import re
import requests
from io import BytesIO

from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth, TruncDate, ExtractHour
import calendar
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect, csrf_exempt
from django.utils.crypto import get_random_string
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .forms import (
    DMVAuthenticationForm,
    AgentSignupForm,
    ServiceRecordForm,
    ClientForm,
    VehicleForm,
    VehicleServiceForm,
    ClientIntakeForm,
)
from .models import (
    Organization, OrganizationMembership, ServiceAuditLog, ServiceRecord, 
    ServiceDocument, CustomServiceType, Referral, ReferralPayment, Client, Vehicle, ClientIntake
)
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.utils import OperationalError, ProgrammingError
from datetime import timedelta
from .tasks import send_automation_email
from .models import AutomationLog, FinanceStrategyNote, ClientNote, Notification
import io
from openpyxl import Workbook


class CountableList(list):
    def count(self, *args, **kwargs):
        if not args and not kwargs:
            return len(self)
        return super().count(*args, **kwargs)
        
    def first(self):
        return self[0] if self else None


def send_email_robustly(task_func, *args, **kwargs):
    """
    Dispatches an email task. Tries Celery first if a worker is active,
    otherwise falls back to running synchronously in a background thread
    to guarantee delivery.
    """
    from django.conf import settings
    import threading
    
    # 1. If Celery is eager, just call it synchronously
    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        try:
            task_func(*args, **kwargs)
            return "sent"
        except Exception as e:
            print(f"Eager send failed: {e}")
            return "failed"
            
    # 2. Check if Celery worker is active
    celery_running = False
    try:
        from celery import current_app
        # Short timeout to prevent blocking HTTP request
        inspect = current_app.control.inspect(timeout=0.3)
        stats = inspect.stats()
        if stats:
            celery_running = True
    except Exception:
        pass
        
    if celery_running:
        try:
            task_func.delay(*args, **kwargs)
            return "queued"
        except Exception as e:
            print(f"Celery queueing failed: {e}. Falling back to background thread.")
            
    # 3. Fallback to background thread
    def run_in_thread():
        try:
            task_func(*args, **kwargs)
        except Exception as err:
            print(f"Background thread email send failed: {err}")
            
    thread = threading.Thread(target=run_in_thread)
    thread.daemon = True
    thread.start()
    return "sent_background"


def _currency(value):
    amount = value or Decimal("0")
    return f"${amount:.2f}"


def _draw_org_logo(pdf, organization, x, y, size=24):
    logo_path = None
    if organization and getattr(organization, "logo", None):
        try:
            logo_path = organization.logo.path
        except Exception:
            logo_path = None
    if logo_path:
        try:
            pdf.drawImage(ImageReader(logo_path), x, y - size, width=size, height=size, mask="auto")
            return
        except Exception:
            pass
    pdf.setFillColorRGB(0.09, 0.38, 0.78)
    pdf.roundRect(x, y - size, size, size, 3, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(x + 4, y - (size / 2), "DMV")
    pdf.setFillColorRGB(0, 0, 0)


def _fit_text(text, max_width, font_name="Helvetica", font_size=7):
    value = str(text or "")
    if stringWidth(value, font_name, font_size) <= max_width:
        return value
    suffix = "..."
    allowed = value
    while allowed and stringWidth(allowed + suffix, font_name, font_size) > max_width:
        allowed = allowed[:-1]
    return (allowed + suffix) if allowed else suffix


def _normalize_weight_from_gvwr(raw_value):
    """
    Normalize noisy decoder GVWR strings into a clean numeric weight hint.
    Returns empty string when uncertain to avoid writing incorrect defaults.
    """
    if not raw_value:
        return ""
    raw = str(raw_value).upper()
    import re

    # Prefer explicit numeric ranges like 0-6000, 6001 TO 10000, etc.
    range_match = re.search(r"(\d{3,6})\s*(?:-|TO)\s*(\d{3,6})", raw)
    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2))
        # Use midpoint as practical hint for paperwork fields.
        return str((low + high) // 2)

    # Fallback: take the largest standalone number, but ignore tiny values.
    nums = [int(x) for x in re.findall(r"\d{3,6}", raw)]
    if nums:
        return str(max(nums))
    return ""


def _draw_cell_text(can, value, start_x, y, step_x, max_len):
    text = (value or "").strip().upper()
    for i, ch in enumerate(text[:max_len]):
        can.drawString(start_x + (i * step_x), y, ch)


def _build_form_prefill_payload(service, client, vehicle):
    dob_m, dob_d, dob_y = ("", "", "")
    if client and client.dob:
        dob_m, dob_d, dob_y = client.dob.strftime("%m"), client.dob.strftime("%d"), client.dob.strftime("%Y")
    return {
        "dob_m": dob_m,
        "dob_d": dob_d,
        "dob_y": dob_y,
        "driver_license": (client.driver_license if client else "") or "",
        "street_address": (f"{client.building_no} {client.street_address}".strip().upper() if client else "") or "",
        "city": (client.city.upper() if client else "") or "",
        "state": (client.state.upper() if client else "NY") or "NY",
        "zip_code": (client.zip_code if client else "") or "",
        "name_full": (client.business_name or client.last_name).upper() if client and client.is_commercial else f"{client.last_name}, {client.first_name} {client.middle_name or ''}".upper() if client else "",
        "year": str(vehicle.year) if vehicle else "",
        "make": vehicle.make.upper() if vehicle else "",
        "model": vehicle.model.upper() if vehicle else "",
        "vin": (vehicle.vin if vehicle else "").upper(),
        "plate_number": (vehicle.plate_number if vehicle else "") or "",
        "county": (client.county.upper() if client and client.county else "") or "",
        "phone_digits": "".join(ch for ch in ((client.phone_number if client else "") or "") if ch.isdigit()),
        "email": (client.email if client and client.email else "") or "",
        "service_type": (service.service_type_label if service else "") or "",
        # New MV-82 fields
        "odometer": vehicle.odometer_reading if vehicle else "",
        "odometer_status": vehicle.odometer_status if vehicle else "",
        "mgw": vehicle.max_gross_weight if vehicle else "",
        "axles": vehicle.num_axles if vehicle else "",
        "owner_name": vehicle.owner_name if vehicle else "",
        "owner_nys_id": vehicle.owner_nys_id if vehicle else "",
        "co_registrant_name": vehicle.co_registrant_name if vehicle else "",
        "co_registrant_nys_id": vehicle.co_registrant_nys_id if vehicle else "",
        "lienholder_name": vehicle.lienholder_name if vehicle else "",
        "lienholder_address": vehicle.lienholder_address if vehicle else "",
        "lien_filing_code": vehicle.lien_filing_code if vehicle else "",
        "lessor_name": vehicle.lessor_name if vehicle else "",
        "lessor_address": vehicle.lessor_address if vehicle else "",
    }


def _build_acroform_prefill_fields(form_type, prefill):
    """
    Strict per-form mapping only.
    Avoid broad aliases that can write into unrelated fields.
    """
    if form_type == "mv82":
        return {
            "NYS New York State driver license ID Identification number of PRIMARY REGISTRANT": prefill["driver_license"],
            "PRIMARY REGISTRANT DATE OF BIRTH Month": prefill["dob_m"],
            "PRIMARY REGISTRANT DATE OF BIRTH Day": prefill["dob_d"],
            "PRIMARY REGISTRANT DATE OF BIRTH Year": prefill["dob_y"],
            "THE ADDRESS WHERE PRIMARY REGISTRANT GETS MAIL": prefill["street_address"],
            "THE ADDRESS WHERE PRIMARY REGISTRANT GETS MAIL City or Town": prefill["city"],
            "THE ADDRESS WHERE PRIMARY REGISTRANT GETS MAIL State": prefill["state"],
            "THE ADDRESS WHERE PRIMARY REGISTRANT GETS MAIL Zip Code": prefill["zip_code"],
            
            # MV-82B keys remain here too; harmless for non-matching forms.
            "NAME OF PRIMARY REGISTRANT Last First Middle": prefill["name_full"],
            "NYS driver license number of PRIMARY": prefill["driver_license"],
            "STREET ADDRESS": prefill["street_address"],
            "CITY OR TOWN": prefill["city"],
            "STATE": prefill["state"],
            "ZIP CODE": prefill["zip_code"],
            "YEAR": prefill["year"],
            "MAKE": prefill["make"],
            "MODEL": prefill["model"],
            "HIN": prefill["vin"],
            # Technical
            "Odometer Reading": prefill["odometer"],
            "Max Gross Weight": prefill["mgw"],
            "Axles": prefill["axles"],
            # Ownership
            "OWNER NAME": prefill["owner_name"],
            "OWNER NYS ID": prefill["owner_nys_id"],
            "CO-REGISTRANT NAME": prefill["co_registrant_name"],
            "CO-REGISTRANT NYS ID": prefill["co_registrant_nys_id"],
            # Liens
            "Lienholder Name": prefill["lienholder_name"],
            "Lienholder Address": prefill["lienholder_address"],
            "Lien Filing Code": prefill["lien_filing_code"],
        }

    if form_type == "mv82b":
        return {
            "NAME OF PRIMARY REGISTRANT Last First Middle": prefill["name_full"],
            "NYS driver license number of PRIMARY": prefill["driver_license"],
            "STREET ADDRESS": prefill["street_address"],
            "CITY OR TOWN": prefill["city"],
            "STATE": prefill["state"],
            "ZIP CODE": prefill["zip_code"],
            "YEAR": prefill["year"],
            "MAKE": prefill["make"],
            "MODEL": prefill["model"],
            "HIN": prefill["vin"],
        }

    # DTF forms currently use overlay/manual paths only.
    return {}


def _extract_pdf_field_names(pdf_reader):
    names = []
    for page in pdf_reader.pages:
        annots = page.get("/Annots") or []
        for annot in annots:
            obj = annot.get_object()
            field_name = obj.get("/T")
            if field_name:
                names.append(str(field_name))
    # Preserve order, drop duplicates
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


def _token_match_score(field_name, required_tokens):
    text = (field_name or "").lower().replace("_", " ")
    score = 0
    for t in required_tokens:
        if t in text:
            score += 1
        else:
            return 0
    return score


def _build_dtf_token_prefill_fields(pdf_reader, prefill):
    """
    Conservative token-based matching for DTF templates:
    - only map when all required tokens are present
    - avoids broad aliases that caused overlap/misplacement
    """
    field_names = _extract_pdf_field_names(pdf_reader)
    if not field_names:
        return {}

    candidates = [
        (["name", "purchaser"], prefill["name_full"]),
        (["name", "buyer"], prefill["name_full"]),
        (["address"], prefill["street_address"]),
        (["city"], prefill["city"]),
        (["state"], prefill["state"]),
        (["zip"], prefill["zip_code"]),
        (["vin"], prefill["vin"]),
        (["vehicle", "identification"], prefill["vin"]),
        (["year"], prefill["year"]),
        (["make"], prefill["make"]),
        (["model"], prefill["model"]),
        (["driver", "license"], prefill["driver_license"]),
        (["dl"], prefill["driver_license"]),
        (["plate"], prefill["plate_number"]),
    ]

    mapped = {}
    used_fields = set()
    for tokens, value in candidates:
        if not value:
            continue
        best = None
        best_score = 0
        for fname in field_names:
            if fname in used_fields:
                continue
            score = _token_match_score(fname, tokens)
            if score > best_score:
                best_score = score
                best = fname
        if best and best_score > 0:
            mapped[best] = value
            used_fields.add(best)
    return mapped


def _has_active_org_access(user, organization_id):
    if not getattr(user, "is_authenticated", False):
        return False
    return OrganizationMembership.objects.filter(
        user=user,
        organization_id=organization_id,
        is_active=True,
        organization__is_active=True,
    ).exists()


def _has_active_owner_access(user, organization_id):
    if not getattr(user, "is_authenticated", False):
        return False
    return OrganizationMembership.objects.filter(
        user=user,
        organization_id=organization_id,
        role=OrganizationMembership.Role.OWNER,
        is_active=True,
        organization__is_active=True,
    ).exists()


def _get_user_organizations(request):
    """
    Helper to get all organizations the user belongs to,
    optionally filtered by the active organization in the session.
    """
    if request.user.is_superuser:
        all_orgs = Organization.objects.filter(is_active=True)
        active_org_id = request.session.get('active_org_id')
        if active_org_id:
            return all_orgs.filter(id=active_org_id)
        return all_orgs

    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    )
    all_orgs = Organization.objects.filter(id__in=memberships.values("organization_id")).distinct()

    active_org_id = request.session.get('active_org_id')
    if active_org_id:
        # Verify the user actually belongs to this org
        if memberships.filter(organization_id=active_org_id).exists():
            return all_orgs.filter(id=active_org_id)

    return all_orgs


@login_required
def switch_organization(request, org_id):
    """
    Switch the active organization for the current session.
    If org_id is 0, it clears the filter (shows all accessible orgs).
    """
    if org_id == 0:
        if 'active_org_id' in request.session:
            del request.session['active_org_id']
        messages.success(request, "Switched to 'All Locations' view.")
    else:
        # Security check: does user belong to this org?
        exists = OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=org_id,
            is_active=True
        ).exists()

        if exists:
            org = Organization.objects.get(id=org_id)
            request.session['active_org_id'] = org_id
            messages.success(request, f"Switched to {org.name}")
        else:
            messages.error(request, "You do not have access to that location.")

    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


def _can_access_finance_hub(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return OrganizationMembership.objects.filter(
        user=user,
        is_active=True,
        organization__is_active=True,
    ).filter(
        Q(role=OrganizationMembership.Role.OWNER) | Q(can_view_reports=True)
    ).exists()


def home(request):
    return render(request, "core/home.html")


def contact(request):
    return render(request, "core/contact.html")


def privacy(request):
    return render(request, "core/privacy.html")



from django.views.decorators.csrf import ensure_csrf_cookie

@ensure_csrf_cookie
def member_signup(request):
    if request.method == "POST":
        form = AgentSignupForm(request.POST)
        if form.is_valid():
            organization = form.cleaned_data["invite_code"]
            
            current_agents = OrganizationMembership.objects.filter(
                organization=organization, role=OrganizationMembership.Role.MEMBER
            ).count()
            
            if current_agents >= organization.max_agents:
                messages.error(request, f"Cannot register: PSB '{organization.name}' has reached its maximum limit of {organization.max_agents} agents.")
                return render(
                    request,
                    "core/auth_form.html",
                    {
                        "title": "Create Agent Account",
                        "subtitle": "Create a separate agent account inside an existing PSB.",
                        "form": form,
                        "submit_text": "Create Agent Account",
                        "switch_label": "Already have an account?",
                        "switch_url": "login",
                        "switch_text": "Sign in",
                    },
                )
                
            user = form.save()
            OrganizationMembership.objects.create(
                organization=organization,
                user=user,
                role=OrganizationMembership.Role.MEMBER,
            )
            login(request, user)
            messages.success(request, "Your agent account was created successfully.")
            return redirect("dashboard")
    else:
        form = AgentSignupForm()
    filtered_query = request.GET.copy()
    filtered_query.pop("page", None)
    filtered_query.pop("export", None)

    return render(
        request,
        "core/auth_form.html",
        {
            "title": "Create Agent Account",
            "subtitle": "Create a separate agent account inside an existing PSB.",
            "form": form,
            "submit_text": "Create Agent Account",
            "switch_label": "Already have an account?",
            "switch_url": "login",
            "switch_text": "Sign in",
        },
    )


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("/admin/")
        return redirect("dashboard")

    if request.method == "POST":
        form = DMVAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.is_superuser:
                return redirect("/admin/")
            return redirect("dashboard")
    else:
        form = DMVAuthenticationForm(request)

    return render(
        request,
        "core/auth_form.html",
        {
            "title": "Sign In to PSB Portal",
            "subtitle": "Access vehicle registrations, renewals, plate transfers, and insurance lapse payments.",
            "form": form,
            "submit_text": "Sign In",
            "switch_label": "Need an agent account?",
            "switch_url": "member-signup",
            "switch_text": "Create agent account",
        },
    )

from django.db import transaction

@login_required
def add_client(request):
    organizations = _get_user_organizations(request)
    if request.method == "POST":
        # Pre-check for existing client to allow auto-merging/redirecting
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        dl = request.POST.get('driver_license', '').strip().upper()
        org_id = request.POST.get('organization')
        is_commercial = request.POST.get('is_commercial') in ['on', 'true', '1']
        business_ein = request.POST.get('business_ein', '').strip()

        if is_commercial and business_ein and org_id:
            # Duplicate check for commercial: match by EIN
            existing = Client.objects.filter(
                is_commercial=True,
                business_ein__iexact=business_ein,
                organization_id=org_id
            ).first()
            if existing:
                messages.info(request, f"Business {existing.name} already exists (EIN match). Redirecting to profile.")
                return redirect("client-detail", client_id=existing.id)
        elif first_name and last_name and dl and org_id:
            existing = Client.objects.filter(
                first_name__iexact=first_name,
                last_name__iexact=last_name,
                driver_license__iexact=dl,
                organization_id=org_id
            ).first()
            if existing:
                messages.info(request, f"Client {existing.name} already exists. Redirecting to profile.")
                return redirect("client-detail", client_id=existing.id)

        form = ClientForm(request.POST, request.FILES, organizations=organizations)
        if form.is_valid():
            try:
                with transaction.atomic():
                    client = form.save(commit=False)
                    
                    # If organization field was disabled, it might not be in cleaned_data
                    if not client.organization_id and organizations.count() == 1:
                        client.organization = organizations.first()
                    
                    # Referral logic
                    source = form.cleaned_data.get('source')
                    if source == 'referral':
                        referral_select = form.cleaned_data.get('referral_select')
                        if referral_select and referral_select != 'new':
                            try:
                                referral = Referral.objects.get(id=referral_select, organization=client.organization)
                                client.referral = referral
                            except Referral.DoesNotExist:
                                pass
                        else:
                            referral_name = form.cleaned_data.get('referral_name')
                            if referral_name:
                                # First, check if a referral with this name already exists in this organization
                                referral = Referral.objects.filter(
                                    organization=client.organization,
                                    name__iexact=referral_name
                                ).first()
                                
                                if not referral:
                                    # Create new referral if not found
                                    referral = Referral.objects.create(
                                        organization=client.organization,
                                        name=referral_name,
                                        category=form.cleaned_data.get('referral_category', 'dealer'),
                                        address=form.cleaned_data.get('referral_address', ''),
                                        phone_no=form.cleaned_data.get('referral_phone_no', ''),
                                        email=form.cleaned_data.get('referral_email', ''),
                                        website=form.cleaned_data.get('referral_website', ''),
                                        initial_balance=form.cleaned_data.get('referral_balance') or 0,
                                    )
                                client.referral = referral
                    
                    client.save()
                messages.success(request, f"Client {client.name} profile created.")
                return redirect("add-vehicle", client_id=client.id)
            except Exception as e:
                messages.error(request, f"An error occurred: {e}")
    else:
        form = ClientForm(organizations=organizations)

    # Global Recognition: Search across all owner-managed branches
    is_owner = OrganizationMembership.objects.filter(
        user=request.user, role=OrganizationMembership.Role.OWNER, is_active=True
    ).exists()
    
    existing_global_clients = []
    search_q = request.GET.get('q_global', '').strip()
    if is_owner and search_q:
        all_owner_orgs = Organization.objects.filter(
            memberships__user=request.user, 
            memberships__role=OrganizationMembership.Role.OWNER,
            is_active=True
        )
        clients_qs = Client.objects.filter(
            Q(ssn=search_q) | Q(driver_license=search_q) | Q(last_name__icontains=search_q) | Q(business_name__icontains=search_q),
            organization__in=all_owner_orgs
        )
        
        # If a specific active org is selected, we exclude it to find matches in OTHER branches.
        # If 'All Locations' is selected (active_org_id is None), we show all matching clients system-wide.
        if request.session.get('active_org_id'):
            clients_qs = clients_qs.exclude(organization__in=organizations)
            
        existing_global_clients = clients_qs.select_related('organization').distinct()

    return render(request, "core/add_client.html", {
        "form": form, 
        "organizations": organizations,
        "existing_global_clients": existing_global_clients,
        "is_owner": is_owner,
        "search_q": search_q
    })


@login_required
def client_detail(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if not _has_active_org_access(request.user, client.organization_id):
        return HttpResponseForbidden("Access denied.")
    
    vehicles = client.vehicles.all()
    records_qs = (
        ServiceRecord.objects.filter(vehicle__client=client)
        .select_related("handled_by", "vehicle", "vehicle__client", "organization", "referral")
        .order_by("-created_at")
    )
    try:
        notes_qs = client.notes.select_related("created_by", "assigned_to").all()
    except (OperationalError, ProgrammingError):
        notes_qs = ClientNote.objects.none()

    assignable_agents = User.objects.filter(
        organization_memberships__organization=client.organization,
        organization_memberships__is_active=True,
        organization_memberships__role=OrganizationMembership.Role.MEMBER,
    ).distinct().order_by("first_name", "last_name", "username")
    
    record_totals = records_qs.aggregate(total_spend=Sum("service_fee"), total_services=Count("id"))
    total_spend = record_totals["total_spend"] or Decimal("0")
    total_services = record_totals["total_services"] or 0
    last_service_date = records_qs.values_list("created_at", flat=True).first()

    notes_paginator = Paginator(notes_qs, 3)
    notes_page = request.GET.get("notes_page")
    notes = notes_paginator.get_page(notes_page)

    records_paginator = Paginator(records_qs, 6)
    tx_page = request.GET.get("tx_page")
    records = records_paginator.get_page(tx_page)
    
    from django.db.models import Q
    all_docs = ServiceDocument.objects.filter(
        Q(vehicle__client=client) | Q(service_record__vehicle__client=client)
    ).select_related("vehicle", "service_record").distinct().order_by("-uploaded_at")
    
    return render(request, "core/client_profile.html", {
        "client": client, 
        "vehicles": vehicles,
        "records": records,
        "documents": all_docs,
        "notes": notes,
        "assignable_agents": assignable_agents,
        "total_spend": total_spend,
        "total_services": total_services,
        "last_service_date": last_service_date
    })


@login_required
@require_POST
def add_client_note(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if not _has_active_org_access(request.user, client.organization_id):
        return HttpResponseForbidden("Access denied.")

    content = (request.POST.get("content") or "").strip()
    follow_up_date = (request.POST.get("follow_up_date") or "").strip()
    assigned_to_raw = (request.POST.get("assigned_to") or "").strip()

    if not content:
        messages.error(request, "Please enter a note.")
        return redirect("client-detail", client_id=client.id)

    try:
        assigned_to = None
        if assigned_to_raw.isdigit():
            assigned_to = User.objects.filter(
                id=int(assigned_to_raw),
                organization_memberships__organization=client.organization,
                organization_memberships__is_active=True,
                organization_memberships__role=OrganizationMembership.Role.MEMBER,
            ).first()

        note = ClientNote.objects.create(
            client=client,
            created_by=request.user,
            assigned_to=assigned_to,
            content=content,
            follow_up_date=follow_up_date or None,
        )

        if assigned_to:
            Notification.objects.create(
                user=assigned_to,
                client=client,
                note=note,
                level=Notification.Level.WARNING,
                title="New client note assigned",
                message=f"{request.user.get_full_name() or request.user.username} assigned you a note for {client.name}.",
            )

        if note.follow_up_date:
            Notification.objects.create(
                user=request.user,
                client=client,
                note=note,
                level=Notification.Level.WARNING,
                title="Client follow-up reminder",
                message=f"Follow up on {client.name} on {note.follow_up_date}.",
            )
    except (OperationalError, ProgrammingError):
        messages.error(request, "Notes table is not available yet. Please run migrations.")
        return redirect("client-detail", client_id=client.id)

    messages.success(request, "Note saved.")
    return redirect("client-detail", client_id=client.id)


@login_required
@require_POST
def mark_client_note_done(request, note_id):
    note = get_object_or_404(ClientNote.objects.select_related("client", "created_by", "assigned_to"), id=note_id)
    if not _has_active_org_access(request.user, note.client.organization_id):
        return HttpResponseForbidden("Access denied.")

    if not note.is_done:
        note.is_done = True
        note.save(update_fields=["is_done"])
        Notification.objects.filter(note=note).update(is_read=True)
        
        if note.created_by and note.created_by != request.user:
            Notification.objects.create(
                user=note.created_by,
                client=note.client,
                level=Notification.Level.INFO,
                title="Client Note Completed",
                message=f"{request.user.get_full_name() or request.user.username} marked your note for {note.client.name} as done.",
            )
            
        if note.assigned_to and note.assigned_to != request.user and note.assigned_to != note.created_by:
            Notification.objects.create(
                user=note.assigned_to,
                client=note.client,
                level=Notification.Level.INFO,
                title="Client Note Completed",
                message=f"{request.user.get_full_name() or request.user.username} marked the note assigned to you for {note.client.name} as done.",
            )

        messages.success(request, "Note marked as done.")

    next_url = (request.POST.get("next") or "").strip()
    if next_url:
        return redirect(next_url)
    return redirect("client-detail", client_id=note.client_id)


@login_required
def open_notification(request, notification_id):
    try:
        notif = get_object_or_404(
            Notification.objects.select_related("client", "note"),
            id=notification_id,
            user=request.user,
        )
    except (OperationalError, ProgrammingError):
        messages.error(request, "Notifications are temporarily unavailable. Please run migrations.")
        return redirect("dashboard")

    # Keep note-linked notifications visible until user marks note as done.
    if not notif.note_id and not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=["is_read"])

    anchor = ""
    if notif.note_id:
        anchor = f"#note-{notif.note_id}"
    return redirect(f"{redirect('client-detail', client_id=notif.client_id).url}{anchor}")


@login_required
def get_client_details(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    # Security: Only owner can fetch across branches if they own BOTH
    if not _has_active_owner_access(request.user, client.organization_id):
        return JsonResponse({"status": "error", "message": "Access denied"}, status=403)
        
    data = {
        "first_name": client.first_name,
        "last_name": client.last_name,
        "middle_name": client.middle_name,
        "ssn": client.ssn,
        "driver_license": client.driver_license,
        "dob": client.dob.isoformat() if client.dob else "",
        "phone_number": client.phone_number,
        "building_no": client.building_no,
        "street_address": client.street_address,
        "apartment": client.apartment,
        "city": client.city,
        "state": client.state,
        "zip_code": client.zip_code,
        "county": client.county,
        "email": client.email,
        "gender": client.gender,
    }
    return JsonResponse({"status": "success", "data": data})


@login_required
def all_clients(request):
    organizations = _get_user_organizations(request)
    clients = Client.objects.filter(organization__in=organizations).order_by("-created_at")
    
    # Advanced filter params
    query = request.GET.get('q', '').strip()
    selected_source = request.GET.get('source', '').strip()
    selected_client_type = request.GET.get('client_type', '').strip()
    selected_referral = request.GET.get('referral', '').strip()

    if query:
        clients = clients.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone_number__icontains=query) |
            Q(city__icontains=query) |
            Q(business_name__icontains=query) |
            Q(business_ein__icontains=query)
        )
    
    if selected_source:
        clients = clients.filter(source__iexact=selected_source)
        
    if selected_client_type == 'commercial':
        clients = clients.filter(is_commercial=True)
    elif selected_client_type == 'individual':
        clients = clients.filter(is_commercial=False)
        
    if selected_referral:
        clients = clients.filter(referral_id=selected_referral)

    clients = clients.distinct()

    # Dynamic filter choices
    db_sources = Client.objects.filter(organization__in=organizations).values_list('source', flat=True).distinct()
    SOURCE_LABELS = {
        "google_search": "Google Search",
        "walk_in": "Walk-In",
        "walk-in": "Walk-In",
        "website": "Website",
        "meta_platform": "Meta Platform",
        "google_campaigns": "Google Campaigns",
        "existing_client": "Existing Client",
        "dealer": "Dealer",
        "referral": "Referral",
        "cold_calling": "Cold Calling",
        "insurance": "Insurance",
        "other": "Other",
    }
    
    source_choices = []
    seen_sources = set()
    standard_keys = ["google_search", "walk_in", "website", "meta_platform", "google_campaigns", "existing_client", "dealer", "referral", "cold_calling", "insurance", "other"]
    
    for sk in standard_keys:
        source_choices.append({
            "key": sk,
            "label": SOURCE_LABELS.get(sk, sk.replace('_', ' ').replace('-', ' ').title())
        })
        seen_sources.add(sk)

    for s in db_sources:
        if s:
            s_lower = s.lower().strip()
            if s_lower not in seen_sources:
                source_choices.append({
                    "key": s_lower,
                    "label": SOURCE_LABELS.get(s_lower, s.replace('_', ' ').replace('-', ' ').title())
                })
                seen_sources.add(s_lower)

    referrals = Referral.objects.filter(organization__in=organizations).order_by('name')

    paginator = Paginator(clients, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    return render(request, "core/all_clients.html", {
        "page_obj": page_obj,
        "search_query": query,
        "selected_source": selected_source,
        "selected_client_type": selected_client_type,
        "selected_referral": selected_referral,
        "source_choices": source_choices,
        "referrals": referrals,
    })


@login_required
def add_vehicle(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if not _has_active_org_access(request.user, client.organization_id):
        return HttpResponseForbidden("Access denied.")

    if request.method == "POST":
        vin = request.POST.get('vin', '').strip().upper()
        if vin:
            # Block only if the same client already has this VIN (active vehicle)
            existing_same_client = Vehicle.objects.filter(vin=vin, client=client).first()
            if existing_same_client:
                messages.info(request, f"This vehicle (VIN: {vin}) is already in {client}'s profile.")
                return redirect("client-detail", client_id=client.id)

        form = VehicleForm(request.POST, client=client)
        if form.is_valid():
            vehicle = form.save(commit=False)
            vehicle.client = client
            vehicle.save()
            messages.success(request, f"Vehicle {vehicle} added for {client}.")
            return redirect("client-detail", client_id=client.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        # Generate a unique auto-generic vehicle number
        auto_vnum = f"VEH-{get_random_string(6, allowed_chars='0123456789')}"
        form = VehicleForm(initial={'vehicle_number': auto_vnum}, client=client)
    
    return render(request, "core/add_vehicle.html", {"client": client, "form": form})


@login_required
def check_vin_ajax(request):
    vin = request.GET.get("vin", "").strip().upper()
    org_id = request.GET.get("org_id", "").strip()
    client_id = request.GET.get("client_id", "").strip()
    vehicle_id = request.GET.get("vehicle_id", "").strip()

    if not vin:
        return JsonResponse({"exists": False, "is_valid": False})

    if not org_id.isdigit() or not _has_active_org_access(request.user, int(org_id)):
        return JsonResponse({"exists": False, "is_valid": False})
    
    # Structural check (Modern VINs are 17 characters and don't contain I, O, or Q)
    is_valid_format = len(vin) == 17 and not any(c in vin for c in "IOQ")
    
    # Base filter for active vehicles with this VIN in the organization
    org_vehicles = Vehicle.objects.filter(vin=vin, client__organization_id=int(org_id))
    if vehicle_id.isdigit():
        org_vehicles = org_vehicles.exclude(id=int(vehicle_id))
    
    exists_this_client = False
    if client_id.isdigit():
        exists_this_client = org_vehicles.filter(client_id=int(client_id)).exists()
    
    # Other owners (excluding the current client if client_id is passed)
    other_vehicles = org_vehicles
    if client_id.isdigit():
        other_vehicles = other_vehicles.exclude(client_id=int(client_id))
        
    other_owners = []
    for v in other_vehicles.select_related("client"):
        c = v.client
        name_val = c.business_name if c.is_commercial and c.business_name else f"{c.first_name} {c.last_name}".strip()
        other_owners.append({
            "name": name_val,
            "vehicle": f"{v.year} {v.make} {v.model}",
            "plate": v.plate_number or "N/A"
        })
        
    primary_vehicle = org_vehicles.first()
    
    decoded_fallback = {}
    if primary_vehicle:
        decoded_fallback = {
            "year": primary_vehicle.year,
            "make": primary_vehicle.make,
            "model": primary_vehicle.model,
            "body_type": primary_vehicle.body_type,
            "fuel_type": primary_vehicle.fuel_type,
            "cylinders": primary_vehicle.cylinders,
            "seats": primary_vehicle.seats,
            "weight": primary_vehicle.weight,
            "color": primary_vehicle.color
        }

    response_data = {
        "exists": exists_this_client,  # keep 'exists' mapped to same-client for backward compatibility
        "exists_this_client": exists_this_client,
        "exists_other_client": len(other_owners) > 0,
        "is_valid": is_valid_format,
        "other_owners": other_owners,
    }
    
    if decoded_fallback:
        response_data["decoded"] = decoded_fallback
        
    if exists_this_client or len(other_owners) > 0:
        return JsonResponse(response_data)
        
    # 2. If it's a new VIN and valid, try to decode it via NHTSA API
    decoded_data = {}
    if is_valid_format:
        try:
            import requests
            url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json().get("Results", [{}])[0]
                # Map NHTSA fields to our model fields
                decoded_data = {
                    "year": data.get("ModelYear"),
                    "make": data.get("Make"),
                    "model": data.get("Model"),
                    "body_type": data.get("BodyClass"),
                    "fuel_type": data.get("FuelTypePrimary"),
                    "cylinders": data.get("EngineCylinders"),
                    "weight_raw": data.get("GVWR"),
                    "weight": _normalize_weight_from_gvwr(data.get("GVWR")),
                    "seats": data.get("Seats"),
                    "color": data.get("ExteriorColor"),
                }
        except Exception:
            pass
            
    if decoded_data:
        response_data["decoded"] = decoded_data
        
    return JsonResponse(response_data)


@login_required
def check_client_name_ajax(request):
    first_name = request.GET.get("first_name", "").strip()
    last_name = request.GET.get("last_name", "").strip()
    org_id = request.GET.get("org_id", "").strip()
    
    if not first_name or not last_name or not org_id:
        return JsonResponse({"exists": False})

    if not org_id.isdigit() or not _has_active_org_access(request.user, int(org_id)):
        return JsonResponse({"exists": False})
    
    exists = Client.objects.filter(
        first_name__iexact=first_name,
        last_name__iexact=last_name,
        organization_id=int(org_id)
    ).exists()
    
    return JsonResponse({"exists": exists})


@login_required
def vehicle_detail(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle.all_objects, id=vehicle_id)
    if not _has_active_org_access(request.user, vehicle.client.organization_id):
        return HttpResponseForbidden("Access denied.")
    
    from django.db.models import Q
    # Show all docs for this client's fleet
    documents = ServiceDocument.objects.filter(
        Q(vehicle__client=vehicle.client) | 
        Q(service_record__vehicle__client=vehicle.client)
    ).distinct().order_by("-uploaded_at")
    service_records = vehicle.service_records.order_by("-created_at")
    latest_service = service_records.first()
    
    # Paginate documents (docs tab)
    doc_paginator = Paginator(documents, 12)
    doc_page_number = request.GET.get('doc_page')
    page_obj = doc_paginator.get_page(doc_page_number)
    
    # Paginate service records (transactions tab)
    svc_paginator = Paginator(service_records, 12)
    svc_page_number = request.GET.get('svc_page')
    services_page_obj = svc_paginator.get_page(svc_page_number)
    # Keep latest_service from full queryset (not paginated)
    latest_service = service_records.first()
    
    return render(request, "core/vehicle_detail.html", {
        "vehicle": vehicle,
        "page_obj": page_obj,
        "services_page_obj": services_page_obj,
        "latest_service": latest_service
    })


@login_required
def start_process(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle.all_objects, id=vehicle_id)
    if not _has_active_org_access(request.user, vehicle.client.organization_id):
        return HttpResponseForbidden("Access denied.")
    
    if request.method == "POST":
        form = VehicleServiceForm(request.POST, organization=vehicle.client.organization)
        if form.is_valid():
            record = form.save(commit=False)
            record.vehicle = vehicle
            record.organization = vehicle.client.organization
            record.handled_by = request.user
            
            # Snapshots of vehicle info for the receipt
            record.vehicle_number = vehicle.vehicle_number
            record.vin = vehicle.vin
            record.plate_number = vehicle.plate_number
            
            # Snapshots of client info
            record.client_name = vehicle.client.name
            record.client_address = vehicle.client.full_address
            
            # Logic for payment and balance
            total_paid = form.cleaned_data.get('paid_amount')
            if total_paid is None:
                total_paid = Decimal("0")
            record.paid_amount = total_paid
            total_fees = (
                (record.processing_fee or Decimal("0"))
                + (record.dmv_fee or Decimal("0"))
                + (record.sales_tax or Decimal("0"))
                + (record.dmv_sales_tax or Decimal("0"))
                + (record.other_fees or Decimal("0"))
                + (record.other_dmv_fee or Decimal("0"))
                + (record.credit_card_fee or Decimal("0"))
            )

            # Auto-link to referral if this client came from a referralship
            if vehicle.client.referral:
                record.referral = vehicle.client.referral
                # Automatically calculate the balance if referral is selected
                if total_paid < total_fees:
                    record.referral_balance = total_fees - total_paid
                else:
                    record.referral_balance = 0
            
            record.save()
            
            # If referral and there is a balance, create a ReferralPayment ledger record
            if record.referral and record.referral_balance > 0:
                from .models import ReferralPayment
                ReferralPayment.objects.create(
                    referral=record.referral,
                    service_record=record,
                    amount=record.referral_balance,
                    payment_type="debt",
                    notes=f"Initial debt from {record.service_type_label}"
                )

            ServiceAuditLog.objects.create(
                organization=record.organization,
                service_record=record,
                actor=request.user,
                action="created",
                details=f"Service {record.service_type} started for vehicle {vehicle}. Paid: {record.paid_amount}, Balance: {record.referral_balance}"
            )
            
            messages.success(request, f"Service {record.service_type} created successfully.")
            
            # Send Confirmation Email and Log
            if vehicle.client.email:
                subject = f"Case Confirmation: {record.case_id} - {record.service_type_label}"
                context = {
                    "client_name": vehicle.client.name,
                    "service_type": record.service_type_label,
                    "case_id": record.case_id,
                    "psb_name": record.organization.name,
                }
                mail_dispatch_status = send_email_robustly(
                    send_automation_email,
                    vehicle.client.email,
                    subject,
                    "core/emails/confirmation.html",
                    context,
                )
                
                AutomationLog.objects.create(
                    organization=record.organization,
                    service_record=record,
                    vehicle=vehicle,
                    client=vehicle.client,
                    log_type="confirmation",
                    sent_to=vehicle.client.email,
                    details=f"Initial case confirmation {mail_dispatch_status} for {record.case_id}.",
                )
            return redirect("client-detail", client_id=vehicle.client.id)
    else:
        form = VehicleServiceForm(organization=vehicle.client.organization)
    
    return render(request, "core/start_process.html", {"vehicle": vehicle, "form": form})


def get_latest_news(request):
    from .models import SiteNews
    news = SiteNews.objects.filter(is_active=True).order_by('-created_at').first()
    if news:
        return JsonResponse({
            "id": news.id,
            "title": news.title,
            "content": news.content,
        })
    return JsonResponse({"id": None})


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect("/admin/")
        
    organizations = _get_user_organizations(request)
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
        organization__in=organizations
    ).select_related("organization")

    if not memberships.exists():
        messages.error(request, "Your account is currently disabled for all psbs. Contact an owner.")
        logout(request)
        return redirect("login")
    
    # Client/Vehicle flow is now handled by separate views.
    # Dashboard just shows overview statistics and quick links.

    owner_org_ids = list(
        memberships.filter(role=OrganizationMembership.Role.OWNER).values_list(
            "organization_id", flat=True
        )
    )
    is_owner = bool(owner_org_ids)
    owner_orgs = Organization.objects.filter(id__in=owner_org_ids) if is_owner else Organization.objects.none()
    
    scope_qs = ServiceRecord.objects.filter(organization__in=organizations)
    # Visibility unlocked: Agents can see all records in their PSB
    # if not is_owner:
    #     scope_qs = scope_qs.filter(handled_by=request.user)

    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    service_records = (
        scope_qs.select_related("organization", "handled_by")
        .order_by("-created_at")[:3]
    )

    audit_scope = ServiceAuditLog.objects.filter(service_record__organization__in=organizations)
    # Visibility unlocked: Agents can see all audit logs in their PSB
    # if not is_owner:
    #     audit_scope = audit_scope.filter(service_record__handled_by=request.user)

    audit_logs = (
        audit_scope.select_related("actor", "organization", "service_record")
        .order_by("-created_at")[:5]
    )

    service_totals_qs = (
        scope_qs.values("service_type")
        .annotate(total=Count("id"), amount=Sum("service_fee"))
        .order_by("-total")
    )
    status_totals_qs = (
        scope_qs.values("status")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    service_type_map = dict(ServiceRecord.SERVICE_TYPES)
    status_map = dict(ServiceRecord.STATUS_CHOICES)
    service_totals = [
        {
            **row,
            "service_label": service_type_map.get(row["service_type"], row["service_type"]),
        }
        for row in service_totals_qs
    ]
    status_totals = [
        {
            **row,
            "status_label": status_map.get(row["status"], row["status"]),
        }
        for row in status_totals_qs
    ]

    overall_totals = scope_qs.aggregate(
        total_amount=Sum("service_fee"),
        total_processing=Sum("processing_fee"),
        total_dmv=Sum("dmv_fee"),
        total_tax=Sum("sales_tax"),
        total_card=Sum("credit_card_fee"),
    )
    overall_amount = overall_totals["total_amount"] or Decimal("0")
    overall_net_profit = overall_totals["total_processing"] or Decimal("0")

    yearly_qs = scope_qs.filter(created_at__date__gte=year_start, created_at__date__lte=today)
    monthly_qs = scope_qs.filter(created_at__date__gte=month_start, created_at__date__lte=today)
    daily_qs = scope_qs.filter(created_at__date=today)
    
    yearly_report = yearly_qs.aggregate(
        total_records=Count("id"),
        processing_fee=Sum("processing_fee")
    )
    yearly_report["net_profit"] = yearly_report["processing_fee"] or Decimal("0")
    monthly_report = monthly_qs.aggregate(
        total_records=Count("id"),
        total_amount=Sum("service_fee"),
        processing_fee=Sum("processing_fee"),
        dmv_fee=Sum("dmv_fee"),
        sales_tax=Sum("sales_tax"),
        credit_card_fee=Sum("credit_card_fee"),
    )
    monthly_report["completed"] = monthly_qs.filter(status="completed").count()
    monthly_report["pending"] = monthly_qs.filter(status="pending").count()
    monthly_report["failed"] = monthly_qs.filter(status="failed").count()
    monthly_report["net_profit"] = monthly_report["processing_fee"] or Decimal("0")
    monthly_report["total_amount"] = monthly_report["total_amount"] or Decimal("0")
    monthly_report["processing_fee"] = monthly_report["processing_fee"] or Decimal("0")
    monthly_report["dmv_fee"] = monthly_report["dmv_fee"] or Decimal("0")
    monthly_report["sales_tax"] = monthly_report["sales_tax"] or Decimal("0")
    monthly_report["credit_card_fee"] = monthly_report["credit_card_fee"] or Decimal("0")

    daily_report = daily_qs.aggregate(
        total_records=Count("id"),
        total_amount=Sum("service_fee"),
        processing_fee=Sum("processing_fee"),
        dmv_fee=Sum("dmv_fee"),
        sales_tax=Sum("sales_tax"),
        credit_card_fee=Sum("credit_card_fee"),
    )
    daily_report["completed"] = daily_qs.filter(status="completed").count()
    daily_report["pending"] = daily_qs.filter(status="pending").count()
    daily_report["failed"] = daily_qs.filter(status="failed").count()
    daily_report["net_profit"] = daily_report["processing_fee"] or Decimal("0")
    daily_report["total_amount"] = daily_report["total_amount"] or Decimal("0")
    daily_report["processing_fee"] = daily_report["processing_fee"] or Decimal("0")
    daily_report["dmv_fee"] = daily_report["dmv_fee"] or Decimal("0")
    daily_report["sales_tax"] = daily_report["sales_tax"] or Decimal("0")
    daily_report["credit_card_fee"] = daily_report["credit_card_fee"] or Decimal("0")

    custom_types = CustomServiceType.objects.filter(organization__in=organizations)
    all_service_keys = list(ServiceRecord.SERVICE_TYPES)
    for ct in custom_types:
        all_service_keys.append((ct.key, ct.label))

    service_cards = []
    for service_key, service_label in all_service_keys:
        service_subset = scope_qs.filter(service_type=service_key)
        service_cards.append(
            {
                "key": service_key,
                "label": service_label,
                "daily_count": service_subset.filter(created_at__date=today).count(),
                "monthly_count": service_subset.filter(created_at__date__gte=month_start).count(),
                "yearly_count": service_subset.filter(created_at__date__gte=year_start).count(),
                "total_count": service_subset.count(),
                "is_custom": service_key not in [t[0] for t in ServiceRecord.SERVICE_TYPES],
            }
        )

    show_all_services_card = False
    if len(service_cards) >= 8:
        service_cards = service_cards[:7]
        show_all_services_card = True

    owner_agents = []
    if is_owner:
        owner_agents = OrganizationMembership.objects.filter(
            organization_id__in=owner_org_ids
        ).exclude(user=request.user).select_related("user", "organization")
        
    user_can_view_reports = any(m.can_view_reports for m in memberships)
    user_can_view_net_profit = any(m.can_view_net_profit for m in memberships)
    user_can_manage_referrals = any(m.can_manage_referrals for m in memberships)
    user_can_trigger_automation = any(m.can_trigger_automation for m in memberships)
    user_can_view_commission = any(m.can_view_commission for m in memberships)
    user_can_view_banking = any(m.can_view_banking for m in memberships)
    
    # Also check if automation is enabled for any of the user's organizations
    automation_enabled = organizations.filter(is_automation_enabled=True).exists()

    total_outstanding_referral_balance = Decimal("0")
    if is_owner or user_can_manage_referrals:
        # Sum from all service records in accessible organizations (ignoring handled_by)
        service_outstanding = ServiceRecord.objects.filter(
            organization__in=organizations,
            is_referral_paid=False
        ).aggregate(
            total=Sum('referral_balance')
        )['total'] or Decimal("0")
        
        # Sum from initial balances of referrals in accessible orgs
        initial_outstanding = Referral.objects.filter(
            organization__in=organizations
        ).aggregate(
            total=Sum('initial_balance')
        )['total'] or Decimal("0")
        
        total_outstanding_referral_balance = service_outstanding + initial_outstanding

    # Automation data
    # Only show logs from psbs that have automation enabled
    automation_logs = AutomationLog.objects.filter(
        organization__in=organizations,
        organization__is_automation_enabled=True
    ).select_related("vehicle", "client").order_by("-timestamp")[:5]
    
    # Upcoming expirations (next 45 days)
    # Only show vehicles from psbs that have automation enabled
    upcoming_expirations = Vehicle.objects.filter(
        client__organization__in=organizations,
        client__organization__is_automation_enabled=True,
        registration_expiration_date__gte=today,
        registration_expiration_date__lte=today + timedelta(days=45)
    ).select_related("client").order_by("registration_expiration_date")[:5]

    # Location Comparison (Owner Only)
    location_stats = []
    if is_owner and not request.session.get('active_org_id') and organizations.count() > 1:
        for org in organizations:
            org_records = ServiceRecord.objects.filter(organization=org)
            location_stats.append({
                'id': org.id,
                'name': org.name,
                'city': org.city,
                'daily_profit': org_records.filter(created_at__date=today).aggregate(Sum('processing_fee'))['processing_fee__sum'] or 0,
                'monthly_profit': org_records.filter(created_at__date__gte=month_start).aggregate(Sum('processing_fee'))['processing_fee__sum'] or 0,
                'total_records': org_records.count(),
            })
        location_stats = sorted(location_stats, key=lambda x: x['monthly_profit'], reverse=True)

    pending_intakes = ClientIntake.objects.filter(organization__in=organizations, status=ClientIntake.Status.PENDING).order_by("-created_at")
    for intake in pending_intakes:
        intake.vin_exists = Vehicle.objects.filter(vin=intake.vin).exists()

    return render(
        request,
        "core/dashboard.html",
        {
            "location_stats": location_stats,
            "memberships": memberships,
            "owner_agents": owner_agents,
            "user_can_view_reports": user_can_view_reports,
            "user_can_view_net_profit": user_can_view_net_profit,
            "is_owner": is_owner,
            "owner_orgs": owner_orgs,
            "service_records": service_records,
            "audit_logs": audit_logs,
            "service_totals": service_totals,
            "status_totals": status_totals,
            "overall_amount": overall_amount,
            "overall_net_profit": overall_net_profit,
            "pending_intakes": pending_intakes,
            "yearly_report": yearly_report,
            "monthly_report": monthly_report,
            "daily_report": daily_report,
            "service_cards": service_cards,
            "show_all_services_card": show_all_services_card,
            "today": today,
            "overall_card_fees": overall_totals["total_card"] or Decimal("0"),
            "total_outstanding_referral_balance": total_outstanding_referral_balance,
            "automation_logs": automation_logs,
            "upcoming_expirations": upcoming_expirations,
            "custom_types": custom_types,
            "user_can_manage_referrals": user_can_manage_referrals,
            "automation_enabled": automation_enabled,
            "user_can_trigger_automation": user_can_trigger_automation,
            "user_can_view_commission": user_can_view_commission,
            "user_can_view_banking": user_can_view_banking,
        },
    )


@login_required
def owner_report_pdf(request):
    owner_org_ids = set(
        OrganizationMembership.objects.filter(
            user=request.user, role=OrganizationMembership.Role.OWNER
        ).values_list("organization_id", flat=True)
    )
    if not owner_org_ids:
        return HttpResponseForbidden("Owner access required.")

    report_rows = (
        ServiceRecord.objects.filter(organization_id__in=owner_org_ids)
        .values("organization__name", "service_type", "status")
        .annotate(
            total=Count("id"),
            amount=Sum("service_fee"),
            processing=Sum("processing_fee"),
            dmv=Sum("dmv_fee"),
            tax=Sum("sales_tax"),
            card=Sum("credit_card_fee"),
        )
        .order_by("organization__name", "service_type")
    )
    totals = ServiceRecord.objects.filter(organization_id__in=owner_org_ids).aggregate(
        total_amount=Sum("service_fee"),
        total_processing=Sum("processing_fee"),
        total_dmv=Sum("dmv_fee"),
        total_tax=Sum("sales_tax"),
        total_card=Sum("credit_card_fee"),
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="owner-service-report.pdf"'
    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin_x = 48
    content_width = width - (margin_x * 2)
    y = height - 62

    org_for_logo = Organization.objects.filter(id__in=owner_org_ids).order_by("id").first()
    pdf.setFillColorRGB(0.06, 0.24, 0.47)
    pdf.roundRect(margin_x, y - 34, content_width, 60, 10, fill=1, stroke=0)
    _draw_org_logo(pdf, org_for_logo, margin_x + 12, y + 10, size=24)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(width / 2, y + 10, "Owner Financial Service Report")
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(width / 2, y - 4, f"Owner: {request.user.username}")
    pdf.drawCentredString(width / 2, y - 16, "Professional DMV printable layout")
    y -= 48
    columns = [
        ("Org", 78),
        ("Service", 74),
        ("Status", 50),
        ("Count", 38),
        ("Processing", 58),
        ("Total Gross", 58),
        ("DMV", 52),
        ("Tax", 52),
        ("Card", 50),
    ]
    table_x = margin_x
    row_height = 14

    def draw_header(current_y):
        pdf.setFillColorRGB(0.95, 0.97, 1)
        pdf.roundRect(table_x, current_y - 10, content_width, 18, 5, fill=1, stroke=0)
        pdf.setFillColorRGB(0.12, 0.2, 0.34)
        pdf.setFont("Helvetica-Bold", 8)
        running_x = table_x
        for title, col_width in columns:
            pdf.drawCentredString(running_x + (col_width / 2), current_y - 2, title)
            running_x += col_width
        return current_y - 16

    y = draw_header(y)
    pdf.setFont("Helvetica", 7)

    for row in report_rows:
        pdf.setFillColor(colors.whitesmoke if int(y / row_height) % 2 == 0 else colors.white)
        pdf.rect(table_x, y - 3, content_width, 12, fill=1, stroke=0)
        pdf.setStrokeColorRGB(0.86, 0.9, 0.96)
        pdf.rect(table_x, y - 3, content_width, 12, fill=0, stroke=1)
        pdf.setFillColor(colors.black)

        cells = [
            row["organization__name"],
            str(row["service_type"]).replace("_", " ").title(),
            str(row["status"]).title(),
            row["total"],
            _currency(row["processing"]),
            _currency(row["amount"]),
            _currency(row["dmv"]),
            _currency(row["tax"]),
            _currency(row["card"]),
        ]
        running_x = table_x
        for idx, (_, col_width) in enumerate(columns):
            text = _fit_text(cells[idx], col_width - 6, font_size=7)
            pdf.drawCentredString(running_x + (col_width / 2), y, text)
            if idx < len(columns) - 1:
                pdf.setStrokeColorRGB(0.86, 0.9, 0.96)
                pdf.line(running_x + col_width, y - 3, running_x + col_width, y + 9)
            running_x += col_width
        y -= 12
        if y < 84:
            pdf.showPage()
            y = height - 62
            pdf.setFillColorRGB(0.06, 0.24, 0.47)
            pdf.roundRect(margin_x, y - 34, content_width, 60, 10, fill=1, stroke=0)
            _draw_org_logo(pdf, org_for_logo, margin_x + 12, y + 10, size=24)
            pdf.setFillColorRGB(1, 1, 1)
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawCentredString(width / 2, y + 10, "Owner Financial Service Report")
            pdf.setFont("Helvetica", 9)
            pdf.drawCentredString(width / 2, y - 4, f"Owner: {request.user.username}")
            pdf.drawCentredString(width / 2, y - 16, "Professional DMV printable layout")
            y -= 48
            pdf.setFont("Helvetica", 7)
            y = draw_header(y)

    y -= 10
    pdf.setFillColorRGB(0.93, 0.96, 1)
    pdf.roundRect(margin_x, y - 62, content_width, 66, 8, fill=1, stroke=0)
    y -= 12
    pdf.setFillColorRGB(0.1, 0.18, 0.28)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(width / 2, y, f"Net Profit (Processing Fees): {_currency(totals['total_processing'])}")
    y -= 16
    pdf.drawCentredString(width / 2, y, f"Gross Collections: {_currency(totals['total_amount'])}")
    y -= 16
    pdf.drawCentredString(
        width / 2,
        y,
        f"DMV Fees: {_currency(totals['total_dmv'])} | Sales Tax: {_currency(totals['total_tax'])} | Card Fees: {_currency(totals['total_card'])}",
    )

    pdf.save()
    return response


@login_required
def monthly_report_pdf(request):
    owner_org_ids = set(
        OrganizationMembership.objects.filter(
            user=request.user, role=OrganizationMembership.Role.OWNER
        ).values_list("organization_id", flat=True)
    )
    if not owner_org_ids:
        return HttpResponseForbidden("Owner access required.")

    today = timezone.localdate()
    month_start = today.replace(day=1)
    monthly_qs = ServiceRecord.objects.filter(
        organization_id__in=owner_org_ids,
        created_at__date__gte=month_start,
        created_at__date__lte=today,
    )
    totals = monthly_qs.aggregate(
        total_amount=Sum("service_fee"),
        total_processing=Sum("processing_fee"),
        total_dmv=Sum("dmv_fee"),
        total_tax=Sum("sales_tax"),
        total_card=Sum("credit_card_fee"),
    )
    status = {
        "completed": monthly_qs.filter(status="completed").count(),
        "pending": monthly_qs.filter(status="pending").count(),
        "failed": monthly_qs.filter(status="failed").count(),
        "total_records": monthly_qs.count(),
    }

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="monthly-insights-dashboard.pdf"'
    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin_x = 40
    content_width = width - (margin_x * 2)
    
    # Premium Color Palette
    electric_blue = colors.Color(0.0, 0.45, 0.95)
    emerald = colors.Color(0.06, 0.63, 0.45)
    amethyst = colors.Color(0.6, 0.2, 0.8)
    dark_slate = colors.Color(0.07, 0.1, 0.15)
    soft_gray = colors.Color(0.97, 0.98, 1.0)
    border_color = colors.Color(0.9, 0.92, 0.95)

    def draw_dashboard_frame():
        # Vibrant Left Sidebar Accent
        pdf.setFillColor(electric_blue)
        pdf.rect(0, 0, 8, height, fill=1, stroke=0)
        
        # Soft background for the main area
        pdf.setFillColor(colors.white)
        pdf.rect(8, 0, width-8, height, fill=1, stroke=0)
        
        # Header area
        pdf.setFillColor(dark_slate)
        pdf.rect(8, height - 120, width-8, 120, fill=1, stroke=0)
        
        org_for_logo = Organization.objects.filter(id__in=owner_org_ids).order_by("id").first()
        
        # Logo Frame (White rounded box)
        pdf.setFillColor(colors.white)
        pdf.roundRect(margin_x, height - 90, 60, 60, 10, fill=1, stroke=0)
        # Center logo in frame
        _draw_org_logo(pdf, org_for_logo, margin_x + 5, height - 35, size=50)
        
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 26)
        pdf.drawString(margin_x + 80, height - 60, "Monthly Insights")
        
        pdf.setFont("Helvetica", 11)
        pdf.setFillColor(colors.Color(0.7, 0.75, 0.8))
        pdf.drawString(margin_x + 80, height - 80, f"PSB Performance Dashboard | {month_start.strftime('%B %Y')}")
        
        # Date Pill
        pdf.setFillColor(electric_blue)
        pdf.roundRect(width - 160, height - 75, 120, 24, 12, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawCentredString(width - 100, height - 68, today.strftime('%d %b, %Y'))

    draw_dashboard_frame()
    y = height - 160

    # High-Impact Summary Cards
    stats = [
        ("Net Profit", _currency(totals['total_processing'] or 0), emerald, "Total PSB Income"),
        ("Gross Sales", _currency(totals['total_amount'] or 0), electric_blue, "Total amount collected"),
        ("Active Cases", str(status['total_records']), amethyst, "Monthly volume"),
        ("Efficiency", f"{(status['completed']/status['total_records']*100 if status['total_records'] > 0 else 0):.1f}%", colors.black, "Success rate"),
    ]

    card_w = (content_width - 30) / 4
    curr_x = margin_x
    for label, val, color, desc in stats:
        # Card Shadow/Border
        pdf.setFillColor(soft_gray)
        pdf.roundRect(curr_x, y - 70, card_w, 80, 10, fill=1, stroke=0)
        pdf.setStrokeColor(border_color)
        pdf.roundRect(curr_x, y - 70, card_w, 80, 10, fill=0, stroke=1)
        
        # Label
        pdf.setFillColor(colors.Color(0.4, 0.45, 0.5))
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(curr_x + 12, y - 15, label.upper())
        
        # Value
        pdf.setFillColor(color)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(curr_x + 12, y - 42, val)
        
        # Description
        pdf.setFillColor(colors.Color(0.6, 0.6, 0.6))
        pdf.setFont("Helvetica-Oblique", 7)
        pdf.drawString(curr_x + 12, y - 60, desc)
        
        curr_x += card_w + 10

    y -= 120
    
    # Leaderboard Section
    pdf.setFillColor(dark_slate)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin_x, y, "Service Performance Leaderboard")
    
    # Vibrant Section Underline
    pdf.setFillColor(electric_blue)
    pdf.rect(margin_x, y - 6, 40, 3, fill=1, stroke=0)
    y -= 35

    # Modern Header
    pdf.setFillColor(soft_gray)
    pdf.roundRect(margin_x, y - 5, content_width, 28, 6, fill=1, stroke=0)
    pdf.setFillColor(dark_slate)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin_x + 15, y + 2, "RANK / SERVICE DESCRIPTION")
    pdf.drawCentredString(width/2 + 50, y + 2, "VOLUME")
    pdf.drawRightString(width - margin_x - 15, y + 2, "TOTAL REVENUE")
    y -= 32

    rows = (
        monthly_qs.values("service_type")
        .annotate(total=Count("id"), amount=Sum("service_fee"))
        .order_by("-total")
    )
    service_map = dict(ServiceRecord.SERVICE_TYPES)
    for ct in CustomServiceType.objects.filter(organization_id__in=owner_org_ids):
        service_map[ct.key] = ct.label
    
    rank = 1
    for row in rows:
        # Row Divider
        pdf.setStrokeColor(border_color)
        pdf.setLineWidth(0.5)
        pdf.line(margin_x, y - 8, width - margin_x, y - 8)
        
        # Rank Pill
        pdf.setFillColor(colors.Color(0.9, 0.94, 1))
        pdf.roundRect(margin_x + 10, y - 4, 20, 16, 8, fill=1, stroke=0)
        pdf.setFillColor(electric_blue)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawCentredString(margin_x + 20, y + 1, str(rank))
        
        # Data
        pdf.setFillColor(dark_slate)
        pdf.setFont("Helvetica-Bold", 10)
        name = service_map.get(row["service_type"], row["service_type"])
        pdf.drawString(margin_x + 40, y + 1, name[:45].upper())
        
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(width/2 + 50, y + 1, f"{row['total']} records")
        
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawRightString(width - margin_x - 15, y + 1, _currency(row["amount"]))
        
        y -= 28
        rank += 1
        if y < 80:
            pdf.showPage()
            draw_dashboard_frame()
            y = height - 160

    # Final Footer
    pdf.setFillColor(dark_slate)
    pdf.rect(0, 0, width, 25, fill=1, stroke=0)
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors.white)
    pdf.drawCentredString(width/2, 8, "© 2024 RegiManager Intelligence Platform | Secure Transaction Report")

    pdf.save()
    return response
@login_required
def daily_report_pdf(request):
    owner_org_ids = set(
        OrganizationMembership.objects.filter(
            user=request.user, role=OrganizationMembership.Role.OWNER
        ).values_list("organization_id", flat=True)
    )
    if not owner_org_ids:
        return HttpResponseForbidden("Owner access required.")

    today = timezone.localdate()
    daily_qs = ServiceRecord.objects.filter(
        organization_id__in=owner_org_ids,
        created_at__date=today,
    )
    totals = daily_qs.aggregate(
        total_amount=Sum("service_fee"),
        total_processing=Sum("processing_fee"),
        total_dmv=Sum("dmv_fee"),
        total_tax=Sum("sales_tax"),
        total_card=Sum("credit_card_fee"),
    )
    status = {
        "completed": daily_qs.filter(status="completed").count(),
        "pending": daily_qs.filter(status="pending").count(),
        "failed": daily_qs.filter(status="failed").count(),
        "total_records": daily_qs.count(),
    }

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="daily-report-{today}.pdf"'
    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin_x = 40
    content_width = width - (margin_x * 2)
    
    # Premium Color Palette (Daily Edition)
    vibrant_amber = colors.Color(1.0, 0.6, 0.0)
    charcoal = colors.Color(0.12, 0.15, 0.18)
    soft_slate = colors.Color(0.96, 0.97, 0.98)
    border_color = colors.Color(0.9, 0.92, 0.94)

    def draw_daily_frame():
        # Vibrant Left Sidebar Accent (Amber for Daily)
        pdf.setFillColor(vibrant_amber)
        pdf.rect(0, 0, 8, height, fill=1, stroke=0)
        
        pdf.setFillColor(colors.white)
        pdf.rect(8, 0, width-8, height, fill=1, stroke=0)
        
        # Header area
        pdf.setFillColor(charcoal)
        pdf.rect(8, height - 120, width-8, 120, fill=1, stroke=0)
        
        org_for_logo = Organization.objects.filter(id__in=owner_org_ids).order_by("id").first()
        
        # Logo Frame (White rounded box)
        pdf.setFillColor(colors.white)
        pdf.roundRect(margin_x, height - 90, 60, 60, 10, fill=1, stroke=0)
        # Center logo in frame
        _draw_org_logo(pdf, org_for_logo, margin_x + 5, height - 35, size=50)
        
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 26)
        pdf.drawString(margin_x + 80, height - 60, "Daily Insights")
        
        pdf.setFont("Helvetica", 11)
        pdf.setFillColor(colors.Color(0.7, 0.7, 0.7))
        pdf.drawString(margin_x + 80, height - 80, f"PSB Activity Audit | {today.strftime('%A, %B %d, %Y')}")
        
        # Status Pill
        pdf.setFillColor(vibrant_amber)
        pdf.roundRect(width - 160, height - 75, 120, 24, 12, fill=1, stroke=0)
        pdf.setFillColor(charcoal)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawCentredString(width - 100, height - 68, "LIVE LOG")

    draw_daily_frame()
    y = height - 160

    # Summary Statistics Grid
    stats = [
        ("Daily Profit", _currency(totals['total_processing'] or 0), vibrant_amber, "Total PSB Income"),
        ("Gross Collections", _currency(totals['total_amount'] or 0), charcoal, "Total amount collected"),
        ("Transactions", str(status['total_records']), colors.Color(0.3, 0.3, 0.3), "Files processed"),
        ("Pending", str(status['pending']), colors.red, "Needs attention"),
    ]

    card_w = (content_width - 30) / 4
    curr_x = margin_x
    for label, val, color, desc in stats:
        pdf.setFillColor(soft_slate)
        pdf.roundRect(curr_x, y - 70, card_w, 80, 10, fill=1, stroke=0)
        pdf.setStrokeColor(border_color)
        pdf.roundRect(curr_x, y - 70, card_w, 80, 10, fill=0, stroke=1)
        
        pdf.setFillColor(colors.Color(0.4, 0.45, 0.5))
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(curr_x + 12, y - 15, label.upper())
        
        pdf.setFillColor(color)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(curr_x + 12, y - 42, val)
        
        pdf.setFillColor(colors.Color(0.6, 0.6, 0.6))
        pdf.setFont("Helvetica-Oblique", 7)
        pdf.drawString(curr_x + 12, y - 60, desc)
        
        curr_x += card_w + 10

    y -= 120
    
    # Daily Volume List
    pdf.setFillColor(charcoal)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin_x, y, "Daily Transaction Breakdown")
    pdf.setFillColor(vibrant_amber)
    pdf.rect(margin_x, y - 6, 40, 3, fill=1, stroke=0)
    y -= 35

    # Modern Header
    pdf.setFillColor(soft_slate)
    pdf.roundRect(margin_x, y - 5, content_width, 28, 6, fill=1, stroke=0)
    pdf.setFillColor(charcoal)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin_x + 15, y + 2, "SERVICE TYPE / DESCRIPTION")
    pdf.drawCentredString(width/2 + 50, y + 2, "VOLUME")
    pdf.drawRightString(width - margin_x - 15, y + 2, "COLLECTIONS")
    y -= 32

    rows = (
        daily_qs.values("service_type")
        .annotate(total=Count("id"), amount=Sum("service_fee"))
        .order_by("-total")
    )
    service_map = dict(ServiceRecord.SERVICE_TYPES)
    for ct in CustomServiceType.objects.filter(organization_id__in=owner_org_ids):
        service_map[ct.key] = ct.label
    
    for row in rows:
        pdf.setStrokeColor(border_color)
        pdf.setLineWidth(0.5)
        pdf.line(margin_x, y - 8, width - margin_x, y - 8)
        
        pdf.setFillColor(charcoal)
        pdf.setFont("Helvetica-Bold", 10)
        name = service_map.get(row["service_type"], row["service_type"])
        pdf.drawString(margin_x + 15, y + 1, name.upper())
        
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(width/2 + 50, y + 1, str(row['total']))
        
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawRightString(width - margin_x - 15, y + 1, _currency(row["amount"]))
        
        y -= 28
        if y < 80:
            pdf.showPage()
            draw_daily_frame()
            y = height - 160

    # Daily Footer
    pdf.setFillColor(charcoal)
    pdf.rect(0, 0, width, 25, fill=1, stroke=0)
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors.white)
    pdf.drawCentredString(width/2, 8, "Generated by RegiManager Financial System | Daily Audit Summary")

    pdf.save()
    return response


@login_required
def service_receipt_pdf(request, service_id):
    service_record = get_object_or_404(ServiceRecord, pk=service_id)
    can_access = OrganizationMembership.objects.filter(
        user=request.user,
        organization=service_record.organization,
    ).exists()
    if not can_access:
        return HttpResponseForbidden("You do not have access to this receipt.")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="receipt-{service_record.receipt_number}.pdf"'
    )

    pdf = canvas.Canvas(response, pagesize=letter)
    width, height = letter
    margin_x = 40
    content_width = width - (margin_x * 2)
    y = height - 50

    receipt_parts = str(service_record.receipt_number).split('-')
    receipt_short = receipt_parts[1][-6:] if len(receipt_parts) > 1 else str(service_record.receipt_number)[:6]

    pdf.setFont("Helvetica-Bold", 16)
    org_name = service_record.organization.name.upper()
    pdf.drawString(margin_x, y, org_name)
    
    y -= 25
    pdf.setFont("Helvetica-Bold", 10)
    address = f"{service_record.organization.address_line} {service_record.organization.city}, {service_record.organization.state}"
    pdf.drawString(margin_x, y, "PSBC")
    pdf.drawString(margin_x + 50, y, address.upper()[:50])
    y -= 12
    pdf.drawString(margin_x, y, f"No. {receipt_short}")
    pdf.drawString(margin_x + 50, y, address.upper()[50:])

    y -= 25
    pdf.setFont("Helvetica", 9)
    # the image shows specific email/phone formatting
    email = service_record.organization.email if hasattr(service_record.organization, 'email') else "info@xpressplates.com"
    pdf.drawString(margin_x, y, f"Email: {email}")
    pdf.drawString(margin_x + 180, y, "Phone: 914 961-6666")
    pdf.drawString(margin_x + 300, y, "Fax: 914 961-6633")

    y -= 30
    
    def draw_box(x, y_pos, w, h, label, val):
        pdf.setFont("Helvetica", 8)
        pdf.drawString(x, y_pos + 3, label)
        pdf.rect(x, y_pos - h, w, h)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(x + 4, y_pos - h + 5, str(val))
        return x + w

    # Upper Row
    dt = service_record.transaction_date or service_record.created_at.date()
    date_str = dt.strftime("%b %d, %Y")
    time_str = service_record.created_at.strftime("%I:%M %p")
    
    x = margin_x
    draw_box(x, y, 80, 16, "Transaction Date", date_str)
    x += 85
    draw_box(x, y, 60, 16, "Time", time_str)
    x += 65
    draw_box(x, y, 80, 16, "Terminal Number", service_record.terminal_number)
    x += 85
    draw_box(x, y, 80, 16, "Receipt number", receipt_short)
    x += 85
    vehicle_number = service_record.vehicle_number
    if not vehicle_number and service_record.vehicle:
        vehicle_number = service_record.vehicle.vehicle_number
    vehicle_number = vehicle_number or ""

    draw_box(x, y, 80, 16, "Vehicle number", vehicle_number)
    x += 85
    draw_box(x, y, 70, 16, "Transaction type", service_record.transaction_type)

    y -= 45
    client_name = service_record.client_name
    if not client_name and service_record.vehicle and service_record.vehicle.client:
        client_name = service_record.vehicle.client.name
    client_name = (client_name or "").upper()
    draw_box(margin_x, y, 380, 16, "Client", client_name)

    y -= 45
    client_address = service_record.client_address
    if not client_address and service_record.vehicle and service_record.vehicle.client:
        client_address = service_record.vehicle.client.full_address
    client_address = (client_address or "").upper()
    draw_box(margin_x, y, 380, 16, "Client Address", client_address)

    y -= 40
    
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(margin_x, y, "SERVICES PROVIDED")
    pdf.drawString(margin_x + 220, y, "DMV FEE")
    org_first_word = org_name.split()[0][:10] if org_name else "XPRESS"
    pdf.drawString(margin_x + 340, y, f"{org_first_word} FEE")

    y -= 15

    # Define the exact fixed rows based on the receipt image
    fixed_rows = [
        ("PLATE SURRENDER", "surrender_plates"),
        ("VEHICLE REGISTRATION", "vehicle_registration"),
        ("MOTORCYCLE REGISTRATION", "motorcycle_registration"),
        ("REGISTRATION RENEWAL", "registration_renewal"),
        ("DUPLICATE REGISTRATION", "duplicate_registration"),
        ("DUPLICATE TITLE", "duplicate_title"),
        ("TITLE ONLY", "title_only"),
        ("NEW PLATES", "new_plates"),
        ("PLATE TRANSFER", "transfer_plate")
    ]

    for label, type_key in fixed_rows:
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margin_x, y - 8, label)
        
        dmv_val = "$ 0.00"
        org_val = "$ 0.00"
        
        if service_record.service_type == type_key:
            dmv_val = _currency(service_record.dmv_fee)
            org_val = _currency(service_record.processing_fee)

        # DMV Box
        pdf.rect(margin_x + 220, y - 16, 80, 16)
        pdf.drawRightString(margin_x + 296, y - 11, dmv_val)

        # ORG Box
        pdf.rect(margin_x + 340, y - 16, 80, 16)
        pdf.drawRightString(margin_x + 416, y - 11, org_val)
        
        y -= 25

    # OTHER Row
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margin_x, y - 8, "OTHER")
    pdf.rect(margin_x + 220, y - 16, 80, 16)
    pdf.drawRightString(margin_x + 296, y - 11, _currency(service_record.other_dmv_fee))
    pdf.rect(margin_x + 340, y - 16, 80, 16)
    pdf.drawRightString(margin_x + 416, y - 11, _currency(service_record.other_fees))

    y -= 25

    # SALES TAX Row
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margin_x, y - 8, "SALES TAX")
    pdf.rect(margin_x + 220, y - 16, 80, 16)
    pdf.drawRightString(margin_x + 296, y - 11, _currency(service_record.dmv_sales_tax))
    pdf.rect(margin_x + 340, y - 16, 80, 16)
    pdf.drawRightString(margin_x + 416, y - 11, _currency(service_record.sales_tax))

    y -= 30

    # Sub total
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margin_x, y - 8, "SUB TOTAL")
    pdf.rect(margin_x + 220, y - 16, 80, 16)
    pdf.setFont("Helvetica-Bold", 9)
    total_dmv = service_record.dmv_fee + service_record.dmv_sales_tax + service_record.other_dmv_fee
    pdf.drawRightString(margin_x + 296, y - 11, _currency(total_dmv))
    
    pdf.rect(margin_x + 340, y - 16, 80, 16)
    total_psb = service_record.processing_fee + service_record.sales_tax + service_record.other_fees
    pdf.drawRightString(margin_x + 416, y - 11, _currency(total_psb))

    y -= 40
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin_x, y - 6, "GRAND TOTAL")
    
    pdf.setLineWidth(1.5)
    pdf.setFillColorRGB(0.92, 0.92, 0.92) # Light gray background
    pdf.rect(margin_x + 220, y - 18, 200, 24, fill=1)
    
    pdf.setFillColorRGB(0, 0, 0) # Back to black text
    pdf.setFont("Helvetica-Bold", 14)
    # Center horizontally at margin_x + 320, and vertically at y - 12
    pdf.drawCentredString(margin_x + 320, y - 12, _currency(service_record.service_fee))
    
    pdf.setLineWidth(1) # Reset line width

    # Signatures
    sig_y = height - 510
    pdf.setStrokeColorRGB(0,0,0)
    pdf.line(margin_x + 440, sig_y, margin_x + 550, sig_y)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(margin_x + 495, sig_y - 12, "CLIENT SIGNATURE")

    sig_y -= 40
    pdf.setFont("Helvetica", 9)
    agent_name = service_record.handled_by.get_full_name() or service_record.handled_by.username
    pdf.drawString(margin_x + 440, sig_y, f"Agent Name: {agent_name}")

    sig_y -= 40
    # Draw the agent signature image if it exists
    try:
        membership = OrganizationMembership.objects.filter(
            organization=service_record.organization, user=service_record.handled_by
        ).first()
        if membership and membership.signature and os.path.exists(membership.signature.path):
            pdf.drawImage(
                membership.signature.path,
                margin_x + 455,
                sig_y + 2,
                width=80,
                height=30,
                mask='auto'
            )
    except Exception:
        pass

    pdf.line(margin_x + 440, sig_y, margin_x + 550, sig_y)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(margin_x + 495, sig_y - 12, "AGENT SIGNATURE")

    # Payment details table  — extra vertical gap below grand total
    py = 115
    # thin separator line above the payment table
    pdf.setLineWidth(0.5)
    pdf.setStrokeColorRGB(0.7, 0.7, 0.7)
    pdf.line(margin_x, py + 42, margin_x + 530, py + 42)
    pdf.setLineWidth(1)
    pdf.setStrokeColorRGB(0, 0, 0)

    pdf.rect(margin_x, py, 530, 32)
    # vertical lines
    pdf.line(margin_x + 110, py, margin_x + 110, py + 32)
    pdf.line(margin_x + 280, py, margin_x + 280, py + 32)
    pdf.line(margin_x + 350, py, margin_x + 350, py + 32)
    pdf.line(margin_x + 420, py, margin_x + 420, py + 32)
    # horizontal line
    pdf.line(margin_x, py + 16, margin_x + 530, py + 16)

    # headers
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin_x + 4, py + 20, "Date and time")
    pdf.drawString(margin_x + 114, py + 20, "Payment description")
    pdf.drawString(margin_x + 284, py + 20, "Amount")
    pdf.drawString(margin_x + 354, py + 20, "CC Fees")
    pdf.drawString(margin_x + 424, py + 20, "Paid Amount")

    # values
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin_x + 4, py + 5, dt.strftime("%b %d, %Y %I:%M %p"))
    pdf.drawString(margin_x + 114, py + 5, service_record.get_payment_method_display() + " Payment")
    
    amt_no_fee = service_record.service_fee - service_record.credit_card_fee
    pdf.drawRightString(margin_x + 346, py + 5, _currency(amt_no_fee))
    pdf.drawRightString(margin_x + 416, py + 5, _currency(service_record.credit_card_fee))
    pdf.drawRightString(margin_x + 526, py + 5, _currency(service_record.paid_amount))

    # bottom totals
    py -= 35
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(margin_x, py + 4, "Total CC Fees")
    pdf.rect(margin_x + 60, py, 60, 16)
    pdf.drawRightString(margin_x + 116, py + 4, _currency(service_record.credit_card_fee))

    pdf.drawString(margin_x + 130, py + 4, "Total Paid")
    pdf.rect(margin_x + 180, py, 70, 16)
    pdf.drawRightString(margin_x + 246, py + 4, _currency(service_record.paid_amount))

    pdf.drawString(margin_x + 260, py + 4, "Outstanding Balance")
    pdf.rect(margin_x + 355, py, 60, 16)
    outstanding_str = _currency(service_record.referral_balance) if service_record.referral_balance and service_record.referral_balance > 0 else "$ 0.00"
    pdf.drawRightString(margin_x + 411, py + 4, outstanding_str)

    # Footer
    pdf.setFont("Helvetica-Bold", 8)
    footer_text = "This is a licensed Private Service Bureau but is not an official psb of the Department of Motor Vehicles, State of New York."
    pdf.drawCentredString(width / 2, 40, footer_text)

    pdf.save()
    return response


def logout_view(request):
    logout(request)
    return redirect("login")


from django.views.decorators.clickjacking import xframe_options_exempt
from pypdf import PdfReader, PdfWriter
import os

@xframe_options_exempt
def generate_dmv_form(request, form_type, service_id):
    """
    Brilliant central hub for generating all official NYS DMV forms.
    """
    service = get_object_or_404(ServiceRecord, id=service_id)
    if not _has_active_org_access(request.user, service.organization_id):
        return HttpResponseForbidden("Access denied.")

    vehicle = service.vehicle
    if not vehicle and service.vin:
        vehicle = Vehicle.objects.filter(vin=service.vin).first()
    client = vehicle.client if vehicle else None
    prefill = _build_form_prefill_payload(service, client, vehicle)
    
    # Path mapping - using local paths within core app
    current_dir = os.path.dirname(os.path.abspath(__file__))
    form_map = {
        "mv82": "static/core/pdf/mv82_template.pdf",
        "dtf802": "static/core/pdf/dtf802_template.pdf",
        "dtf803": "static/core/pdf/dtf803_template.pdf",
        "mv82b": "static/core/pdf/mv82b_template.pdf",
    }
    
    template_path = os.path.join(current_dir, form_map.get(form_type, form_map["mv82"]))
    if not os.path.exists(template_path):
        template_path = os.path.join(current_dir, form_map["mv82"])

    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 10)
    
    if form_type == "mv82":
        _fill_mv82_overlay(can, service, client, vehicle)
    elif form_type == "dtf802":
        _fill_dtf802_overlay(can, service, client, vehicle)
    elif form_type == "dtf803":
        _fill_dtf803_overlay(can, service, client, vehicle)
    elif form_type == "mv82b":
        _fill_mv82b_overlay(can, service, client, vehicle)
    
    can.save()
    packet.seek(0)
    new_pdf = PdfReader(packet)
    template_pdf = PdfReader(template_path)
    output = PdfWriter()
    from pypdf.generic import NameObject

    page1 = template_pdf.pages[0]
    page1.merge_page(new_pdf.pages[0])
    output.add_page(page1)
    if len(template_pdf.pages) > 1:
        output.add_page(template_pdf.pages[1])

    if "/AcroForm" in template_pdf.trailer["/Root"]:
        output._root_object.update({
            NameObject("/AcroForm"): template_pdf.trailer["/Root"]["/AcroForm"]
        })

        fields = _build_acroform_prefill_fields(form_type, prefill)
        if not fields and form_type in ("dtf802", "dtf803"):
            # Conservative token-based DTF mapping (safe fallback).
            fields = _build_dtf_token_prefill_fields(template_pdf, prefill)
        if fields:
            for page in output.pages:
                output.update_page_form_field_values(page, fields)

    final_output = io.BytesIO()
    output.write(final_output)
    final_output.seek(0)
    response = HttpResponse(final_output.read(), content_type="application/pdf")
    filename = f"PREFILLED-{form_type.upper()}-{service.vin or service.id}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@xframe_options_exempt
@login_required
def generate_dmv_form_vehicle(request, form_type, vehicle_id):
    """
    Generates all official NYS DMV forms directly from a Vehicle (no ServiceRecord needed).
    """
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    if not _has_active_org_access(request.user, vehicle.client.organization_id):
        return HttpResponseForbidden("Access denied.")

    client = vehicle.client
    prefill = _build_form_prefill_payload(None, client, vehicle)
    
    # Path mapping - using local paths within core app
    current_dir = os.path.dirname(os.path.abspath(__file__))
    form_map = {
        "mv82": "static/core/pdf/mv82_template.pdf",
        "dtf802": "static/core/pdf/dtf802_template.pdf",
        "dtf803": "static/core/pdf/dtf803_template.pdf",
        "mv82b": "static/core/pdf/mv82b_template.pdf",
    }
    
    template_path = os.path.join(current_dir, form_map.get(form_type, form_map["mv82"]))
    if not os.path.exists(template_path):
        template_path = os.path.join(current_dir, form_map["mv82"])

    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 10)
    
    if form_type == "mv82":
        _fill_mv82_overlay(can, None, client, vehicle)
    elif form_type == "dtf802":
        _fill_dtf802_overlay(can, None, client, vehicle)
    elif form_type == "dtf803":
        _fill_dtf803_overlay(can, None, client, vehicle)
    elif form_type == "mv82b":
        _fill_mv82b_overlay(can, None, client, vehicle)
    
    can.save()
    packet.seek(0)
    new_pdf = PdfReader(packet)
    template_pdf = PdfReader(template_path)
    output = PdfWriter()
    from pypdf.generic import NameObject

    page1 = template_pdf.pages[0]
    page1.merge_page(new_pdf.pages[0])
    output.add_page(page1)
    if len(template_pdf.pages) > 1:
        output.add_page(template_pdf.pages[1])

    if "/AcroForm" in template_pdf.trailer["/Root"]:
        output._root_object.update({
            NameObject("/AcroForm"): template_pdf.trailer["/Root"]["/AcroForm"]
        })

        fields = _build_acroform_prefill_fields(form_type, prefill)
        if not fields and form_type in ("dtf802", "dtf803"):
            fields = _build_dtf_token_prefill_fields(template_pdf, prefill)
        if fields:
            for page in output.pages:
                output.update_page_form_field_values(page, fields)

    final_output = io.BytesIO()
    output.write(final_output)
    final_output.seek(0)
    response = HttpResponse(final_output.read(), content_type="application/pdf")
    filename = f"PREFILLED-{form_type.upper()}-{vehicle.vin or vehicle.id}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _fill_mv82_overlay(can, service, client, vehicle):
    st = service.service_type if service else ""
    plate_str = (service.plate_number if service else None) or (vehicle.plate_number if vehicle else "")
    if plate_str:
        can.drawString(465, 615, plate_str.upper())
    if client and client.is_commercial:
        name_str = client.business_name or client.last_name
    else:
        name_str = f"{client.last_name if client else ''}, {client.first_name if client else ''} {client.middle_name or ''}"
    can.drawString(40, 588, name_str.upper())
    phone = (client.phone_number if client and client.phone_number else "").replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
    for i, char in enumerate(phone[:3]): can.drawString(463 + (i * 9), 560, char)
    for i, char in enumerate(phone[3:10]): can.drawString(493 + (i * 14.5), 560, char)
    if client and client.email:
        can.setFont("Helvetica", 8)
        can.drawString(398, 535, client.email)
        can.setFont("Helvetica-Bold", 10)
    can.drawString(535, 442, client.county.upper() if client else "")
    can.setFont("Courier-Bold", 12)
    vin_str = ((service.vin or "") if service else (vehicle.vin or "") if vehicle else "").upper()
    for i, char in enumerate(vin_str[:17]): can.drawString(38 + (i * 18.4), 407, char)
    can.setFont("Helvetica-Bold", 10)
    can.drawString(358, 407, str(vehicle.year) if vehicle else "")
    can.drawString(400, 407, vehicle.make.upper() if vehicle else "")
    # Body type checkboxes intentionally left blank (no X marks)
    can.drawString(40, 381, vehicle.color.upper() if vehicle else "")
    can.drawString(90, 381, str(vehicle.weight) if vehicle else "")
    can.drawString(34, 355, str(vehicle.cylinders) if vehicle else "")
    
    # Technical specs
    if vehicle:
        if vehicle.odometer_reading:
            can.drawString(110, 355, vehicle.odometer_reading)
        if vehicle.max_gross_weight:
            can.drawString(180, 355, vehicle.max_gross_weight)
        if vehicle.num_axles:
            can.drawString(240, 355, vehicle.num_axles)
            
    # Co-Registrant
    if vehicle and vehicle.co_registrant_name:
        can.drawString(40, 510, vehicle.co_registrant_name.upper())
        if vehicle.co_registrant_nys_id:
            can.drawString(463, 510, vehicle.co_registrant_nys_id)
            
    # Owner (if different)
    if vehicle and vehicle.owner_name:
        can.drawString(40, 320, vehicle.owner_name.upper())
        if vehicle.owner_nys_id:
            can.drawString(463, 320, vehicle.owner_nys_id)


def _fill_dtf802_overlay(can, service, client, vehicle):
    """
    DTF-802 Overlay cleared per user request.
    """
    pass

def _fill_dtf803_overlay(can, service, client, vehicle):
    """
    DTF-803 Overlay cleared per user request.
    """
    pass

def _fill_mv82b_overlay(can, service, client, vehicle):
    """
    Overlay for MV-82B (Boat Registration)
    Note: Most fields are handled via AcroForm for this document.
    """
    pass

def regenerate_mv82_document(service_document):
    from django.core.files.base import ContentFile
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject
    import io
    import os
    from django.utils import timezone

    service = service_document.service_record
    vehicle = service_document.vehicle or (service.vehicle if service else None)
    client = vehicle.client if vehicle else None
    
    if not vehicle or not client:
        return
        
    prefill = _build_form_prefill_payload(service, client, vehicle)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "static/core/pdf/mv82_template.pdf")
    if not os.path.exists(template_path):
        return
    
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    _fill_mv82_overlay(can, service, client, vehicle)
    can.save()
    packet.seek(0)
    
    new_pdf = PdfReader(packet)
    template_pdf = PdfReader(template_path)
    output = PdfWriter()

    page1 = template_pdf.pages[0]
    page1.merge_page(new_pdf.pages[0])
    output.add_page(page1)
    if len(template_pdf.pages) > 1:
        output.add_page(template_pdf.pages[1])

    if "/AcroForm" in template_pdf.trailer["/Root"]:
        output._root_object.update({
            NameObject("/AcroForm"): template_pdf.trailer["/Root"]["/AcroForm"]
        })
        fields = _build_acroform_prefill_fields("mv82", prefill)
        if fields:
            for page in output.pages:
                output.update_page_form_field_values(page, fields)

    final_output = io.BytesIO()
    output.write(final_output)
    final_output.seek(0)
    
    if service_document.file:
        try:
            service_document.file.delete(save=False)
        except Exception:
            pass
        
    doc_name = f"MV82-{vehicle.vin}-{timezone.now().strftime('%Y%m%d')}.pdf"
    service_document.file.save(doc_name, ContentFile(final_output.read()), save=True)

@login_required
@xframe_options_exempt
def intake_mv82_pdf(request, intake_id):
    """
    Allows agents to preview the MV-82 generated from an intake submission
    before it's approved.
    """
    intake = get_object_or_404(ClientIntake, id=intake_id)
    if not _has_active_org_access(request.user, intake.organization_id):
        return HttpResponseForbidden("Access denied.")

    # Mock objects for prefill
    prefill = {
        "driver_license": intake.driver_license,
        "dob_m": intake.dob.strftime("%m") if intake.dob else "",
        "dob_d": intake.dob.strftime("%d") if intake.dob else "",
        "dob_y": intake.dob.strftime("%Y") if intake.dob else "",
        "street_address": f"{intake.building_no} {intake.street_address}".strip(),
        "city": intake.city,
        "state": intake.state,
        "zip_code": intake.zip_code,
        "name_full": f"{intake.last_name}, {intake.first_name} {intake.middle_name or ''}",
        "year": str(intake.year),
        "make": intake.make,
        "model": intake.model,
        "vin": intake.vin,
        "odometer": intake.odometer_reading,
        "mgw": intake.max_gross_weight,
        "axles": intake.num_axles,
        "owner_name": intake.owner_name,
        "owner_nys_id": intake.owner_nys_id,
        "co_registrant_name": intake.co_registrant_name,
        "co_registrant_nys_id": intake.co_registrant_nys_id,
        "lienholder_name": intake.lienholder_name,
        "lienholder_address": intake.lienholder_address,
        "lien_filing_code": intake.lien_filing_code,
    }

    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "static/core/pdf/mv82_template.pdf")
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 10)
    
    # Simple overlay for preview
    name_str = prefill["name_full"]
    can.drawString(40, 588, name_str.upper())
    vin_str = (intake.vin or "").upper()
    can.setFont("Courier-Bold", 12)
    for i, char in enumerate(vin_str[:17]): can.drawString(38 + (i * 18.4), 407, char)
    can.setFont("Helvetica-Bold", 10)
    can.drawString(358, 407, prefill["year"])
    can.drawString(400, 407, prefill["make"].upper())
    
    can.save()
    packet.seek(0)
    new_pdf = PdfReader(packet)
    template_pdf = PdfReader(template_path)
    output = PdfWriter()
    from pypdf.generic import NameObject

    page1 = template_pdf.pages[0]
    page1.merge_page(new_pdf.pages[0])
    output.add_page(page1)
    if len(template_pdf.pages) > 1:
        output.add_page(template_pdf.pages[1])

    if "/AcroForm" in template_pdf.trailer["/Root"]:
        output._root_object.update({
            NameObject("/AcroForm"): template_pdf.trailer["/Root"]["/AcroForm"]
        })
        fields = _build_acroform_prefill_fields("mv82", prefill)
        if fields:
            for page in output.pages:
                output.update_page_form_field_values(page, fields)

    final_output = io.BytesIO()
    output.write(final_output)
    final_output.seek(0)
    response = HttpResponse(final_output.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="PREVIEW-MV82-{intake.vin}.pdf"'
    return response

@xframe_options_exempt
def mv82_form_pdf(request, service_id):
    return generate_dmv_form(request, "mv82", service_id)


@login_required
def mv82_interactive(request, service_id):
    """
    Renders an interactive, editable MV-82 form pre-filled with data.
    Allows agents to check marks and type before final printing.
    """
    service = get_object_or_404(ServiceRecord, pk=service_id)
    vehicle = Vehicle.objects.filter(vin=service.vin).first()
    client = vehicle.client if vehicle else None
    
    # Permission Check
    can_access = OrganizationMembership.objects.filter(
        user=request.user,
        organization=service.organization,
    ).exists()
    if not can_access:
        return HttpResponseForbidden("Access Denied.")

    context = {
        "service": service,
        "vehicle": vehicle,
        "client": client,
        "today": timezone.now().date(),
    }
    return render(request, "core/mv82_interactive.html", context)


@login_required
def service_list(request, service_type):
    organizations = _get_user_organizations(request)
    scope_qs = ServiceRecord.objects.filter(organization__in=organizations)

    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    )
    owner_org_ids = list(
        memberships.filter(role=OrganizationMembership.Role.OWNER).values_list(
            "organization_id", flat=True
        )
    )
    is_owner = bool(owner_org_ids)

    # Visibility unlocked: Agents can search all records in their PSB
    # if not is_owner:
    #     scope_qs = scope_qs.filter(handled_by=request.user)

    if service_type != "all":
        if service_type == "vehicle_registration":
            scope_qs = scope_qs.filter(service_type__in=["vehicle_registration", "duplicate_registration"])
        elif service_type == "get_title":
            scope_qs = scope_qs.filter(service_type__in=["get_title", "title_only", "duplicate_title"])
        elif service_type == "transfer_plate":
            scope_qs = scope_qs.filter(service_type__in=["transfer_plate", "new_plates"])
        else:
            scope_qs = scope_qs.filter(service_type=service_type)

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    org_filter = request.GET.get('organization', '').strip()
    agent_filter = request.GET.get('agent', '').strip()
    payment_filter = request.GET.get('payment_method', '').strip()
    source_filter = request.GET.get('source', '').strip()
    referral_filter = request.GET.get('referral', '').strip()
    min_amount = request.GET.get('min_amount', '').strip()
    max_amount = request.GET.get('max_amount', '').strip()
    sort_by = request.GET.get('sort_by', '-created_at').strip() or '-created_at'
    export_type = request.GET.get('export', '').strip().lower()

    if search_query:
        scope_qs = scope_qs.filter(
            Q(client_name__icontains=search_query) |
            Q(client_identifier__icontains=search_query) |
            Q(receipt_number__icontains=search_query) |
            Q(vehicle__client__first_name__icontains=search_query) |
            Q(vehicle__client__last_name__icontains=search_query)
        )

    if status_filter in dict(ServiceRecord.STATUS_CHOICES):
        scope_qs = scope_qs.filter(status=status_filter)

    org_ids = set(organizations.values_list("id", flat=True))
    if org_filter and org_filter.isdigit() and int(org_filter) in org_ids:
        scope_qs = scope_qs.filter(organization_id=int(org_filter))

    accessible_agents = User.objects.filter(
        organization_memberships__organization__in=organizations,
        organization_memberships__is_active=True,
    ).distinct()
    agent_ids = set(accessible_agents.values_list("id", flat=True))
    if agent_filter and agent_filter.isdigit() and int(agent_filter) in agent_ids:
        scope_qs = scope_qs.filter(handled_by_id=int(agent_filter))

    payment_choices = {key for key, _ in ServiceRecord.PAYMENT_METHODS}
    if payment_filter in payment_choices:
        scope_qs = scope_qs.filter(payment_method=payment_filter)

    if source_filter:
        scope_qs = scope_qs.filter(source__iexact=source_filter)

    accessible_referrals = Referral.objects.filter(
        organization__in=organizations,
        deleted_at__isnull=True,
    ).order_by("name")
    referral_ids = set(accessible_referrals.values_list("id", flat=True))
    if referral_filter and referral_filter.isdigit() and int(referral_filter) in referral_ids:
        scope_qs = scope_qs.filter(referral_id=int(referral_filter))
        
    if date_from:
        scope_qs = scope_qs.filter(created_at__date__gte=date_from)
    if date_to:
        scope_qs = scope_qs.filter(created_at__date__lte=date_to)

    try:
        if min_amount:
            scope_qs = scope_qs.filter(service_fee__gte=Decimal(min_amount))
        if max_amount:
            scope_qs = scope_qs.filter(service_fee__lte=Decimal(max_amount))
    except Exception:
        pass

    sort_map = {
        "-created_at": "-created_at",
        "created_at": "created_at",
        "-service_fee": "-service_fee",
        "service_fee": "service_fee",
        "client_name": "client_name",
        "-status": "-status",
    }
    sort_by = sort_map.get(sort_by, "-created_at")

    records = scope_qs.select_related("organization", "handled_by", "vehicle__client", "referral").order_by(sort_by)

    service_type_map = dict(ServiceRecord.SERVICE_TYPES)
    
    if service_type == "all":
        service_label = "All Services"
    else:
        service_label = service_type_map.get(service_type)
        if not service_label:
            from .models import CustomServiceType
            custom = CustomServiceType.objects.filter(
                organization__in=organizations, key=service_type
            ).first()
            if custom:
                service_label = custom.label
            else:
                service_label = service_type.replace('_', ' ').title()

    if export_type in {"csv", "xlsx"}:
        export_rows = records
        if export_type == "csv":
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="{service_type}_records.csv"'
            writer = csv.writer(response)
            writer.writerow([
                "Date",
                "Receipt No",
                "PSB",
                "Service Type",
                "Status",
                "Client Name",
                "Phone",
                "Email",
                "Agent",
                "Payment Method",
                "Source",
                "Referral",
                "Amount",
            ])
            for record in export_rows:
                client = record.vehicle.client if record.vehicle and record.vehicle.client else None
                writer.writerow([
                    timezone.localtime(record.created_at).strftime("%Y-%m-%d %H:%M"),
                    record.receipt_number,
                    record.organization.name if record.organization else "",
                    record.service_type_label,
                    record.get_status_display(),
                    client.name if client else (record.client_name or ""),
                    client.phone_number if client else (record.phone_no or ""),
                    client.email if client else (record.email or ""),
                    record.handled_by.get_full_name() or record.handled_by.username,
                    record.get_payment_method_display(),
                    record.source or "",
                    record.referral.name if record.referral else "",
                    f"{record.service_fee or Decimal('0'):.2f}",
                ])
            return response

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Service Records"
        headers = [
            "Date",
            "Receipt No",
            "PSB",
            "Service Type",
            "Status",
            "Client Name",
            "Phone",
            "Email",
            "Agent",
            "Payment Method",
            "Source",
            "Referral",
            "Amount",
        ]
        sheet.append(headers)
        for record in export_rows:
            client = record.vehicle.client if record.vehicle and record.vehicle.client else None
            sheet.append([
                timezone.localtime(record.created_at).strftime("%Y-%m-%d %H:%M"),
                record.receipt_number,
                record.organization.name if record.organization else "",
                record.service_type_label,
                record.get_status_display(),
                client.name if client else (record.client_name or ""),
                client.phone_number if client else (record.phone_no or ""),
                client.email if client else (record.email or ""),
                record.handled_by.get_full_name() or record.handled_by.username,
                record.get_payment_method_display(),
                record.source or "",
                record.referral.name if record.referral else "",
                float(record.service_fee or Decimal("0")),
            ])

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{service_type}_records.xlsx"'
        return response

    paginator = Paginator(records, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    filtered_query = request.GET.copy()
    filtered_query.pop("page", None)
    filtered_query.pop("export", None)

    # Determine delete-receipt permission for the current user
    can_delete_receipt = is_owner or memberships.filter(
        can_delete_receipt=True
    ).exists()

    return render(
        request,
        "core/service_list.html",
        {
            "page_obj": page_obj,
            "service_label": service_label,
            "service_type": service_type,
            "search_query": search_query,
            "status_filter": status_filter,
            "date_from": date_from,
            "date_to": date_to,
            "org_filter": org_filter,
            "agent_filter": agent_filter,
            "payment_filter": payment_filter,
            "source_filter": source_filter,
            "referral_filter": referral_filter,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "sort_by": sort_by,
            "status_choices": ServiceRecord.STATUS_CHOICES,
            "payment_choices": ServiceRecord.PAYMENT_METHODS,
            "organizations_for_filter": organizations.order_by("name"),
            "agents_for_filter": accessible_agents.order_by("first_name", "last_name", "username"),
            "referrals_for_filter": accessible_referrals,
            "sources_for_filter": sorted(
                {
                    s
                    for s in ServiceRecord.objects.filter(organization__in=organizations)
                    .exclude(source__isnull=True)
                    .exclude(source__exact="")
                    .values_list("source", flat=True)
                },
                key=str.lower,
            ),
            "query_string_no_page": filtered_query.urlencode(),
            "is_owner": is_owner,
            "can_delete_receipt": can_delete_receipt,
        }
    )

@login_required
def service_search_ajax(request):
    service_type = request.GET.get('service_type', 'all')
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    organizations = _get_user_organizations(request)
    scope_qs = ServiceRecord.objects.filter(organization__in=organizations)

    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    )
    is_owner = memberships.filter(role=OrganizationMembership.Role.OWNER).exists()

    # Visibility unlocked: Agents can see all records on the transactions page
    # if not is_owner:
    #     scope_qs = scope_qs.filter(handled_by=request.user)

    if service_type != "all":
        scope_qs = scope_qs.filter(service_type=service_type)

    if search_query:
        scope_qs = scope_qs.filter(
            Q(client_name__icontains=search_query) |
            Q(receipt_number__icontains=search_query) |
            Q(vehicle__client__first_name__icontains=search_query) |
            Q(vehicle__client__last_name__icontains=search_query)
        )

    if status_filter:
        scope_qs = scope_qs.filter(status=status_filter)
        
    if date_from:
        scope_qs = scope_qs.filter(created_at__date__gte=date_from)
    if date_to:
        scope_qs = scope_qs.filter(created_at__date__lte=date_to)

    records = scope_qs.select_related("handled_by", "vehicle__client").order_by("-created_at")[:50]

    from django.template.loader import render_to_string
    html = render_to_string("core/partials/service_table_rows.html", {
        "records": records,
        "service_type": service_type,
        "user": request.user
    })
    
    return JsonResponse({"html": html, "count": records.count()})


@login_required
@require_POST
def upload_document_ajax(request, service_id):
    service_record = get_object_or_404(ServiceRecord, pk=service_id)
    # Verify access
    organizations = _get_user_organizations(request)
    if not organizations.filter(id=service_record.organization_id).exists():
        return JsonResponse({"status": "error", "message": "Access denied"}, status=403)

    if 'file' not in request.FILES or 'document_type' not in request.POST:
        return JsonResponse({"status": "error", "message": "Missing file or document_type"}, status=400)

    file_obj = request.FILES['file']
    doc_type = request.POST['document_type']

    # --- Server-side validation ---
    ALLOWED_MIME_PREFIXES = ('image/',)
    ALLOWED_MIME_EXACT = ('application/pdf',)
    ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.pdf')
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

    file_mime = file_obj.content_type or ''
    file_ext = os.path.splitext(file_obj.name)[1].lower()
    is_allowed_mime = any(file_mime.startswith(p) for p in ALLOWED_MIME_PREFIXES) or file_mime in ALLOWED_MIME_EXACT
    is_allowed_ext = file_ext in ALLOWED_EXTENSIONS
    if not (is_allowed_mime or is_allowed_ext):
        return JsonResponse({"status": "error", "message": "Only images (JPG, PNG, etc.) and PDF files are accepted."}, status=400)

    if file_obj.size > MAX_UPLOAD_BYTES:
        size_mb = round(file_obj.size / (1024 * 1024), 1)
        return JsonResponse({"status": "error", "message": f"File too large ({size_mb} MB). Maximum allowed size is 50 MB."}, status=400)

    valid_types = [t[0] for t in ServiceDocument.DOCUMENT_TYPES]
    if doc_type not in valid_types:
        return JsonResponse({"status": "error", "message": "Invalid document type"}, status=400)

    custom_name = request.POST.get('custom_name', '').strip()

    try:
        doc = ServiceDocument.objects.create(
            service_record=service_record,
            vehicle=service_record.vehicle, # Automatically link to vehicle too
            document_type=doc_type,
            custom_name=custom_name,
            file=file_obj
        )
        return JsonResponse({
            "status": "success", 
            "message": "File uploaded successfully",
            "document_id": doc.id,
            "document_type": doc.document_type
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@login_required
@require_POST
def upload_document_ajax_vehicle(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle.all_objects, pk=vehicle_id)
    # Verify access
    if not _has_active_org_access(request.user, vehicle.client.organization_id):
        return JsonResponse({"status": "error", "message": "Access denied"}, status=403)

    if 'file' not in request.FILES or 'document_type' not in request.POST:
        return JsonResponse({"status": "error", "message": "Missing file or document_type"}, status=400)

    file_obj = request.FILES['file']
    doc_type = request.POST['document_type']

    # --- Server-side validation ---
    ALLOWED_MIME_PREFIXES = ('image/',)
    ALLOWED_MIME_EXACT = ('application/pdf',)
    ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.pdf')
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

    file_mime = file_obj.content_type or ''
    file_ext = os.path.splitext(file_obj.name)[1].lower()
    is_allowed_mime = any(file_mime.startswith(p) for p in ALLOWED_MIME_PREFIXES) or file_mime in ALLOWED_MIME_EXACT
    is_allowed_ext = file_ext in ALLOWED_EXTENSIONS
    if not (is_allowed_mime or is_allowed_ext):
        return JsonResponse({"status": "error", "message": "Only images (JPG, PNG, etc.) and PDF files are accepted."}, status=400)

    if file_obj.size > MAX_UPLOAD_BYTES:
        size_mb = round(file_obj.size / (1024 * 1024), 1)
        return JsonResponse({"status": "error", "message": f"File too large ({size_mb} MB). Maximum allowed size is 50 MB."}, status=400)

    valid_types = [t[0] for t in ServiceDocument.DOCUMENT_TYPES]
    if doc_type not in valid_types:
        return JsonResponse({"status": "error", "message": "Invalid document type"}, status=400)

    custom_name = request.POST.get('custom_name', '').strip()

    try:
        doc = ServiceDocument.objects.create(
            vehicle=vehicle,
            document_type=doc_type,
            custom_name=custom_name,
            file=file_obj
        )
        return JsonResponse({
            "status": "success", 
            "message": "File uploaded successfully",
            "document_id": doc.id,
            "document_type": doc.document_type
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)



@login_required
@require_POST
def update_agent_role(request):
    membership_id = request.POST.get("membership_id")
    new_role = request.POST.get("role")
    
    if new_role not in dict(OrganizationMembership.Role.choices):
        return JsonResponse({"status": "error", "message": "Invalid role"})

    try:
        membership = OrganizationMembership.objects.get(id=membership_id)
        # Verify request.user is owner of this org
        is_owner = _has_active_owner_access(request.user, membership.organization_id)
        
        if not is_owner:
            return JsonResponse({"status": "error", "message": "Unauthorized"})
            
        # Prevent demoting the last owner
        if new_role != OrganizationMembership.Role.OWNER and membership.role == OrganizationMembership.Role.OWNER:
            owner_count = OrganizationMembership.objects.filter(
                organization=membership.organization,
                role=OrganizationMembership.Role.OWNER
            ).count()
            if owner_count <= 1:
                return JsonResponse({"status": "error", "message": "Cannot demote the last owner of the PSB."})

        membership.role = new_role
        membership.save()
        return JsonResponse({"status": "success"})
    except OrganizationMembership.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Membership not found"})

@login_required
def update_agent_permissions(request):
    if request.method == "POST":
        membership_id = request.POST.get("membership_id")
        
        membership = get_object_or_404(OrganizationMembership, id=membership_id)
        
        is_owner = _has_active_owner_access(request.user, membership.organization_id)
        
        if not is_owner:
            return JsonResponse({"status": "error", "message": "Permission denied."}, status=403)
            
        if membership.role == OrganizationMembership.Role.OWNER:
            return JsonResponse({"status": "error", "message": "Cannot modify owner permissions."}, status=400)
            
        field = request.POST.get("field")
        value = request.POST.get("value") == "true"
        
        if field == "can_view_reports":
            membership.can_view_reports = value
        elif field == "can_view_net_profit":
            membership.can_view_net_profit = value
        elif field == "can_manage_referrals":
            membership.can_manage_referrals = value
        elif field == "can_trigger_automation":
            membership.can_trigger_automation = value
        elif field == "can_view_commission":
            membership.can_view_commission = value
        elif field == "can_view_banking":
            membership.can_view_banking = value
        elif field == "can_manage_news":
            membership.can_manage_news = value
        elif field == "can_manage_knowledge_hub":
            membership.can_manage_knowledge_hub = value
            
        membership.save()
        
        return JsonResponse({"status": "success"})
    return JsonResponse({"status": "error"}, status=400)


@login_required
def get_documents(request, service_id):
    service_record = get_object_or_404(ServiceRecord, id=service_id)
    
    # Check permissions
    is_owner = OrganizationMembership.objects.filter(
        organization=service_record.organization,
        user=request.user,
        role=OrganizationMembership.Role.OWNER
    ).exists()
    
    if not is_owner and service_record.handled_by != request.user:
        return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)
        
    from django.db.models import Q
    # Show docs for this specific service, OR any doc linked to this client's vehicles
    documents = ServiceDocument.objects.filter(
        Q(service_record=service_record) | 
        Q(vehicle__client=service_record.vehicle.client) |
        Q(service_record__vehicle__client=service_record.vehicle.client)
    ).distinct()
    doc_map = dict(ServiceDocument.DOCUMENT_TYPES)
    
    docs_data = [
        {
            "id": doc.id,
            "type": doc.document_type,
            "type_label": doc.display_name,
            "url": request.build_absolute_uri(doc.file.url) if doc.file else ""
        }
        for doc in documents
    ]
    
    return JsonResponse({
        "status": "success",
        "documents": docs_data
    })


@login_required
def get_documents_vehicle(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle.all_objects, id=vehicle_id)
    if not _has_active_org_access(request.user, vehicle.client.organization_id):
        return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)
        
    from django.db.models import Q
    # Get all docs belonging to the owner of this vehicle
    documents = ServiceDocument.objects.filter(
        Q(vehicle__client=vehicle.client) | 
        Q(service_record__vehicle__client=vehicle.client)
    ).distinct()
    
    docs_data = [
        {
            "id": doc.id,
            "type": doc.document_type,
            "type_label": doc.display_name,
            "url": request.build_absolute_uri(doc.file.url) if doc.file else "",
            "uploaded_at": doc.uploaded_at.strftime("%b %d, %Y %H:%M") if doc.uploaded_at else ""
        }
        for doc in documents
    ]
    
    return JsonResponse({
        "status": "success",
        "documents": docs_data
    })



@login_required
@require_POST
def add_custom_service(request):
    organization_id = request.POST.get("organization_id")
    label = request.POST.get("label", "").strip()
    
    if not label or not organization_id:
        return JsonResponse({"status": "error", "message": "Missing fields"}, status=400)
        
    organization = get_object_or_404(Organization, id=organization_id)
    
    is_owner = _has_active_owner_access(request.user, organization.id)
    
    if not is_owner:
        return JsonResponse({"status": "error", "message": "Permission denied."}, status=403)
        
    import re
    key = re.sub(r'[^a-zA-Z0-9]', '_', label.lower())
    
    try:
        CustomServiceType.objects.create(
            organization=organization,
            key=key,
            label=label
        )
        return JsonResponse({"status": "success"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": "Service type already exists or error occurred."}, status=400)


@login_required
def all_service_types(request):
    organizations = _get_user_organizations(request)
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        organization__in=organizations
    ).select_related("organization")
    
    scope_qs = ServiceRecord.objects.filter(organization__in=organizations)
    
    owner_org_ids = list(
        memberships.filter(role=OrganizationMembership.Role.OWNER).values_list("organization_id", flat=True)
    )
    is_owner = bool(owner_org_ids)
    
    # Visibility unlocked: Agents can see org-wide reports
    # if not is_owner:
    #     scope_qs = scope_qs.filter(handled_by=request.user)

    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    custom_types = CustomServiceType.objects.filter(organization__in=organizations)
    all_service_keys = list(ServiceRecord.SERVICE_TYPES)
    for ct in custom_types:
        all_service_keys.append((ct.key, ct.label))

    service_cards = []
    for service_key, service_label in all_service_keys:
        service_subset = scope_qs.filter(service_type=service_key)
        service_cards.append(
            {
                "key": service_key,
                "label": service_label,
                "daily_count": service_subset.filter(created_at__date=today).count(),
                "monthly_count": service_subset.filter(created_at__date__gte=month_start).count(),
                "yearly_count": service_subset.filter(created_at__date__gte=year_start).count(),
                "total_count": service_subset.count(),
                "is_custom": service_key not in [t[0] for t in ServiceRecord.SERVICE_TYPES],
            }
        )

    return render(
        request,
        "core/all_service_types.html",
        {
            "service_cards": service_cards,
            "is_owner": is_owner,
            "organizations": organizations,
        }
    )

@login_required
def all_agents_directory(request):
    organizations = _get_user_organizations(request).filter(memberships__role=OrganizationMembership.Role.OWNER)
    owner_org_ids = list(organizations.values_list("id", flat=True))
    if not owner_org_ids:
        return HttpResponseForbidden("Owner access required.")

    agents = OrganizationMembership.objects.filter(
        organization_id__in=owner_org_ids
    ).exclude(user=request.user).select_related("user", "organization")
    
    agent_data = []
    for agent in agents:
        records = ServiceRecord.objects.filter(
            organization=agent.organization, handled_by=agent.user
        )
        totals = records.aggregate(
            total_records=Count("id"),
            total_revenue=Sum("service_fee")
        )
        agent_data.append({
            "membership": agent,
            "total_records": totals["total_records"] or 0,
            "total_revenue": totals["total_revenue"] or Decimal("0")
        })

    return render(request, "core/all_agents.html", {"agent_data": agent_data})


@login_required
def agent_audit_view(request, membership_id):
    membership = get_object_or_404(OrganizationMembership, id=membership_id)
    organizations = _get_user_organizations(request)
    
    memberships = _get_user_organizations(request) # This returns a queryset of organizations, but the template usually expects memberships.
    # Actually, let's follow the dashboard pattern:
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    ).select_related("organization")

    is_owner = memberships.filter(
        organization=membership.organization,
        role=OrganizationMembership.Role.OWNER
    ).exists()
    
    if not is_owner:
        return HttpResponseForbidden("Owner access required.")

    today = timezone.localdate()
    month_start = today.replace(day=1)
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = timezone.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = timezone.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    else:
        start_date = today.replace(day=1)
        end_date = today

    records_qs = ServiceRecord.objects.filter(
        organization=membership.organization,
        handled_by=membership.user,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )

    total_records = records_qs.count()
    failed_records = records_qs.filter(status="failed").count()
    error_rate = round((failed_records / total_records * 100), 2) if total_records > 0 else 0
    
    total_profit = round(records_qs.aggregate(prof=Sum("processing_fee"))["prof"] or Decimal("0"), 2)
    
    badges = []
    if error_rate > 10:
        badges.append({"label": "Needs Improvement", "type": "danger", "icon": "⚠️"})
    elif total_records > 50 and error_rate < 2:
        badges.append({"label": "Top Performer", "type": "success", "icon": "🏆"})
        
    if total_profit > 1000:
        badges.append({"label": "High Earner", "type": "warning", "icon": "💎"})

    instructions = None
    if error_rate > 10:
        instructions = (
            "High Error Rate Detected: This agent's failed/voided rate is negatively "
            "impacting processing efficiency. Please review their recent failed transactions "
            "and ensure they are properly verifying client documents before submission."
        )
    elif total_records == 0:
        instructions = "No Activity: This agent has not processed any records in this period."

    daily_volume = (
        records_qs.extra(select={'day': 'date(created_at)'})
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    chart_dates = []
    if daily_volume:
        for v in daily_volume:
            d_val = v['day']
            if isinstance(d_val, str):
                d_val = timezone.datetime.strptime(d_val[:10], "%Y-%m-%d").date()
            chart_dates.append(d_val.strftime("%b %d"))
    chart_counts = [v['count'] for v in daily_volume] if daily_volume else []

    type_distribution = (
        records_qs.values('service_type')
        .annotate(count=Count('id'))
    )
    
    service_map = dict(ServiceRecord.SERVICE_TYPES)
    for ct in CustomServiceType.objects.filter(organization=membership.organization):
        service_map[ct.key] = ct.label
        
    pie_labels = [service_map.get(d['service_type'], d['service_type']) for d in type_distribution] if type_distribution else []
    pie_counts = [d['count'] for d in type_distribution] if type_distribution else []

    from django.core.paginator import Paginator
    paginator = Paginator(records_qs.order_by("-created_at"), 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    location_stats = []
    if is_owner and not request.session.get('active_org_id') and organizations.count() > 1:
        for org in organizations:
            org_records = ServiceRecord.objects.filter(organization=org)
            location_stats.append({
                'id': org.id,
                'name': org.name,
                'city': org.city,
                'daily_rev': org_records.filter(created_at__date=today).aggregate(Sum('service_fee'))['service_fee__sum'] or 0,
                'monthly_rev': org_records.filter(created_at__date__gte=month_start).aggregate(Sum('service_fee'))['service_fee__sum'] or 0,
                'total_records': org_records.count(),
            })
        # Sort by monthly revenue descending
        location_stats = sorted(location_stats, key=lambda x: x['monthly_rev'], reverse=True)

    context = {
        "is_owner": is_owner,
        "location_stats": location_stats,
        "memberships": memberships,
        "agent_membership": membership,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "total_records": total_records,
        "error_rate": round(error_rate, 1),
        "total_profit": total_profit,
        "badges": badges,
        "instructions": instructions,
        "chart_dates": json.dumps(chart_dates),
        "chart_counts": json.dumps(chart_counts),
        "pie_labels": json.dumps(pie_labels),
        "pie_counts": json.dumps(pie_counts),
        "page_obj": page_obj,
    }
    return render(request, "core/agent_audit.html", context)


@login_required
def audit_log_list(request):
    organizations = _get_user_organizations(request)
    scope_qs = ServiceAuditLog.objects.filter(organization__in=organizations).select_related(
        "actor", "organization", "service_record"
    )

    memberships = OrganizationMembership.objects.filter(user=request.user, organization__in=organizations)
    owner_org_ids = list(
        memberships.filter(role=OrganizationMembership.Role.OWNER).values_list(
            "organization_id", flat=True
        )
    )
    is_owner = bool(owner_org_ids)

    if not is_owner:
        return HttpResponseForbidden("Owner access required to view global audit logs.")

    search_query = request.GET.get('q', '').strip()
    action_filter = request.GET.get('action', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if search_query:
        scope_qs = scope_qs.filter(
            Q(actor__username__icontains=search_query) |
            Q(service_record__receipt_number__icontains=search_query) |
            Q(details__icontains=search_query)
        )
        
    if action_filter:
        scope_qs = scope_qs.filter(action=action_filter)

    if date_from:
        try:
            df = timezone.datetime.strptime(date_from, "%Y-%m-%d").date()
            scope_qs = scope_qs.filter(created_at__date__gte=df)
        except ValueError:
            pass

    if date_to:
        try:
            dt = timezone.datetime.strptime(date_to, "%Y-%m-%d").date()
            scope_qs = scope_qs.filter(created_at__date__lte=dt)
        except ValueError:
            pass

    logs = scope_qs.order_by("-created_at")
    paginator = Paginator(logs, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "core/all_audit_logs.html",
        {
            "page_obj": page_obj,
        }
    )

@login_required
@login_required
def all_referrals(request):
    organizations = _get_user_organizations(request)
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        organization__in=organizations
    ).select_related("organization")
    
    if not memberships.exists():
        return redirect("home")

    owner_org_ids = list(
        memberships.filter(role=OrganizationMembership.Role.OWNER).values_list(
            "organization_id", flat=True
        )
    )
    is_owner = bool(owner_org_ids)
    user_can_manage_referrals = any(m.can_manage_referrals for m in memberships)

    if not is_owner and not user_can_manage_referrals:
        return HttpResponseForbidden("You do not have permission to manage referral entities.")

    organizations = [m.organization for m in memberships]
    
    if request.method == "POST":
        category = request.POST.get("category", "referral")
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        website = request.POST.get("website")
        address = request.POST.get("address")
        is_partner = request.POST.get("is_partner") == "on"
        
        if name:
            Referral.objects.create(
                organization=organizations[0],
                category=category,
                name=name,
                email=email,
                phone_no=phone,
                website=website,
                address=address,
                is_partner=is_partner
            )
            messages.success(request, f"Referral entity '{name}' registered successfully.")
            return redirect("all-referrals")

    referrals = Referral.objects.filter(organization__in=organizations).annotate(
        record_count=Count('service_records')
    ).order_by('name')

    # Calculate outstanding balance per referral
    for ref in referrals:
        service_outstanding = ServiceRecord.objects.filter(
            Q(referral=ref) | Q(vehicle__client__referral=ref),
            is_referral_paid=False
        ).distinct().aggregate(total=Sum('referral_balance'))['total'] or Decimal('0')
        ref.outstanding = service_outstanding + ref.initial_balance

    return render(
        request,
        "core/all_referrals.html",
        {
            "referrals": referrals,
            "is_owner": is_owner,
        }
    )

@login_required
@require_POST
def toggle_referral_partner(request):
    referral_id = request.POST.get("referral_id")
    is_partner = request.POST.get("is_partner") == "true"
    
    memberships = request.user.organization_memberships.select_related("organization").filter(
        is_active=True,
        organization__is_active=True,
    )
    is_owner = memberships.filter(role=OrganizationMembership.Role.OWNER).exists()
    user_can_manage_referrals = any(m.can_manage_referrals for m in memberships)

    if not is_owner and not user_can_manage_referrals:
        return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)

    organizations = [m.organization for m in memberships]
    referral = get_object_or_404(Referral, id=referral_id, organization__in=organizations)
    
    referral.is_partner = is_partner
    referral.save()
    
    return JsonResponse({"status": "success", "is_partner": referral.is_partner})

@login_required
def referral_profile(request, referral_id):
    memberships = request.user.organization_memberships.select_related("organization").filter(
        is_active=True,
        organization__is_active=True,
    )
    if not memberships.exists():
        return redirect("home")

    is_owner = memberships.filter(role=OrganizationMembership.Role.OWNER).exists()
    user_can_manage_referrals = any(m.can_manage_referrals for m in memberships)

    if not is_owner and not user_can_manage_referrals:
        return HttpResponseForbidden("You do not have permission to view referral profiles.")

    organizations = [m.organization for m in memberships]
    referral = get_object_or_404(Referral, id=referral_id, organization__in=organizations)

    if request.method == "POST":
        if "mark_paid" in request.POST:
            record_id = request.POST.get("record_id")
            payment_amount_str = request.POST.get("payment_amount", "0")
            record = get_object_or_404(ServiceRecord, id=record_id, referral=referral)
            
            try:
                payment_amount = Decimal(payment_amount_str)
            except:
                payment_amount = Decimal("0")
                
            record.paid_amount = (record.paid_amount or Decimal("0")) + payment_amount
            record.save()
            
            # Create payment log
            ReferralPayment.objects.create(
                referral=referral,
                amount=payment_amount,
                notes=f"Payment for specific invoice: {record.client_name}"
            )
            
            messages.success(request, f"Payment of ${payment_amount:.2f} applied to invoice for {record.client_name}.")
            return redirect("referral-profile", referral_id=referral.id)
            
        elif "log_bulk_payment" in request.POST:
            payment_amount_str = request.POST.get("bulk_payment_amount", "0")
            notes = request.POST.get("payment_notes", "")
            try:
                payment_amount = Decimal(payment_amount_str)
            except:
                payment_amount = Decimal("0")
                
            if payment_amount > 0:
                # Create payment log
                ReferralPayment.objects.create(
                    referral=referral,
                    amount=payment_amount,
                    notes=notes
                )
                
                # Apply to oldest unpaid records
                remaining = payment_amount
                unpaid_records = ServiceRecord.objects.filter(referral=referral, referral_balance__gt=0).order_by("created_at")
                
                for rec in unpaid_records:
                    if remaining <= 0:
                        break
                    if rec.referral_balance <= remaining:
                        payment_applied = rec.referral_balance
                        remaining -= payment_applied
                    else:
                        payment_applied = remaining
                        remaining = Decimal("0")
                    
                    rec.paid_amount = (rec.paid_amount or Decimal("0")) + payment_applied
                    rec.save()
                
                # If still remaining, apply to initial_balance
                if remaining > 0:
                    if referral.initial_balance <= remaining:
                        remaining -= referral.initial_balance
                        referral.initial_balance = Decimal("0")
                    else:
                        referral.initial_balance -= remaining
                        remaining = Decimal("0")
                    referral.save()
                
                messages.success(request, f"Bulk payment of ${payment_amount:.2f} applied to outstanding invoices.")
            return redirect("referral-profile", referral_id=referral.id)

    # Show all records where referral is directly set OR client is linked to this referral
    records = ServiceRecord.objects.filter(
        Q(referral=referral) | Q(vehicle__client__referral=referral)
    ).select_related("vehicle__client").distinct().order_by("-created_at")

    outstanding_balance = records.filter(is_referral_paid=False).aggregate(
        total=Sum('referral_balance')
    )['total'] or Decimal('0')
    outstanding_balance += referral.initial_balance
    
    total_revenue = records.aggregate(total=Sum('service_fee'))['total'] or Decimal('0')
    
    # Analytics
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    monthly_volume = records.filter(created_at__gte=thirty_days_ago).count()
    
    # Service distribution
    service_distribution = list(records.values('service_type').annotate(count=Count('id')).order_by('-count')[:5])
    service_map = dict(ServiceRecord.SERVICE_TYPES)
    for item in service_distribution:
        item['label'] = service_map.get(item['service_type'], item['service_type'])
        
    chart_labels = [item['label'] for item in service_distribution]
    chart_data = [item['count'] for item in service_distribution]
    
    # Payment Ledger
    payments = ReferralPayment.objects.filter(referral=referral).order_by("-payment_date", "-created_at")

    return render(
        request,
        "core/referral_profile.html",
        {
            "referral": referral,
            "records": records,
            "outstanding_balance": outstanding_balance,
            "total_revenue": total_revenue,
            "monthly_volume": monthly_volume,
            "chart_labels": json.dumps(chart_labels),
            "chart_data": json.dumps(chart_data),
            "payments": payments,
        }
    )






@login_required
def run_automation_scan(request):
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    )
    can_trigger = any(m.can_trigger_automation for m in memberships)
    
    if not can_trigger:
        messages.error(request, 'You do not have permission to trigger the automation scan.')
        return redirect('dashboard')
        
    from .tasks import check_registration_reminders
    check_registration_reminders()
    messages.success(request, 'Automation scan completed. Check the Recent Automations log for details.')
    return redirect('dashboard')

@login_required
def all_automation_logs(request):
    logs = AutomationLog.objects.filter(
        organization__in=_get_user_organizations(request)
    ).select_related('client', 'vehicle', 'organization').order_by('-timestamp').distinct()
    
    paginator = Paginator(logs, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'core/all_automation_logs.html', {'page_obj': page_obj})

@login_required
def upcoming_expirations_view(request):
    organizations = _get_user_organizations(request)
    today = timezone.now().date()
    forty_five_days_later = today + timezone.timedelta(days=45)
    
    upcoming_expirations = Vehicle.objects.filter(
        client__organization__in=organizations,
        registration_expiration_date__isnull=False,
        registration_expiration_date__lte=forty_five_days_later
    ).select_related('client').order_by('registration_expiration_date')
    
    paginator = Paginator(upcoming_expirations, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'core/upcoming_expirations.html', {
        'page_obj': page_obj,
        'today': today,
    })
@login_required
@require_POST
def bulk_send_reminders(request):
    from .tasks import process_vehicle_reminder
    
    try:
        data = json.loads(request.body)
        vehicle_ids = data.get('vehicle_ids', [])
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid request data."}, status=400)

    if not vehicle_ids:
        return JsonResponse({"status": "error", "message": "No vehicles selected."}, status=400)

    count = 0
    today = timezone.now().date()
    
    for v_id in vehicle_ids:
        try:
            vehicle = Vehicle.objects.get(id=v_id)
            # Permission check per vehicle
            if _has_active_org_access(request.user, vehicle.client.organization_id):
                days_left = (vehicle.registration_expiration_date - today).days
                
                if days_left <= 0: log_type = "expired_warning"
                elif days_left <= 15: log_type = "reminder_15"
                elif days_left <= 30: log_type = "reminder_30"
                else: log_type = "reminder_45"
                
                process_vehicle_reminder(vehicle.id, days_left, log_type, force_sync=True)
                count += 1
        except Exception:
            continue
            
    return JsonResponse({"status": "success", "count": count})


@login_required
def send_manual_reminder(request, vehicle_id):
    from .tasks import process_vehicle_reminder
    vehicle = get_object_or_404(Vehicle.all_objects, id=vehicle_id)
    
    # Check permission
    if not _has_active_org_access(request.user, vehicle.client.organization_id):
        messages.error(request, "You do not have permission to send reminders for this client.")
        return redirect('dashboard')

    today = timezone.now().date()
    days_left = (vehicle.registration_expiration_date - today).days
    
    # Determine log type based on proximity
    if days_left <= 0:
        log_type = "expired_warning"
    elif days_left <= 15:
        log_type = "reminder_15"
    elif days_left <= 30:
        log_type = "reminder_30"
    else:
        log_type = "reminder_45"
        
    try:
        process_vehicle_reminder(vehicle.id, days_left, log_type, force_sync=True)
        messages.success(request, f"Registration reminder successfully sent to {vehicle.client.name}.")
    except Exception as e:
        messages.error(request, f"Failed to send email: {str(e)}")
    
    # Redirect back to where they came from
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('upcoming-expirations')

def _check_ocr_auth(request):
    if request.user.is_authenticated:
        return True
    portal_token = request.POST.get("portal_token")
    if portal_token:
        from .models import Organization
        return Organization.objects.filter(portal_token=portal_token).exists()
    return False

def _perform_ocr(file_obj):
    """
    Robust OCR wrapper for OCR.space with Engine 2 -> Engine 1 fallback
    and auto-orientation detection.
    """
    import os, requests
    api_key = os.environ.get('OCR_API_KEY', 'helloworld')
    
    # Try Engine 2 first (Better for table-like data)
    try:
        payload = {
            'isOverlayRequired': False,
            'apikey': api_key,
            'language': 'eng',
            'OCREngine': 2,
            'scale': True,
        }
        r = requests.post('https://api.ocr.space/parse/image',
                        files={'file': file_obj},
                        data=payload,
                        timeout=20)
        result = r.json()
        
        if result.get('OCRExitCode') == 1:
            parsed = result.get('ParsedResults')
            if parsed and parsed[0].get('ParsedText'):
                return True, parsed[0].get('ParsedText')
    except:
        pass

    # Fallback to Engine 1 with auto-orientation
    try:
        file_obj.seek(0)
        payload = {
            'isOverlayRequired': False,
            'apikey': api_key,
            'language': 'eng',
            'OCREngine': 1,
            'detectOrientation': True,
            'scale': True,
        }
        r = requests.post('https://api.ocr.space/parse/image',
                        files={'file': file_obj},
                        data=payload,
                        timeout=20)
        result = r.json()
        
        if result.get('OCRExitCode') == 1:
            parsed = result.get('ParsedResults')
            if parsed and parsed[0].get('ParsedText'):
                return True, parsed[0].get('ParsedText')
        
        err = result.get('ErrorMessage') or "OCR Failed"
        if isinstance(err, list): err = ", ".join(err)
        return False, err
    except Exception as e:
        return False, str(e)

@require_POST
def ocr_dl_ajax(request):
    if not _check_ocr_auth(request):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
    import re
    data = {}
    barcode_str = request.POST.get('barcode_data', '')
    
    if barcode_str:
        # AAMVA PDF417 Parser (Simplistic implementation)
        mapping = {
            "DAQ": "driver_license",
            "DCS": "last_name",
            "DAC": "first_name",
            "DAD": "middle_name",
            "DBB": "dob",
            "DBC": "gender",
            "DAG": "street_address",
            "DAI": "city",
            "DAJ": "state",
            "DAK": "zip_code",
        }
        
        def normalize_gender(val):
            v = (val or "").strip().upper()
            if v.startswith("1") or v.startswith("M"):
                return "male"
            if v.startswith("2") or v.startswith("F"):
                return "female"
            if v.startswith("3") or v.startswith("X") or v.startswith("O"):
                return "other"
            return ""

        # Look for the DL subfile start
        dl_start = barcode_str.find("DL")
        if dl_start != -1:
            content = barcode_str[dl_start:]
            for key, field in mapping.items():
                # Find key and then look for the next key or end of line
                # Standard fields are usually 3 chars followed by value
                match = re.search(f"{key}(.*?)(?=[A-Z]{{3}}|\n|\r|$)", content)
                if match:
                    val = match.group(1).strip()
                    if field == "dob":
                        # Convert MMDDYYYY to YYYY-MM-DD
                        if len(val) == 8:
                            data[field] = f"{val[4:8]}-{val[0:2]}-{val[2:4]}"
                        else:
                            data[field] = val
                    elif field == "gender":
                        g = normalize_gender(val)
                        if g:
                            data[field] = g
                    else:
                        data[field] = val
                        
    elif 'file' in request.FILES:
        # Real OCR using OCR.space Free API
        success, text = _perform_ocr(request.FILES['file'])
        if not success:
            return JsonResponse({"status": "error", "message": f"OCR failed: {text}"})
        
        # Advanced parser for New York State and standard DLs
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        
        # 1. Driver License
        dl_match = re.search(r'\b(?:ID\s*|\w\s+)?(\d{3}\s?\d{3}\s?\d{3})\b', text)
        if dl_match:
            data['driver_license'] = dl_match.group(1).replace(' ', '')
        
        # 2. DOB (Notice raw text has 'ров 01/03/2002' instead of DOB)
        dob_match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
        if dob_match:
            try:
                parts = dob_match.group(1).split('/')
                # Check if it's MM/DD/YYYY
                if int(parts[0]) <= 12:
                    data['dob'] = f"{parts[2]}-{parts[0]}-{parts[1]}"
            except: pass
                    
        # 3. Use City, State, Zip as the Anchor for Address and Names
        csz_index = -1
        for i, line in enumerate(lines):
            csz_match = re.search(r'^(.+?)[,\s]+([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)', line)
            if csz_match:
                csz_index = i
                data['city'] = csz_match.group(1).strip()
                data['state'] = csz_match.group(2).strip().upper()
                data['zip_code'] = csz_match.group(3).strip()
                
                if data['state'] == 'NY':
                    city_upper = data['city'].upper()
                    zip_start = data['zip_code'][:3]
                    if city_upper == 'YONKERS' or zip_start in ('105', '106', '107', '108'):
                        data['county'] = 'Westchester'
                    elif zip_start in ('100', '101', '102'):
                        data['county'] = 'New York'
                    elif zip_start == '103':
                        data['county'] = 'Richmond'
                    elif zip_start == '104':
                        data['county'] = 'Bronx'
                    elif zip_start in ('110', '114', '111', '113', '116'):
                        data['county'] = 'Queens'
                    elif zip_start == '112':
                        data['county'] = 'Kings'
                break

        if csz_index != -1:
            # Index - 1: Street Address
            if csz_index - 1 >= 0:
                addr_line1 = lines[csz_index - 1]
                bno_match = re.search(r'^(\d+)\s+(.+)$', addr_line1)
                if bno_match:
                    data['building_no'] = bno_match.group(1)
                    rest_of_street = bno_match.group(2)
                    apt_match = re.search(r'(?i)\s+(APT|#|UNIT|STE|SUITE|APARTMENT)\s+(.+)$', rest_of_street)
                    if apt_match:
                        data['street_address'] = rest_of_street[:apt_match.start()].strip()
                        data['apartment'] = f"{apt_match.group(1).upper()} {apt_match.group(2).strip()}"
                    else:
                        data['street_address'] = rest_of_street
                else:
                    data['street_address'] = addr_line1

            # Index - 2: First Name, Middle Name
            if csz_index - 2 >= 0:
                name_line = lines[csz_index - 2]
                names = [n.strip() for n in name_line.replace('FIRST', '').replace('NAME', '').split(',')]
                if len(names) == 1 and ' ' in names[0]:
                    names = names[0].split(' ', 1)
                if len(names) > 0 and names[0]:
                    data['first_name'] = names[0].strip()
                if len(names) > 1:
                    data['middle_name'] = names[1].strip()

            # Index - 3: Last Name
            if csz_index - 3 >= 0:
                data['last_name'] = lines[csz_index - 3].replace('LAST', '').replace('NAME', '').strip()

        # 3. Fallbacks if strict parsing missed
        if 'driver_license' not in data:
            dl_match = re.search(r'\b(?:ID\s*)?(\d{3}\s?\d{3}\s?\d{3})\b', text)
            if dl_match:
                data['driver_license'] = dl_match.group(1).replace(' ', '')
                
        if 'dob' not in data:
            dob_match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
            if dob_match:
                parts = dob_match.group(1).split('/')
                data['dob'] = f"{parts[2]}-{parts[0]}-{parts[1]}"
        
        if not data:
            data = {"status_msg": "Text extracted but could not be parsed automatically. Please fill manually.", "raw_text": text[:100]}

    
    return JsonResponse({"status": "success", "data": data})


@require_POST
def ocr_vehicle_title_ajax(request):
    """
    Title/barcode scan parser for vehicle autofill.
    Works with handheld scanner text payload OR image file upload via OCR.space.
    """
    if not _check_ocr_auth(request):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
        
    import re
    data = {}

    raw = (request.POST.get("scan_data") or "").strip().upper()

    if 'file' in request.FILES:
        success, text = _perform_ocr(request.FILES['file'])
        if not success:
            return JsonResponse({"status": "error", "message": f"OCR failed: {text}"})
        raw = text.upper()

    if not raw:
        return JsonResponse({"status": "error", "message": "Missing scan data or image."}, status=400)

    # 1. VIN (17 chars) - Handle OCR misreading 1 as L
    vin_match = re.search(r"\b([1A-HJ-NPR-Z0-9]{17}|[L][A-HJ-NPR-Z0-9]{16})\b", raw)
    if vin_match:
        vin = vin_match.group(1)
        if vin.startswith('L'): # Common OCR error for NY titles
             vin = '1' + vin[1:]
        data["vin"] = vin

    # 2. Year (4 digits)
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", raw)
    if year_match:
        data["year"] = year_match.group(1)

    # 3. Make (Common NY Abbreviations)
    makes_map = {
        "CHEVR": "CHEVROLET", "TOYOT": "TOYOTA", "HONDA": "HONDA", "FORD": "FORD", 
        "NISSA": "NISSAN", "BMW": "BMW", "MERCE": "MERCEDES-BENZ", "VOLKS": "VOLKSWAGEN",
        "DODGE": "DODGE", "GMC": "GMC", "LEXUS": "LEXUS", "MAZDA": "MAZDA", 
        "SUBAR": "SUBARU", "HYUND": "HYUNDAI", "KIA": "KIA", "JEEP": "JEEP",
        "CHRYSL": "CHRYSLER", "ACURA": "ACURA", "INFIN": "INFINITI", "AUDI": "AUDI",
        "CADIL": "CADILLAC", "BUICK": "BUICK", "RAM": "RAM", "LINCO": "LINCOLN"
    }
    for code, full in makes_map.items():
        if code in raw:
            data["make"] = full
            break

    # 4. Color (2 chars)
    color_map = {
        "GY": "GRAY", "WH": "WHITE", "BK": "BLACK", "BL": "BLUE", "RD": "RED", 
        "SL": "SILVER", "BR": "BROWN", "GR": "GREEN", "OR": "ORANGE", "YW": "YELLOW", 
        "PR": "PURPLE", "TN": "TAN", "GD": "GOLD", "MR": "MAROON"
    }
    # Look for the color code, usually near 'COLOR' or on its own line
    color_match = re.search(r"\b(GY|WH|BK|BL|RD|SL|BR|GR|OR|YW|PR|TN|GD|MR)\b", raw)
    if color_match:
        data["color"] = color_map.get(color_match.group(1))

    # 5. Cylinders
    cyl_match = re.search(r"(?:CYL|PROP)\.?\s*(\d+)", raw)
    if not cyl_match: # Fallback: search for single digit near the word CYL
        cyl_match = re.search(r"CYL[\s\S]{1,20}?\b(\d)\b", raw)
    if cyl_match:
        data["cylinders"] = cyl_match.group(1)

    # 6. Weight (Usually 4 digits, near WT)
    weight_match = re.search(r"(?:WT|LGTH)\.?\s*(\d{3,5})", raw)
    if not weight_match:
        # Fallback: look for 4 digits that are NOT the year
        all_nums = re.findall(r"\b(\d{4})\b", raw)
        for num in all_nums:
            if num != data.get("year"):
                data["weight"] = num
                break
    else:
        data["weight"] = weight_match.group(1)

    # 7. Fuel
    fuel_match = re.search(r"\b(GAS|DSL|HYB|ELE|G)\b", raw)
    if fuel_match:
        f_val = fuel_match.group(1)
        data["fuel_type"] = "GAS" if f_val in ("GAS", "G") else f_val

    # 8. Document No
    doc_match = re.search(r"(?:DOCUMENT|DOC)\.?\s*NO\.?\s*(\d{7,10}[A-Z]?)", raw)
    if doc_match:
        data["document_no"] = doc_match.group(1)

    # 9. Odometer Reading
    odo_match = re.search(r"ODOMETER\s*READING:?\s*(\d+)", raw)
    if odo_match:
        data["odometer_reading"] = odo_match.group(1)

    # 10. Owner Name & Address (Brilliant Contextual Parsing)
    # NY Titles put Name and Address under 'Name and Address of Owner(s)'
    if "NAME AND ADDRESS" in raw:
        # Split text into lines to find the block
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        for i, line in enumerate(lines):
            if "OWNER(S)" in line or "NAME AND ADDRESS" in line:
                # The next 3 lines are usually Name, Street, City/Zip
                if i + 3 < len(lines):
                    name_line = lines[i+1]
                    street_line = lines[i+2]
                    city_zip_line = lines[i+3]
                    
                    # Parse Name (LAST, FIRST, MIDDLE)
                    if ',' in name_line:
                        parts = [p.strip() for p in name_line.split(',')]
                        data["last_name"] = parts[0]
                        if len(parts) > 1: data["first_name"] = parts[1]
                        if len(parts) > 2: data["middle_name"] = parts[2]
                    
                    # Parse Street (Building No + Street Name)
                    street_parts = street_line.split(' ', 1)
                    if len(street_parts) > 1 and street_parts[0].isdigit():
                        data["building_no"] = street_parts[0]
                        data["street_address"] = street_parts[1]
                    else:
                        data["street_address"] = street_line

                    # Parse City, State, Zip
                    cz_match = re.search(r"^(.*?)\s+(NY|NJ|CT)\s+(\d{5})", city_zip_line)
                    if cz_match:
                        data["city"] = cz_match.group(1)
                        data["state"] = cz_match.group(2)
                        data["zip_code"] = cz_match.group(3)

    # 11. Model (Heuristic Improvement)
    if not data.get("model"):
        model_match = re.search(r"\b(SLV|SUV|PICK|4DSD|2DSD|SUBN|TRAC|VAN|SDN|WAG|CONV)\b", raw)
        if model_match:
            data["model"] = model_match.group(1)

    if 'file' in request.FILES and not data:
        data = {"status_msg": "Image processed but no clear vehicle data found. Please fill manually.", "raw_text": raw[:100]}

    return JsonResponse({"status": "success", "data": data})
            
@login_required
def finance_hub(request):
    """
    Brilliant Financial & BI Hub for PSB Analytics.
    """
    if not _can_access_finance_hub(request.user):
        messages.error(
            request,
            "Finance & BI access is disabled for your account. Ask an owner to enable it from Agent permissions.",
        )
        return redirect("dashboard")

    organizations = _get_user_organizations(request).filter(
        Q(memberships__role=OrganizationMembership.Role.OWNER) | Q(memberships__can_view_reports=True)
    ).distinct()
    records = ServiceRecord.objects.filter(organization__in=organizations).select_related(
        "organization",
        "handled_by",
    )

    org_filter = request.GET.get("organization", "").strip()
    status_filter = request.GET.get("status", "").strip()
    service_filter = request.GET.get("service_type", "").strip()
    agent_filter = request.GET.get("agent", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    compare_a = request.GET.get("compare_a", "").strip()
    compare_b = request.GET.get("compare_b", "").strip()
    compare_mode = request.GET.get("compare_mode", "month").strip().lower()

    if org_filter.isdigit():
        records = records.filter(organization_id=int(org_filter))
    if status_filter in dict(ServiceRecord.STATUS_CHOICES):
        records = records.filter(status=status_filter)
    if service_filter:
        records = records.filter(service_type=service_filter)
    if agent_filter.isdigit():
        records = records.filter(handled_by_id=int(agent_filter))
    if date_from:
        records = records.filter(created_at__date__gte=date_from)
    if date_to:
        records = records.filter(created_at__date__lte=date_to)
    
    # KPIs
    totals = records.aggregate(total_revenue=Sum("service_fee"), total_services=Count("id"))
    total_revenue = totals["total_revenue"] or Decimal("0")
    total_services = totals["total_services"] or 0
    
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0)
    month_revenue = records.filter(created_at__gte=month_start).aggregate(Sum("service_fee"))["service_fee__sum"] or Decimal("0")
    
    # Last 12 Months Chart Data - single grouped query
    chart_end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    chart_start = (chart_end - timedelta(days=365)).replace(day=1)
    monthly_rows = (
        records.filter(created_at__gte=chart_start)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(revenue=Sum("service_fee"))
        .order_by("month")
    )
    month_map = {row["month"].date().strftime("%Y-%m"): float(row["revenue"] or 0) for row in monthly_rows}
    chart_labels = []
    chart_data = []
    cursor = chart_start.date()
    end_cursor = chart_end.date()
    while cursor <= end_cursor:
        key = cursor.strftime("%Y-%m")
        chart_labels.append(cursor.strftime("%b %Y"))
        chart_data.append(month_map.get(key, 0))
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)

    # Service Type Breakdown
    service_counts = records.values("service_type").annotate(count=Count("id")).order_by("-count")[:6]
    service_type_map = dict(ServiceRecord.SERVICE_TYPES)
    custom_service_map = {
        ct.key: ct.label for ct in CustomServiceType.objects.filter(organization__in=organizations)
    }
    service_type_map.update(custom_service_map)
    pie_labels = [service_type_map.get(s["service_type"], s["service_type"].replace("_", " ").title()) for s in service_counts]
    pie_data = [s["count"] for s in service_counts]

    avg_order_value = total_revenue / total_services if total_services > 0 else Decimal("0")

    def _parse_month(value):
        try:
            month_start_date = timezone.datetime.strptime(value, "%Y-%m").date().replace(day=1)
            if month_start_date.month == 12:
                next_month_date = month_start_date.replace(year=month_start_date.year + 1, month=1, day=1)
            else:
                next_month_date = month_start_date.replace(month=month_start_date.month + 1, day=1)
            return month_start_date, next_month_date
        except Exception:
            return None, None

    def _add_months(d, months):
        y = d.year + (d.month - 1 + months) // 12
        m = (d.month - 1 + months) % 12 + 1
        return d.replace(year=y, month=m, day=1)

    def _quarter_label(start_date):
        q = ((start_date.month - 1) // 3) + 1
        return f"Q{q} {start_date.year}"

    compare_data = None
    if compare_a and compare_b:
        a_start, a_end = _parse_month(compare_a)
        b_start, b_end = _parse_month(compare_b)
        if a_start and b_start:
            if compare_mode == "quarter":
                # Treat compare_a/compare_b as quarter start months and compare 3-month ranges.
                a_end = _add_months(a_start, 3)
                b_end = _add_months(b_start, 3)

            a_qs = records.filter(created_at__date__gte=a_start, created_at__date__lt=a_end)
            b_qs = records.filter(created_at__date__gte=b_start, created_at__date__lt=b_end)
            a_stats = a_qs.aggregate(revenue=Sum("service_fee"), records=Count("id"), profit=Sum("processing_fee"))
            b_stats = b_qs.aggregate(revenue=Sum("service_fee"), records=Count("id"), profit=Sum("processing_fee"))

            a_revenue = a_stats["revenue"] or Decimal("0")
            b_revenue = b_stats["revenue"] or Decimal("0")
            a_records = a_stats["records"] or 0
            b_records = b_stats["records"] or 0
            a_profit = a_stats["profit"] or Decimal("0")
            b_profit = b_stats["profit"] or Decimal("0")

            def pct_delta(current, previous):
                if previous in (0, Decimal("0")):
                    return Decimal("0")
                return ((current - previous) / previous) * Decimal("100")

            compare_data = {
                "a_label": _quarter_label(a_start) if compare_mode == "quarter" else a_start.strftime("%B %Y"),
                "b_label": _quarter_label(b_start) if compare_mode == "quarter" else b_start.strftime("%B %Y"),
                "a_revenue": a_revenue,
                "b_revenue": b_revenue,
                "a_records": a_records,
                "b_records": b_records,
                "a_profit": a_profit,
                "b_profit": b_profit,
                "revenue_delta_pct": pct_delta(b_revenue, a_revenue),
                "records_delta_pct": pct_delta(Decimal(b_records), Decimal(a_records)),
                "profit_delta_pct": pct_delta(b_profit, a_profit),
            }

    agents_for_filter = User.objects.filter(
        organization_memberships__organization__in=organizations,
        organization_memberships__is_active=True,
    ).distinct().order_by("first_name", "last_name", "username")
    service_choices_all = list(ServiceRecord.SERVICE_TYPES)
    seen_keys = {key for key, _ in service_choices_all}
    for ct in CustomServiceType.objects.filter(organization__in=organizations).order_by("label"):
        if ct.key not in seen_keys:
            service_choices_all.append((ct.key, ct.label))
            seen_keys.add(ct.key)

    try:
        strategy_note = getattr(getattr(request.user, "finance_strategy_note", None), "content", "")
    except (OperationalError, ProgrammingError):
        # DB migrations not applied yet (table missing). Keep page functional.
        strategy_note = ""

    context = {
        "total_revenue": total_revenue,
        "total_services": total_services,
        "month_revenue": month_revenue,
        "avg_order_value": avg_order_value,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
        "pie_labels": json.dumps(pie_labels),
        "pie_data": json.dumps(pie_data),
        "today": now.date(),
        "organizations_for_filter": organizations.order_by("name"),
        "agents_for_filter": agents_for_filter,
        "status_choices": ServiceRecord.STATUS_CHOICES,
        "service_choices": service_choices_all,
        "org_filter": org_filter,
        "status_filter": status_filter,
        "service_filter": service_filter,
        "agent_filter": agent_filter,
        "date_from": date_from,
        "date_to": date_to,
        "compare_a": compare_a,
        "compare_b": compare_b,
        "compare_mode": compare_mode,
        "compare_data": compare_data,
        "strategy_note": strategy_note,
    }
    return render(request, "core/finance_hub.html", context)


@login_required
@require_POST
def save_finance_strategy_note(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    content = (payload.get("content") or "").strip()
    try:
        note, _ = FinanceStrategyNote.objects.get_or_create(user=request.user)
        note.content = content
        note.save(update_fields=["content", "updated_at"])
        return JsonResponse({"status": "success", "updated_at": note.updated_at.isoformat()})
    except (OperationalError, ProgrammingError):
        return JsonResponse(
            {
                "status": "error",
                "message": "Database table missing. Run migrations: python manage.py migrate",
            },
            status=500,
        )


@login_required
def yearly_report_pdf(request):
    organizations = _get_user_organizations(request).filter(memberships__role=OrganizationMembership.Role.OWNER)
    owner_org_ids = list(organizations.values_list("id", flat=True))
    if not owner_org_ids: return HttpResponseForbidden("Owner access required.")
    
    today = timezone.localdate()
    qs = ServiceRecord.objects.filter(organization_id__in=owner_org_ids, created_at__year=today.year)
    return _generate_report_v2(request, qs, "Annual Audit", f"Fiscal Year Summary | {today.year}", f"yearly-audit-{today.year}.pdf")


@login_required
def custom_range_report_pdf(request):
    start_str, end_str = request.GET.get('from'), request.GET.get('to')
    if not start_str or not end_str: return HttpResponse("Missing date parameters.", status=400)
    
    from datetime import datetime
    start, end = datetime.strptime(start_str, '%Y-%m-%d').date(), datetime.strptime(end_str, '%Y-%m-%d').date()
    organizations = _get_user_organizations(request).filter(memberships__role=OrganizationMembership.Role.OWNER)
    owner_org_ids = list(organizations.values_list("id", flat=True))
    
    qs = ServiceRecord.objects.filter(organization_id__in=owner_org_ids, created_at__date__range=(start, end))
    return _generate_report_v2(request, qs, "Custom Audit", f"Range: {start} to {end}", f"custom-audit-{start}-to-{end}.pdf")

def _generate_report_v2(request, qs, title, subtitle, filename):
    from decimal import Decimal
    totals = qs.aggregate(rev=Sum('service_fee'), prof=Sum('processing_fee'))
    status_counts = {"total": qs.count(), "comp": qs.filter(status='completed').count()}
    
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin = 40
    
    # Elite Navy Theme
    navy, gold = colors.Color(0.06, 0.09, 0.16), colors.Color(0.85, 0.65, 0.13)
    
    # Header
    pdf.setFillColor(navy)
    pdf.rect(0, height-120, width, 120, fill=1, stroke=0)
    pdf.setFillColor(gold); pdf.rect(0, height-123, width, 3, fill=1, stroke=0)
    
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 24); pdf.drawString(margin, height-60, title)
    pdf.setFont("Helvetica", 11); pdf.setFillColor(colors.Color(0.8,0.8,0.8))
    pdf.drawString(margin, height-80, subtitle)
    
    # Stats
    y = height - 180
    pdf.setFillColor(colors.Color(0.97,0.98,1.0)); pdf.roundRect(margin, y-60, width-(margin*2), 70, 10, fill=1, stroke=0)
    pdf.setFillColor(navy); pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin+20, y-10, "AGENCY PROFIT (NET)"); pdf.drawString(width/2 - 40, y-10, "GROSS REVENUE"); pdf.drawString(width-margin-100, y-10, "TOTAL VOLUME")
    
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margin+20, y-35, _currency(totals['prof'] or 0))
    pdf.drawString(width/2 - 40, y-35, _currency(totals['rev'] or 0))
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(width-margin-100, y-35, str(status_counts['total']))
    
    # Table
    y -= 120
    pdf.setFont("Helvetica-Bold", 12); pdf.setFillColor(navy); pdf.drawString(margin, y, "Service Breakdown")
    pdf.setFillColor(gold); pdf.rect(margin, y-4, 40, 2, fill=1, stroke=0)
    
    y -= 40
    pdf.setFillColor(navy); pdf.roundRect(margin, y-5, width-(margin*2), 25, 5, fill=1, stroke=0)
    pdf.setFillColor(colors.white); pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(margin+10, y+2, "SERVICE TYPE"); pdf.drawRightString(width-margin-10, y+2, "NET PROFIT")
    
    y -= 30
    rows = qs.values('service_type').annotate(t=Count('id'), a=Sum('processing_fee')).order_by('-t')
    service_map = dict(ServiceRecord.SERVICE_TYPES)
    for row in rows:
        pdf.setFillColor(navy); pdf.setFont("Helvetica", 10)
        pdf.drawString(margin+10, y, service_map.get(row['service_type'], row['service_type']).upper())
        pdf.drawRightString(width-margin-10, y, _currency(row['a']))
        pdf.setStrokeColor(colors.lightgrey); pdf.line(margin, y-5, width-margin, y-5)
        y -= 25
        if y < 50: pdf.showPage(); y = height - 50
        
    pdf.save()
    return response


@login_required
def session_heartbeat(request):
    """
    Lightweight endpoint for the frontend to check if the session is still active.
    If the SingleSessionMiddleware has logged the user out, this will return a redirect
    which the frontend will detect.
    """
    return JsonResponse({"status": "active", "user": request.user.username})

@require_POST
@login_required
def toggle_psb_automation(request):
    """
    Toggles the is_automation_enabled field for an Organization.
    Only accessible by the Organization Owner.
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid request payload."}, status=400)
    psb_id = data.get("psb_id")
    enabled = data.get("enabled")

    if not psb_id:
        return JsonResponse({"status": "error", "message": "Missing psb_id."}, status=400)
    if not _has_active_owner_access(request.user, psb_id):
        return JsonResponse({"status": "error", "message": "Permission denied."}, status=403)

    membership = get_object_or_404(
        OrganizationMembership,
        organization_id=psb_id,
        user=request.user,
        role=OrganizationMembership.Role.OWNER,
        is_active=True,
        organization__is_active=True,
    )
    
    psb = membership.organization
    psb.is_automation_enabled = enabled
    psb.save()

    return JsonResponse({
        "status": "success",
        "psb_id": psb.id,
        "is_automation_enabled": psb.is_automation_enabled
    })


@require_POST
@login_required
def toggle_agent_active(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid request payload."}, status=400)
    membership_id = data.get("membership_id")
    enabled = data.get("enabled")

    membership = get_object_or_404(OrganizationMembership, id=membership_id)

    is_owner = _has_active_owner_access(request.user, membership.organization_id)
    if not is_owner:
        return JsonResponse({"status": "error", "message": "Permission denied."}, status=403)

    if membership.role == OrganizationMembership.Role.OWNER and not bool(enabled):
        owner_count = OrganizationMembership.objects.filter(
            organization=membership.organization,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        ).count()
        if owner_count <= 1:
            return JsonResponse(
                {"status": "error", "message": "Cannot disable the last active owner."},
                status=400,
            )

    membership.is_active = bool(enabled)
    membership.save(update_fields=["is_active"])

    return JsonResponse(
        {"status": "success", "membership_id": membership.id, "is_active": membership.is_active}
    )


@login_required
def branch_analytics(request, org_id):
    from django.db.models.functions import TruncDate, ExtractHour
    from .models import CustomServiceType
    import calendar
    
    # Ensure user has access to this organization
    organizations = _get_user_organizations(request)
    if not organizations.filter(id=org_id).exists():
        return HttpResponseForbidden('You do not have access to this branch.')
    
    org = get_object_or_404(Organization, id=org_id)
    
    # Analytics Logic
    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    
    records = ServiceRecord.objects.filter(organization=org)
    
    # --- TRENDS ---
    trend = records.filter(created_at__date__gte=today - timedelta(days=30))\
                  .annotate(date=TruncDate('created_at'))\
                  .values('date')\
                  .annotate(count=Count('id'), revenue=Sum('service_fee'))\
                  .order_by('date')
    
    # --- SMART FORECAST ---
    # Calc average daily revenue from last 7 days for more recency
    last_7_days_rev = records.filter(created_at__date__gte=today - timedelta(days=7))\
                             .aggregate(total=Sum('service_fee'))['total'] or Decimal('0')
    avg_daily_recent = last_7_days_rev / 7
    
    # How many days left in the month?
    _, num_days = calendar.monthrange(today.year, today.month)
    remaining_days = num_days - today.day
    current_month_rev = records.filter(created_at__date__gte=month_start).aggregate(total=Sum('service_fee'))['total'] or Decimal('0')
    
    # Forecast = What we have + (Current Rate * Remaining Days)
    projected_month = current_month_rev + (avg_daily_recent * Decimal(str(remaining_days)))
    
    # Growth indicator: Compare last 7 days vs previous 7 days
    prev_7_days_rev = records.filter(created_at__date__gte=today - timedelta(days=14), created_at__date__lt=today - timedelta(days=7))\
                             .aggregate(total=Sum('service_fee'))['total'] or Decimal('0')
    growth_rate = 0
    if prev_7_days_rev > 0:
        growth_rate = ((last_7_days_rev - prev_7_days_rev) / prev_7_days_rev) * 100

    # --- BI INSIGHTS ---
    # 1. Capacity
    agent_count = OrganizationMembership.objects.filter(organization=org, role='member', is_active=True).count() or 1
    # Assume 1 agent can comfortably handle 15 records a day
    monthly_capacity = agent_count * 15 * 22 # 22 working days
    current_monthly_count = records.filter(created_at__date__gte=month_start).count()
    capacity_usage = (current_monthly_count / monthly_capacity) * 100 if monthly_capacity > 0 else 0
    
    # 2. Peak Hour
    peak_hour_data = records.filter(created_at__date__gte=today - timedelta(days=30))\
                            .annotate(hour=ExtractHour('created_at'))\
                            .values('hour')\
                            .annotate(count=Count('id'))\
                            .order_by('-count').first()
    peak_hour = peak_hour_data['hour'] if peak_hour_data else 10
    peak_label = f"{peak_hour % 12 or 12} {'AM' if peak_hour < 12 else 'PM'}"

    # 3. Referral Mix
    referral_records_count = records.filter(referral__isnull=False).count()
    total_recs = records.count()
    referral_percentage = (referral_records_count / total_recs * 100) if total_recs > 0 else 0

    # --- SERVICE DISTRIBUTION ---
    dist = records.values('service_type').annotate(count=Count('id')).order_by('-count')
    service_map = dict(ServiceRecord.SERVICE_TYPES)
    custom_map = {c.key: c.label for c in CustomServiceType.objects.filter(organization=org)}
    service_map.update(custom_map)
    
    dist_data = []
    for item in dist:
        dist_data.append({
            'label': service_map.get(item['service_type'], item['service_type']),
            'count': item['count']
        })

    return render(request, 'core/branch_analytics.html', {
        'organization': org,
        'trend_json': json.dumps([{'date': str(i['date']), 'revenue': float(i['revenue'])} for i in trend]),
        'dist_json': json.dumps(dist_data),
        'avg_daily': avg_daily_recent,
        'projected_month': projected_month,
        'growth_rate': growth_rate,
        'capacity_usage': round(capacity_usage, 1),
        'peak_hour': peak_label,
        'referral_percentage': round(referral_percentage, 1),
        'total_revenue': records.aggregate(Sum('service_fee'))['service_fee__sum'] or 0,
        'total_count': total_recs,
        'monthly_revenue': current_month_rev,
        'yearly_revenue': records.filter(created_at__date__gte=year_start).aggregate(Sum('service_fee'))['service_fee__sum'] or 0,
    })

@login_required
def edit_client(request, client_id):
    from .forms import ClientForm
    client = get_object_or_404(Client, id=client_id)
    orgs = _get_user_organizations(request)
    if not orgs.filter(id=client.organization_id).exists():
        return HttpResponseForbidden()
    
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client, organizations=orgs)
        if form.is_valid():
            try:
                from django.db import transaction
                with transaction.atomic():
                    client = form.save(commit=False)
                    
                    # Referral logic
                    source = form.cleaned_data.get('source')
                    if source == 'referral':
                        referral_select = form.cleaned_data.get('referral_select')
                        if referral_select and referral_select != 'new':
                            try:
                                referral = Referral.objects.get(id=referral_select, organization=client.organization)
                                client.referral = referral
                            except Referral.DoesNotExist:
                                pass
                        else:
                            referral_name = form.cleaned_data.get('referral_name')
                            if referral_name:
                                # First, check if a referral with this name already exists in this organization
                                referral = Referral.objects.filter(
                                    organization=client.organization,
                                    name__iexact=referral_name
                                ).first()
                                
                                if not referral:
                                    # Create new referral if not found
                                    referral = Referral.objects.create(
                                        organization=client.organization,
                                        name=referral_name,
                                        category=form.cleaned_data.get('referral_category', 'dealer'),
                                        address=form.cleaned_data.get('referral_address', ''),
                                        phone_no=form.cleaned_data.get('referral_phone_no', ''),
                                        email=form.cleaned_data.get('referral_email', ''),
                                        website=form.cleaned_data.get('referral_website', ''),
                                        initial_balance=form.cleaned_data.get('referral_balance') or 0,
                                    )
                                client.referral = referral
                    else:
                        client.referral = None
                    
                    client.save()
                    from .models import ServiceDocument
                    for doc in ServiceDocument.objects.filter(vehicle__client=client, document_type="mv82"):
                        try:
                            regenerate_mv82_document(doc)
                        except Exception:
                            pass
                messages.success(request, f"Client {client.name} updated successfully.")
                return redirect('client-detail', client_id=client.id)
            except Exception as e:
                messages.error(request, f"An error occurred: {e}")
    else:
        form = ClientForm(instance=client, organizations=orgs)
    
    return render(request, 'core/add_client.html', {
        'form': form, 
        'edit_mode': True, 
        'client': client,
        'title': 'Edit Client Profile'
    })

@login_required
def edit_service(request, service_id):
    from .forms import VehicleServiceForm
    service = get_object_or_404(ServiceRecord, id=service_id)
    orgs = _get_user_organizations(request)
    
    if not orgs.filter(id=service.organization_id).exists():
        return HttpResponseForbidden()
    
    if request.method == 'POST':
        form = VehicleServiceForm(request.POST, instance=service, organization=service.organization)
        if form.is_valid():
            record = form.save(commit=False)

            # Auto-link to referral if this client came from a referralship and record doesn't have one
            if not record.referral and record.vehicle and record.vehicle.client.referral:
                record.referral = record.vehicle.client.referral

            record.save()
            from .models import ServiceDocument
            for doc in ServiceDocument.objects.filter(service_record=record, document_type="mv82"):
                try:
                    regenerate_mv82_document(doc)
                except Exception:
                    pass
            messages.success(request, "Service record updated successfully.")
            if record.vehicle_id:
                return redirect('vehicle-detail', vehicle_id=record.vehicle_id)
            return redirect('dashboard')
        else:
            messages.error(request, "Error updating service record. Please check the form.")
    else:
        form = VehicleServiceForm(instance=service, organization=service.organization)

    # Compute primary base amount for split payment display in edit mode
    service_paid_amount_1 = Decimal("0.00")
    if service.payment_method_2:
        def get_rate(method):
            if method == 'american_express':
                return Decimal('0.05')
            elif method in ['visa', 'mastercard', 'discover', 'diners_club']:
                return Decimal('0.035')
            return Decimal('0.0')
        
        rate1 = get_rate(service.payment_method)
        rate2 = get_rate(service.payment_method_2)
        p2_base = service.paid_amount_2 or Decimal("0")
        p2_total = p2_base * (Decimal("1") + rate2)
        p1_total = (service.paid_amount or Decimal("0")) - p2_total
        p1_base = p1_total / (Decimal("1") + rate1)
        service_paid_amount_1 = p1_base.quantize(Decimal("0.01"))

    return render(request, 'core/start_process.html', {
        'form': form,
        'edit_mode': True,
        'service': service,
        'vehicle': service.vehicle,
        'title': 'Edit Transaction',
        'service_paid_amount_1': service_paid_amount_1,
    })


@login_required
def edit_vehicle(request, vehicle_id):
    from .forms import VehicleForm
    vehicle = get_object_or_404(Vehicle.all_objects, id=vehicle_id)
    if not OrganizationMembership.objects.filter(user=request.user, organization=vehicle.client.organization).exists():
        return HttpResponseForbidden()
    
    if request.method == 'POST':
        form = VehicleForm(request.POST, instance=vehicle, client=vehicle.client)
        if form.is_valid():
            vehicle = form.save()
            from .models import ServiceDocument
            for doc in ServiceDocument.objects.filter(vehicle=vehicle, document_type="mv82"):
                try:
                    regenerate_mv82_document(doc)
                except Exception:
                    pass
            return redirect('vehicle-detail', vehicle_id=vehicle.id)
    else:
        form = VehicleForm(instance=vehicle, client=vehicle.client)
    
        return render(request, 'core/add_vehicle.html', {
        'form': form,
        'edit_mode': True,
        'vehicle': vehicle,
        'client': vehicle.client,
        'title': 'Edit Vehicle Profile'
    })


@ensure_csrf_cookie
@csrf_exempt
def public_intake_portal(request, portal_token=None):
    """The unified intake portal. Shows the form immediately if a valid token is provided."""
    # 1. Identify the organization
    token = portal_token or request.GET.get("portal_token")
    if not token:
        # No token provided, show the "Private" landing page
        return render(request, "core/public_intake_start.html")
    
    organization = get_object_or_404(Organization, portal_token=token, is_active=True)
    
    # 2. Define services for the form
    standard_services = [
        {"key": "registration_title", "label": "New Registration & Title"},
        {"key": "title_only", "label": "Title Only (No Plates)"},
        {"key": "transfer", "label": "Transfer Plates"},
        {"key": "renewal", "label": "Registration Renewal"},
        {"key": "duplicate_title", "label": "Duplicate Title"},
        {"key": "plate_surrender", "label": "Plate Surrender"},
    ]
    custom_services = CustomServiceType.objects.filter(organization=organization)

    # 3. Handle Submission
    if request.method == "POST":
        form = ClientIntakeForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                from django.db import transaction
                with transaction.atomic():
                    intake = form.save(commit=False)
                    intake.organization = organization
                    intake.requested_services = request.POST.getlist("services")
                    intake.save()
                return redirect(f"/intake/success/?portal_token={token}")
            except Exception as e:
                messages.error(request, f"An error occurred while saving your application. Please try again.")
    else:
        form = ClientIntakeForm()
    
    # 4. Render the form immediately
    return render(request, "core/public_intake_form.html", {
        "form": form,
        "organization": organization,
        "standard_services": standard_services,
        "custom_services": custom_services,
        "portal_token": token,
    })

@login_required
def approve_intake(request, intake_id):
    from django.db import transaction
    from django.core.files.base import ContentFile
    
    with transaction.atomic():
        # Select for update locks the row
        intake = get_object_or_404(
            ClientIntake.objects.select_for_update(), 
            id=intake_id, 
            organization__in=_get_user_organizations(request)
        )
        
        if intake.status != ClientIntake.Status.PENDING:
            messages.error(request, "This intake is already being processed or has been completed.")
            return redirect("dashboard")

        # 1. Check for Duplicate Client (EIN for commercial, Name+DOB or DL for individuals)
        if intake.is_commercial and intake.business_ein:
            client = Client.objects.filter(
                organization=intake.organization,
                is_commercial=True,
                business_ein__iexact=intake.business_ein
            ).first()
        else:
            client = Client.objects.filter(
                organization=intake.organization
            ).filter(
                Q(first_name=intake.first_name, last_name=intake.last_name, dob=intake.dob) |
                Q(driver_license=intake.driver_license)
            ).first()
        
        # 2. Check for Duplicate Vehicle
        existing_vehicle = Vehicle.objects.filter(vin=intake.vin).first()
        
        if existing_vehicle and client and existing_vehicle.client == client:
            # Check if this is an exact duplicate of existing info
            # If VIN and Client match, it's likely a duplicate submission
            intake.status = ClientIntake.Status.REJECTED
            intake.processed_by = request.user
            intake.processed_at = timezone.now()
            if not intake.additional_data: intake.additional_data = {}
            intake.additional_data["rejection_reason"] = "Exact duplicate of existing vehicle in client profile."
            intake.save()
            messages.warning(request, f"Intake rejected: VIN {intake.vin} already exists for {client.name}.")
            return redirect("dashboard")

        # Set to processing immediately to hide from others
        intake.status = ClientIntake.Status.APPROVED
        intake.processed_by = request.user
        intake.processed_at = timezone.now()
        intake.save()

    # 3. Create or get Client
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
            residence_building_no=intake.residence_building_no if not intake.residence_address_same else "",
            residence_street_address=intake.residence_street_address if not intake.residence_address_same else "",
            residence_apartment=intake.residence_apartment if not intake.residence_address_same else "",
            residence_city=intake.residence_city if not intake.residence_address_same else "",
            residence_zip_code=intake.residence_zip_code if not intake.residence_address_same else "",
            residence_county=intake.residence_county if not intake.residence_address_same else "",
            is_commercial=intake.is_commercial,
            business_name=intake.business_name,
            business_ein=intake.business_ein,
            source=intake.source,
        )

    # 4. Update or Create Vehicle
    vehicle, v_created = Vehicle.objects.update_or_create(
        vin=intake.vin,
        defaults={
            "client": client,
            "year": intake.year,
            "make": intake.make,
            "model": intake.model,
            "vehicle_type": intake.vehicle_type,
            "body_type": intake.body_type,
            "fuel_type": intake.fuel_type,
            "color": intake.color,
            "weight": intake.weight,
            "cylinders": intake.cylinders,
            "odometer_reading": intake.odometer_reading,
            "odometer_status": intake.odometer_status,
            "max_gross_weight": intake.max_gross_weight,
            "num_axles": intake.num_axles,
            "owner_name": intake.owner_name,
            "owner_nys_id": intake.owner_nys_id,
            "owner_dob": intake.owner_dob,
            "co_registrant_name": intake.co_registrant_name,
            "co_registrant_nys_id": intake.co_registrant_nys_id,
            "co_registrant_dob": intake.co_registrant_dob,
            "has_lien": intake.has_lien,
            "lienholder_name": intake.lienholder_name,
            "lienholder_address": intake.lienholder_address,
            "lien_filing_code": intake.lien_filing_code,
            "is_leased": intake.is_leased,
            "lessor_name": intake.lessor_name,
            "lessor_address": intake.lessor_address,
            "insurance_company": intake.insurance_company,
            "insurance_policy_number": intake.insurance_policy_number,
            "insurance_effective_date": intake.insurance_effective_date,
            "insurance_expiration_date": intake.insurance_expiration_date,
        }
    )

    # 5. (Service record is NOT auto-created here — the agent will start the
    #    transaction manually from the client or vehicle profile.)

    messages.success(
        request,
        f"Intake approved! Client and vehicle profile created for {client.name}. "
        f"Start a transaction from the profile whenever ready."
    )
    return redirect("client-detail", client_id=client.id)


@login_required
def reject_intake(request, intake_id):
    intake = get_object_or_404(ClientIntake, id=intake_id, organization__in=_get_user_organizations(request))
    intake.status = ClientIntake.Status.REJECTED
    intake.processed_at = timezone.now()
    intake.processed_by = request.user
    intake.save()
    messages.warning(request, "Intake submission has been rejected.")
    return redirect("dashboard")


def public_intake_success(request):
    """Confirmation page after successful submission."""
    token = request.GET.get("portal_token")
    organization = None
    if token:
        organization = Organization.objects.filter(portal_token=token).first()
    return render(request, "core/public_intake_success.html", {"organization": organization})


@login_required
def client_search_ajax(request):
    """
    Lightweight JSON endpoint for the dashboard command bar live search.
    Searches by name, DL, phone (any US format), plate, business name, or EIN.
    Phone normalisation: strips all non-digit chars from both the query and the
    stored value so '7186756671', '(718) 675-6671', '718-675-6671' all match.
    """
    import re

    q     = request.GET.get("q", "").strip()
    limit = min(int(request.GET.get("limit", "8")), 20)

    if len(q) < 2:
        return JsonResponse({"results": []})

    organizations = _get_user_organizations(request)
    q_digits = re.sub(r"\D", "", q)   # e.g. "7186756671"

    # ── Pass 1: collect IDs via DB-level text filter ─────────────────────────
    db_ids = list(
        Client.objects.filter(organization__in=organizations)
        .filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(driver_license__icontains=q)
            | Q(phone_number__icontains=q)
            | Q(vehicles__plate_number__icontains=q)
            | Q(business_name__icontains=q)
            | Q(business_ein__icontains=q)
        )
        .distinct()
        .values_list("id", flat=True)[:limit]
    )

    # ── Pass 2: phone normalisation (Python) ──────────────────────────────────
    # Only runs when query looks like a phone number (7+ digits).
    # Fetches id+phone_number only (cheap), strips non-digits, compares.
    if len(q_digits) >= 7:
        phone_rows = (
            Client.objects.filter(organization__in=organizations)
            .exclude(phone_number="")
            .values_list("id", "phone_number")
        )
        seen = set(db_ids)
        for cid, phone in phone_rows:
            if cid in seen:
                continue
            stored_digits = re.sub(r"\D", "", phone or "")
            # Match if query digits appear in stored digits or vice-versa
            if stored_digits and (q_digits in stored_digits or stored_digits in q_digits):
                db_ids.append(cid)
                seen.add(cid)
                if len(db_ids) >= limit:
                    break

    # ── Pass 3: fetch full objects for matched IDs ────────────────────────────
    if not db_ids:
        return JsonResponse({"results": []})

    clients_by_id = {
        c.id: c
        for c in Client.objects.filter(id__in=db_ids).select_related("organization")
    }

    results = []
    for cid in db_ids:
        c = clients_by_id.get(cid)
        if not c:
            continue
        plate = c.vehicles.values_list("plate_number", flat=True).first() or ""
        display_name = (
            c.business_name
            if c.is_commercial and c.business_name
            else f"{c.first_name} {c.last_name}".strip()
        )
        results.append({
            "name":          display_name,
            "first_name":    c.first_name,
            "last_name":     c.last_name,
            "identifier":    c.driver_license or c.business_ein or "",
            "plate":         plate,
            "url":           f"/dashboard/clients/{c.id}/",
            "is_commercial": c.is_commercial,
            "business_name": c.business_name or "",
        })

    return JsonResponse({"results": results})


@login_required
def outstanding_balances(request):
    """Show all outstanding (unpaid) service record balances across referrals and direct clients."""
    organizations = _get_user_organizations(request)
    if not organizations.exists():
        return HttpResponseForbidden()

    filter_type = request.GET.get("filter", "all")  # all | referral | direct

    qs = ServiceRecord.objects.filter(
        organization__in=organizations,
        referral_balance__gt=0,
        is_referral_paid=False,
    ).select_related("vehicle__client", "referral", "organization").order_by("-created_at")

    if filter_type == "referral":
        qs = qs.filter(referral__isnull=False)
    elif filter_type == "direct":
        qs = qs.filter(referral__isnull=True)

    total = qs.aggregate(t=Sum("referral_balance"))["t"] or Decimal("0")

    return render(request, "core/outstanding_balances.html", {
        "records": qs,
        "total": total,
        "filter_type": filter_type,
        "title": "Outstanding Balances",
    })


@login_required
@require_POST
def mark_balance_paid(request, record_id):
    """
    AJAX endpoint — apply a full or partial payment to a ServiceRecord's
    outstanding referral balance.

    Hardening checklist:
    ✓ Input sanitisation & range validation before any DB write
    ✓ select_for_update() prevents race-condition double-payments
    ✓ Atomic transaction — referral payment log rolls back on failure
    ✓ Specific exception types caught with descriptive JSON errors
    ✓ Never raises an unhandled 500 — always returns JSON
    """
    from django.http import JsonResponse
    from django.db import transaction, IntegrityError, OperationalError

    # ── 1. Authorisation ────────────────────────────────────────────────
    organizations = _get_user_organizations(request)
    if not organizations.exists():
        return JsonResponse(
            {"success": False, "error": "You do not have access to any organisation."},
            status=403,
        )

    # ── 2. Input validation BEFORE touching the DB ───────────────────────
    payment_str = (request.POST.get("payment_amount") or "").strip()

    if payment_str:
        # Reject obviously malicious or garbage strings early
        if len(payment_str) > 20:
            return JsonResponse(
                {"success": False, "error": "Payment amount value is too long."},
                status=400,
            )
        try:
            payment = Decimal(payment_str)
        except Exception:
            return JsonResponse(
                {"success": False, "error": "Invalid payment amount. Please enter a valid number."},
                status=400,
            )
        if payment < Decimal("0.01"):
            return JsonResponse(
                {"success": False, "error": "Payment amount must be at least $0.01."},
                status=400,
            )
        if payment > Decimal("999999.99"):
            return JsonResponse(
                {"success": False, "error": "Payment amount exceeds the maximum allowed value."},
                status=400,
            )
    else:
        payment = None  # will be resolved to full balance inside the transaction

    # ── 3. Atomic DB operation with row-level lock ────────────────────────
    try:
        with transaction.atomic():
            # Lock this specific row so concurrent requests queue up instead
            # of both reading the same balance and double-paying
            try:
                record = (
                    ServiceRecord.objects
                    .select_for_update(nowait=True)
                    .select_related("referral")
                    .get(id=record_id, organization__in=organizations)
                )
            except ServiceRecord.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Record not found or you do not have access to it."},
                    status=404,
                )
            except OperationalError:
                # Another request already holds the lock
                return JsonResponse(
                    {"success": False,
                     "error": "This record is being updated by another request. Please wait a moment and try again."},
                    status=429,
                )

            # Guard: already paid
            if record.is_referral_paid or record.referral_balance <= Decimal("0"):
                return JsonResponse(
                    {"success": False,
                     "error": "This record is already marked as paid. Refresh the page to see the current state."},
                    status=409,
                )

            # Resolve full-payment shorthand now that we have the live balance
            if payment is None:
                payment = record.referral_balance

            # Guard: paying more than owed
            if payment > record.referral_balance:
                return JsonResponse(
                    {"success": False,
                     "error": f"Payment amount (${payment:.2f}) exceeds the outstanding balance "
                              f"(${record.referral_balance:.2f})."},
                    status=422,
                )

            # Apply
            record.paid_amount = (record.paid_amount or Decimal("0")) + payment
            record.save(update_fields=["paid_amount", "referral_balance", "is_referral_paid", "updated_at"])

            # Log against the referral entity if one is linked
            if record.referral_id:
                ReferralPayment.objects.create(
                    referral_id=record.referral_id,
                    amount=payment,
                    notes=f"Payment via Outstanding Balances hub — {record.client_name} ({record.receipt_number})",
                )

    except IntegrityError as e:
        # Constraint violation (e.g. unique receipt_number race — extremely rare)
        return JsonResponse(
            {"success": False, "error": "A database integrity error occurred. No changes were made."},
            status=500,
        )
    except Exception as e:
        # Last-resort catch — never let Django emit a raw 500 HTML page
        import logging
        logging.getLogger("core.views").error(
            "mark_balance_paid unexpected error: record_id=%s user=%s err=%s",
            record_id, request.user.id, e, exc_info=True,
        )
        return JsonResponse(
            {"success": False,
             "error": "An unexpected server error occurred. No changes were made. Please try again."},
            status=500,
        )

    return JsonResponse({
        "success": True,
        "remaining": float(record.referral_balance),
        "is_paid": record.is_referral_paid,
    })


# =========================================================================
# SITE NEWS FEED & INVENTORY MARKETING VIEWS
# =========================================================================

@login_required
def site_news_list(request):
    from .models import SiteNews, OrganizationMembership
    from django.db.models import Q
    
    can_manage = request.user.is_superuser or request.user.is_staff or OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True
    ).filter(
        Q(can_manage_news=True) | Q(role=OrganizationMembership.Role.OWNER)
    ).exists()

    if request.method == "POST" and can_manage:
        action = request.POST.get("action", "")
        if action == "delete":
            news_id = request.POST.get("news_id")
            SiteNews.objects.filter(id=news_id).delete()
            messages.success(request, "News item deleted.")
        else:
            title   = request.POST.get("title", "").strip()
            content = request.POST.get("content", "").strip()
            is_active = request.POST.get("is_active") == "on"
            if title and content:
                SiteNews.objects.create(title=title, content=content, is_active=is_active)
                messages.success(request, "News item published successfully.")
            else:
                messages.error(request, "Title and content are required.")
        return redirect("site-news-list")

    news_items = SiteNews.objects.all().order_by("-created_at")
    return render(request, "core/site_news_list.html", {
        "news_items":   news_items,
        "can_manage":   can_manage,
    })


@login_required
def inventory_list(request):
    from django.utils.text import slugify
    from .models import Space
    organizations = _get_user_organizations(request)
    
    # Check if user has active membership in any accessible org
    if request.user.is_superuser:
        is_active_member = True
    else:
        memberships = OrganizationMembership.objects.filter(
            user=request.user,
            is_active=True,
            organization__is_active=True,
            organization__in=organizations
        )
        is_active_member = memberships.exists()
    
    # Allow any active member (agent or owner) to manage spaces
    is_owner = is_active_member
    owner_orgs = organizations

    if request.method == "POST":
        if not is_owner:
            messages.error(request, "You do not have permission to add spaces.")
            return redirect("spaces-home")
        
        org_id = request.POST.get("organization")
        if not org_id:
            messages.error(request, "Organization is required.")
            return redirect("spaces-home")
            
        if not organizations.filter(id=org_id).exists():
            messages.error(request, "Invalid organization chosen.")
            return redirect("spaces-home")
            
        org = get_object_or_404(Organization, id=org_id)

        label = request.POST.get("label", "").strip()
        key_raw = request.POST.get("key", "").strip()
        description = request.POST.get("description", "").strip()

        key = slugify(key_raw or label).replace("-", "_")

        if not label:
            messages.error(request, "Space label is required.")
            return redirect("spaces-home")

        # Unique together check
        if Space.objects.filter(organization=org, key=key).exists():
            messages.error(request, f"A space with code '{key}' already exists in this PSB.")
            return redirect("spaces-home")

        try:
            Space.objects.create(
                organization=org,
                key=key,
                label=label,
                description=description
            )
            messages.success(request, f"Space '{label}' created successfully.")
        except Exception as e:
            messages.error(request, f"Error creating space: {e}")
        
        redirect_target = request.POST.get("redirect_to", "spaces-home")
        return redirect(redirect_target)

    return redirect("spaces-home")


def _redirect_to_insurance_detail(org):
    from .models import Space
    insurance_card = Space.objects.filter(organization=org, key="insurance").first()
    if insurance_card:
        return redirect("inventory-detail", inventory_id=insurance_card.id)
    return redirect("spaces-home")


@login_required
def inventory_detail(request, inventory_id):
    from .models import Space, Client
    organizations = _get_user_organizations(request)

    card = get_object_or_404(Space, id=inventory_id, organization__in=organizations)

    # Resolve membership and ownership
    if request.user.is_superuser:
        is_owner = True
        membership = None
    else:
        membership = OrganizationMembership.objects.filter(
            user=request.user,
            organization=card.organization,
            is_active=True,
            organization__is_active=True
        ).first()
        if not membership:
            return HttpResponseForbidden("Access denied.")
        is_owner = (membership.role == OrganizationMembership.Role.OWNER)

    user_can_view_commission = is_owner or (membership and membership.can_view_commission)
    user_can_view_banking = is_owner or (membership and membership.can_view_banking)

    # Non-owners must have the specific space in their accessible_spaces
    if not request.user.is_superuser and not is_owner:
        if not membership.accessible_spaces.filter(id=card.id).exists():
            return HttpResponseForbidden("You do not have permission to access this space.")

    if request.method == "POST":
        if not is_owner:
            messages.error(request, "You do not have permission to update spaces.")
            return redirect("inventory-detail", inventory_id=card.id)

        label = request.POST.get("label", "").strip()
        description = request.POST.get("description", "").strip()

        if not label:
            messages.error(request, "Space label is required.")
            return redirect("inventory-detail", inventory_id=card.id)

        try:
            card.label = label
            card.description = description
            card.save()
            messages.success(request, f"Space '{label}' updated successfully.")
        except Exception as e:
            messages.error(request, f"Error updating space: {e}")
        
        return redirect("inventory-detail", inventory_id=card.id)

    # Special handling for the "Insurance" Space card
    if card.key == "insurance":
        from .models import InsuranceCompany, InsurancePolicy, BankAccount, BankTransaction
        active_org = card.organization
        
        is_locked = active_org.insurance_space_locked and active_org.insurance_space_password
        unlocked_session_key = f"insurance_unlocked_{active_org.id}"
        is_unlocked = request.session.get(unlocked_session_key, False)
        insurance_locked = is_locked and not is_unlocked
        
        clients = Client.objects.filter(organization=active_org)
        insurance_companies = InsuranceCompany.objects.filter(organization=active_org)
        bank_accounts = BankAccount.objects.filter(organization=active_org)
        all_bank_transactions = BankTransaction.objects.filter(bank_account__organization=active_org).select_related("bank_account", "insurance_company")
        
        # Get query parameters for filtering
        search_query = request.GET.get("q", "").strip()
        stage_filter = request.GET.get("stage", "").strip()
        status_filter = request.GET.get("status", "").strip()
        type_filter = request.GET.get("insurance_type", "").strip()
        source_filter = request.GET.get("source", "").strip()
        business_type_filter = request.GET.get("business_type", "").strip()
        date_from = request.GET.get("date_from", "").strip()
        date_to = request.GET.get("date_to", "").strip()
        company_filter = request.GET.get("insurance_company", "").strip()
        agent_filter = request.GET.get("agent", "").strip()
        min_premium = request.GET.get("min_premium", "").strip()
        max_premium = request.GET.get("max_premium", "").strip()

        # Base query for all policies
        all_policies = InsurancePolicy.objects.filter(organization=active_org).select_related("client", "insurance_company", "added_by")

        # Filter policies for the CRM table
        policies = all_policies
        if search_query:
            from django.db.models import Q
            policies = policies.filter(
                Q(policy_number__icontains=search_query) |
                Q(client__first_name__icontains=search_query) |
                Q(client__last_name__icontains=search_query)
            )
        if stage_filter:
            policies = policies.filter(stage=stage_filter)
        if status_filter:
            policies = policies.filter(status=status_filter)
        if type_filter:
            policies = policies.filter(insurance_type=type_filter)
        if source_filter:
            policies = policies.filter(source=source_filter)
        if business_type_filter:
            policies = policies.filter(business_type=business_type_filter)
        if date_from:
            policies = policies.filter(start_date__gte=date_from)
        if date_to:
            policies = policies.filter(start_date__lte=date_to)
        if company_filter:
            policies = policies.filter(insurance_company_id=company_filter)
        if agent_filter:
            policies = policies.filter(added_by_id=agent_filter)
        if min_premium:
            try:
                policies = policies.filter(premium__gte=Decimal(min_premium))
            except Exception:
                pass
        if max_premium:
            try:
                policies = policies.filter(premium__lte=Decimal(max_premium))
            except Exception:
                pass

        # ── Banking advanced filters ──────────────────────────────────────────
        bank_search = request.GET.get("bq", "").strip()
        bank_account_filter = request.GET.get("bank_account", "").strip()
        bank_type_filter = request.GET.get("bank_type", "").strip()
        bank_category_filter = request.GET.get("bank_category", "").strip()
        bank_company_filter = request.GET.get("bank_company", "").strip()
        bank_date_from = request.GET.get("bank_date_from", "").strip()
        bank_date_to = request.GET.get("bank_date_to", "").strip()
        bank_min_amount = request.GET.get("bank_min_amount", "").strip()
        bank_max_amount = request.GET.get("bank_max_amount", "").strip()

        bank_transactions = all_bank_transactions
        if bank_search:
            from django.db.models import Q
            bank_transactions = bank_transactions.filter(
                Q(category__icontains=bank_search) |
                Q(description__icontains=bank_search) |
                Q(bank_account__account_name__icontains=bank_search)
            )
        if bank_account_filter:
            bank_transactions = bank_transactions.filter(bank_account_id=bank_account_filter)
        if bank_type_filter:
            bank_transactions = bank_transactions.filter(transaction_type=bank_type_filter)
        if bank_category_filter:
            bank_transactions = bank_transactions.filter(category__icontains=bank_category_filter)
        if bank_company_filter:
            bank_transactions = bank_transactions.filter(insurance_company_id=bank_company_filter)
        if bank_date_from:
            bank_transactions = bank_transactions.filter(date__gte=bank_date_from)
        if bank_date_to:
            bank_transactions = bank_transactions.filter(date__lte=bank_date_to)
        if bank_min_amount:
            try:
                bank_transactions = bank_transactions.filter(amount__gte=Decimal(bank_min_amount))
            except Exception:
                pass
        if bank_max_amount:
            try:
                bank_transactions = bank_transactions.filter(amount__lte=Decimal(bank_max_amount))
            except Exception:
                pass

        # Global metrics calculations (unfiltered total stats)
        active_policies = all_policies.filter(stage="bound", status="active")
        inactive_policies = all_policies.filter(stage="bound", status="inactive")
        
        total_premium = sum(p.premium for p in active_policies)
        total_commission = sum(p.commission_amount for p in active_policies)

        # ── CRM Comparison Stats ──────────────────────────────────────────────
        import json as _json
        from datetime import date as _date, datetime as _datetime
        _today = _date.today()

        # Comparison mode: monthly (default), quarterly, custom
        comp_mode = request.GET.get("comp_mode", "monthly").strip()
        comp_month_offset = 0
        try:
            comp_month_offset = int(request.GET.get("comp_month_offset", "0"))
        except Exception:
            pass
        comp_custom_from = request.GET.get("comp_from", "").strip()
        comp_custom_to = request.GET.get("comp_to", "").strip()

        def _period_bounds(mode, month_offset, custom_from="", custom_to=""):
            if mode == "custom" and custom_from and custom_to:
                try:
                    return _datetime.strptime(custom_from, "%Y-%m-%d").date(), _datetime.strptime(custom_to, "%Y-%m-%d").date()
                except Exception:
                    pass
            # Compute target month
            import calendar
            yr, mo = _today.year, _today.month
            total_months = yr * 12 + (mo - 1) + month_offset
            yr = total_months // 12
            mo = (total_months % 12) + 1
            if mode == "quarterly":
                q_start_mo = ((mo - 1) // 3) * 3 + 1
                start = _date(yr, q_start_mo, 1)
                end_mo = q_start_mo + 2
                end_yr = yr
                if end_mo > 12:
                    end_mo -= 12
                    end_yr += 1
                import calendar
                end = _date(end_yr, end_mo, calendar.monthrange(end_yr, end_mo)[1])
            else:  # monthly
                import calendar
                start = _date(yr, mo, 1)
                end = _date(yr, mo, calendar.monthrange(yr, mo)[1])
            return start, end

        def _prev_period_bounds(mode, month_offset, custom_from="", custom_to=""):
            if mode == "quarterly":
                return _period_bounds(mode, month_offset - 3)
            elif mode == "custom":
                # Shift by same duration
                try:
                    s = _datetime.strptime(custom_from, "%Y-%m-%d").date()
                    e = _datetime.strptime(custom_to, "%Y-%m-%d").date()
                    duration = (e - s).days
                    from datetime import timedelta
                    return s - _datetime.timedelta(days=duration + 1), s - _datetime.timedelta(days=1)
                except Exception:
                    return _period_bounds("monthly", month_offset - 1)
            else:
                return _period_bounds("monthly", month_offset - 1)

        comp_start, comp_end = _period_bounds(comp_mode, comp_month_offset, comp_custom_from, comp_custom_to)
        prev_start, prev_end = _prev_period_bounds(comp_mode, comp_month_offset, comp_custom_from, comp_custom_to)

        def _period_stats(qs, start, end):
            period_qs = qs.filter(created_at__date__gte=start, created_at__date__lte=end)
            quotes = period_qs.filter(stage="quote").count()
            bound = period_qs.filter(stage="bound").count()
            total = quotes + bound
            conversion = (bound / total * 100) if total > 0 else 0
            premium = sum(p.premium for p in period_qs.filter(stage="bound", status="active"))
            return {"quotes": quotes, "bound": bound, "conversion": round(conversion, 1), "premium": float(premium)}

        comp_current = _period_stats(all_policies, comp_start, comp_end)
        comp_previous = _period_stats(all_policies, prev_start, prev_end)
        comp_period_label = f"{comp_start.strftime('%b %d')} – {comp_end.strftime('%b %d, %Y')}"
        prev_period_label = f"{prev_start.strftime('%b %d')} – {prev_end.strftime('%b %d, %Y')}"
        
        def get_user_colors(username):
            # Deterministic pastel color for colorful customization
            h = sum(ord(c) for c in username) * 37 % 360
            return f"hsl({h}, 75%, 93%)", f"hsl({h}, 80%, 25%)"

        # Convert querysets to lists to safely mutate Python attributes
        policies_list = CountableList(policies)
        inactive_policies_list = list(inactive_policies)

        # Distribute refunded amounts from bank transactions to calculate adjusted unearned commissions
        adjusted_unearned_map = {}
        for company in insurance_companies:
            company_transactions = company.transactions.all()
            company_refunded = sum(t.amount for t in company_transactions)
            
            comp_inactive_policies = all_policies.filter(
                insurance_company=company,
                stage="bound",
                status="inactive"
            ).order_by('inactive_date', 'id')
            
            remaining_refund = company_refunded
            for p in comp_inactive_policies:
                raw_val = p.unearned_commission
                if remaining_refund >= raw_val:
                    adjusted_unearned_map[p.id] = Decimal("0.00")
                    remaining_refund -= raw_val
                else:
                    adjusted_unearned_map[p.id] = raw_val - remaining_refund
                    remaining_refund = Decimal("0.00")

        # Apply adjusted unearned commissions to lists
        for p in policies_list:
            if p.id in adjusted_unearned_map:
                p.unearned_commission = adjusted_unearned_map[p.id]
            if p.added_by:
                bg, text = get_user_colors(p.added_by.username)
                p.agent_bg_color = bg
                p.agent_text_color = text

        for p in inactive_policies_list:
            if p.id in adjusted_unearned_map:
                p.unearned_commission = adjusted_unearned_map[p.id]

        company_summaries = []
        for company in insurance_companies:
            comp_policies = all_policies.filter(insurance_company=company)
            comp_unearned = sum(
                adjusted_unearned_map.get(p.id, p.unearned_commission)
                for p in comp_policies
                if p.stage == "bound" and p.status == "inactive"
            )
            comp_active_count = comp_policies.filter(stage="bound", status="active").count()
            
            # Fetch bank transactions linked to this company
            company_transactions = company.transactions.all().select_related("bank_account").order_by("-date", "-created_at")
            
            company_summaries.append({
                "id": company.id,
                "name": company.name,
                "active_count": comp_active_count,
                "unearned_commission": comp_unearned,
                "transactions": company_transactions
            })
            
        total_unearned_commission = sum(
            adjusted_unearned_map.get(p.id, p.unearned_commission)
            for p in inactive_policies_list
        )

        # Paginate policies list
        crm_page_num = request.GET.get("page", 1)
        crm_paginator = Paginator(policies_list, 12)
        try:
            crm_policies_page = crm_paginator.page(crm_page_num)
        except Exception:
            crm_policies_page = crm_paginator.page(1)

        # Paginate bank transactions
        bank_page_num = request.GET.get("bank_page", 1)
        bank_paginator = Paginator(list(bank_transactions), 20)
        try:
            bank_transactions_page = bank_paginator.page(bank_page_num)
        except Exception:
            bank_transactions_page = bank_paginator.page(1)
            
        # Agent Auditing Logic
        insurance_memberships = OrganizationMembership.objects.filter(
            organization=active_org,
            can_deal_with_insurance=True,
            is_active=True,
            user__is_active=True
        ).select_related("user")
        
        agent_stats = []
        best_performer = None
        highest_premium = Decimal("0.00")
        
        for m in insurance_memberships:
            agent = m.user
            agent_policies = all_policies.filter(added_by=agent)
            
            q_count = agent_policies.filter(stage="quote").count()
            p_bound = agent_policies.filter(stage="bound").count()
            
            bound_policies = agent_policies.filter(stage="bound")
            p_sum = sum(p.premium for p in bound_policies)
            c_sum = sum(p.commission_amount for p in bound_policies)
            b_sum = sum(p.broker_fee for p in bound_policies)
            t_profit = c_sum + b_sum
            
            bg, text = get_user_colors(agent.username)
            
            stats = {
                "agent": agent,
                "user_id": agent.id,
                "fullname": agent.get_full_name() or agent.username,
                "quotes_count": q_count,
                "policies_bound": p_bound,
                "total_premium": p_sum,
                "total_commission": c_sum,
                "total_broker_fee": b_sum,
                "total_profit": t_profit,
                "bg_color": bg,
                "text_color": text,
            }
            agent_stats.append(stats)
            
            if p_sum > highest_premium:
                highest_premium = p_sum
                best_performer = stats
                
        if best_performer:
            best_performer["is_best"] = True
            
        # Sort agent stats by total premium descending
        agent_stats.sort(key=lambda s: s["total_premium"], reverse=True)

        chart_agent_names = [s["fullname"] for s in agent_stats]
        chart_agent_premiums = [float(s["total_premium"]) for s in agent_stats]
        chart_agent_profits = [float(s["total_profit"]) for s in agent_stats]
        
        agent_chart_data = {
            "names": chart_agent_names,
            "premiums": chart_agent_premiums,
            "profits": chart_agent_profits,
        }
        
        import json
        agent_chart_data_json = json.dumps(agent_chart_data)
        
        # Build automatic analysis
        analysis_points = []
        if best_performer:
            analysis_points.append(f"🏆 <strong>{best_performer['fullname']}</strong> is the top performer this period, driving a total of <strong>${best_performer['total_premium']:,.2f}</strong> in premium volume.")
        
        total_quotes = sum(s["quotes_count"] for s in agent_stats)
        total_bound = sum(s["policies_bound"] for s in agent_stats)
        
        if total_quotes > 0 or total_bound > 0:
            total_leads = total_quotes + total_bound
            conversion_rate = (total_bound / total_leads * 100) if total_leads > 0 else 0
            analysis_points.append(f"📈 Overall quote-to-bind conversion rate is <strong>{conversion_rate:.1f}%</strong> across all active insurance agents.")
        else:
            analysis_points.append("ℹ️ Quote-to-bind conversion rate cannot be calculated (no quotes/policies logged yet).")
            
        avg_premium = (sum(s["total_premium"] for s in agent_stats) / total_bound) if total_bound > 0 else Decimal("0.00")
        if avg_premium > 0:
            analysis_points.append(f"💼 Average premium per bound policy is <strong>${avg_premium:,.2f}</strong>.")
            
        total_agent_profits = sum(s["total_profit"] for s in agent_stats)
        if total_agent_profits > 0:
            analysis_points.append(f"💵 Total profits brought in by all agents (commission + broker fees) is <strong>${total_agent_profits:,.2f}</strong>.")
            
        income_categories = json.dumps(["Insurance Premium Receipt", "Commission Payment", "Interest", "Other Income"])
        expense_categories = json.dumps(["Rent", "Utilities", "Payroll", "Office Supplies", "Marketing", "Other Expense"])
        
        context = {
            "card": card,
            "is_owner": is_owner,
            "active_org": active_org,
            "insurance_locked": insurance_locked,
            "clients": clients,
            "insurance_companies": insurance_companies,
            "company_summaries": company_summaries,
            "policies": crm_policies_page,
            "crm_policies_page": crm_policies_page,
            "bank_accounts": bank_accounts,
            "bank_transactions": bank_transactions_page,
            "bank_transactions_page": bank_transactions_page,
            "total_premium": total_premium,
            "total_commission": total_commission,
            "total_unearned_commission": total_unearned_commission,
            "active_policies_count": active_policies.count(),
            "inactive_policies_count": inactive_policies.count(),
            "income_categories": income_categories,
            "expense_categories": expense_categories,
            
            # Auditing details
            "insurance_agents": insurance_memberships,
            "agent_stats": agent_stats,
            "best_performer": best_performer,
            "agent_chart_data_json": agent_chart_data_json,
            "analysis_points": analysis_points,
            "total_quotes_count": total_quotes,
            "total_policies_bound": total_bound,
            "total_agent_profits": total_agent_profits,
            
            # CRM comparison
            "comp_mode": comp_mode,
            "comp_month_offset": comp_month_offset,
            "comp_custom_from": comp_custom_from,
            "comp_custom_to": comp_custom_to,
            "comp_current": comp_current,
            "comp_previous": comp_previous,
            "comp_period_label": comp_period_label,
            "prev_period_label": prev_period_label,

            # Banking filters persistence
            "bank_search": bank_search,
            "bank_account_filter": bank_account_filter,
            "bank_type_filter": bank_type_filter,
            "bank_category_filter": bank_category_filter,
            "bank_company_filter": bank_company_filter,
            "bank_date_from": bank_date_from,
            "bank_date_to": bank_date_to,
            "bank_min_amount": bank_min_amount,
            "bank_max_amount": bank_max_amount,

            # Query filters to persist in form fields
            "search_query": search_query,
            "stage_filter": stage_filter,
            "status_filter": status_filter,
            "type_filter": type_filter,
            "source_filter": source_filter,
            "business_type_filter": business_type_filter,
            "date_from": date_from,
            "date_to": date_to,
            "company_filter": company_filter,
            "agent_filter": agent_filter,
            "min_premium": min_premium,
            "max_premium": max_premium,
            "user_can_view_commission": user_can_view_commission,
            "user_can_view_banking": user_can_view_banking,
        }
        return render(request, "core/insurance_space.html", context)

    if card.key == "knowledge_hub":
        from collections import defaultdict
        # Only top-level materials (no parent)
        top_level_qs = card.materials.filter(parent__isnull=True).order_by("roadmap_name", "step_number", "created_at")

        # Group by roadmap name, building plain dicts so template can access sub_steps freely
        roadmaps_dict = defaultdict(list)
        for mat in top_level_qs:
            sub_steps = list(mat.sub_materials.all().order_by("step_number", "created_at"))
            roadmaps_dict[mat.roadmap_name].append({
                "id": mat.id,
                "title": mat.title,
                "description": mat.description,
                "step_number": mat.step_number,
                "file": mat.file,
                "file_url": mat.file.url if mat.file else None,
                "external_url": mat.external_url,
                "sub_steps": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "description": s.description,
                        "step_number": s.step_number,
                        "file": s.file,
                        "file_url": s.file.url if s.file else None,
                        "external_url": s.external_url,
                    }
                    for s in sub_steps
                ],
            })

        roadmaps = [{"name": name, "steps": steps} for name, steps in roadmaps_dict.items()]
        all_roadmap_names = list(roadmaps_dict.keys())

        # Check can_manage_knowledge_hub for agents
        can_manage_kh = is_owner
        if not is_owner and membership:
            can_manage_kh = membership.can_manage_knowledge_hub

        return render(request, "core/knowledge_hub.html", {
            "card": card,
            "is_owner": is_owner,
            "can_manage_kh": can_manage_kh,
            "active_org": card.organization,
            "materials": top_level_qs,
            "roadmaps": roadmaps,
            "all_roadmap_names": all_roadmap_names,
        })

    # Fetch service records matching this space key for the active organization
    from .models import ServiceRecord
    services = ServiceRecord.objects.filter(
        organization=card.organization, service_type=card.key
    ).select_related("vehicle", "handled_by")
    
    total_count = services.count()
    pending_count = services.filter(status="pending").count()
    completed_count = services.filter(status="completed").count()
    total_fees = sum(s.service_fee for s in services)

    return render(request, "core/custom_space.html", {
        "card": card,
        "is_owner": is_owner,
        "active_org": card.organization,
        "services": services,
        "total_count": total_count,
        "pending_count": pending_count,
        "completed_count": completed_count,
        "total_fees": total_fees,
    })






@login_required
def spaces_home(request):
    from .models import Space
    organizations = _get_user_organizations(request)
    
    active_org_id = request.session.get('active_org_id')
    active_org = None
    if active_org_id:
        active_org = organizations.filter(id=active_org_id).first()
    elif organizations.count() == 1:
        active_org = organizations.first()
        request.session['active_org_id'] = active_org.id
    
    if not active_org:
        return render(request, "core/spaces_home.html", {
            "needs_org_selection": True,
            "organizations": organizations,
        })
        
    # Resolve membership and check permissions
    from .models import OrganizationMembership
    is_owner = False
    membership = None
    if not request.user.is_superuser:
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=active_org, is_active=True
        ).first()
        if not membership:
            return HttpResponseForbidden("Access denied.")
        is_owner = (membership.role == OrganizationMembership.Role.OWNER)
        if not is_owner and not membership.can_view_spaces:
            return HttpResponseForbidden("You do not have permission to view Spaces.")

    # Auto-ensure "Insurance" card exists for this active org
    Space.objects.get_or_create(
        organization=active_org, 
        key="insurance", 
        defaults={
            "label": "Insurance", 
            "description": "Insurance CRM and Financial space", 
        }
    )
    # Auto-ensure "Knowledge Hub" card exists for this active org
    Space.objects.get_or_create(
        organization=active_org, 
        key="knowledge_hub", 
        defaults={
            "label": "Knowledge Hub", 
            "description": "Training documents, roadmaps, and educational material", 
        }
    )
        
    if request.user.is_superuser or is_owner:
        inventory_items = Space.objects.filter(organization=active_org)
    else:
        inventory_items = Space.objects.filter(
            id__in=membership.accessible_spaces.values_list('id', flat=True),
            organization=active_org
        )
    
    context = {
        "needs_org_selection": False,
        "active_org": active_org,
        "inventory_items": inventory_items,
    }
    return render(request, "core/spaces_home.html", context)


@login_required
@require_POST
def unlock_insurance_space(request):
    from django.contrib.auth.hashers import check_password
    org_id = request.POST.get("org_id")
    password = request.POST.get("password", "")
    organizations = _get_user_organizations(request)
    org = get_object_or_404(organizations, id=org_id)
    
    if org.insurance_space_password:
        if check_password(password, org.insurance_space_password) or password == org.insurance_space_password:
            request.session[f"insurance_unlocked_{org.id}"] = True
            messages.success(request, "Insurance Space unlocked.")
        else:
            messages.error(request, "Invalid password.")
    else:
        request.session[f"insurance_unlocked_{org.id}"] = True
        
    return _redirect_to_insurance_detail(org)


@login_required
@require_POST
def lock_insurance_space(request):
    org_id = request.POST.get("org_id")
    organizations = _get_user_organizations(request)
    org = get_object_or_404(organizations, id=org_id)
    
    unlocked_key = f"insurance_unlocked_{org.id}"
    if unlocked_key in request.session:
        del request.session[unlocked_key]
    messages.info(request, "Insurance Space locked.")
    return _redirect_to_insurance_detail(org)


@login_required
@require_POST
def toggle_insurance_lock(request):
    from django.contrib.auth.hashers import make_password
    org_id = request.POST.get("org_id")
    enabled = request.POST.get("enabled") == "on" or request.POST.get("enabled") == "true"
    password = request.POST.get("password", "").strip()
    
    organizations = _get_user_organizations(request)
    org = get_object_or_404(organizations, id=org_id)
    
    org.insurance_space_locked = enabled
    if password:
        org.insurance_space_password = make_password(password)
    org.save()
    
    if enabled and password:
        request.session[f"insurance_unlocked_{org.id}"] = True
        
    messages.success(request, "Lock settings updated.")
    return _redirect_to_insurance_detail(org)


@login_required
@require_POST
def add_insurance_policy(request):
    from .models import InsurancePolicy, Client, InsuranceCompany
    org_id = request.POST.get("organization")
    organizations = _get_user_organizations(request)
    org = get_object_or_404(organizations, id=org_id)
    
    client_name = request.POST.get("client_name", "").strip()
    if not client_name:
        messages.error(request, "Client name is required.")
        return _redirect_to_insurance_detail(org)
        
    name_parts = client_name.split()
    if len(name_parts) >= 2:
        first_name = " ".join(name_parts[:-1])
        last_name = name_parts[-1]
    else:
        first_name = client_name
        last_name = "."
        
    client = Client.objects.filter(
        organization=org,
        first_name__iexact=first_name,
        last_name__iexact=last_name
    ).first()
    
    if not client:
        client = Client.objects.create(
            organization=org,
            first_name=first_name,
            last_name=last_name,
            source="insurance"
        )
    
    company_id = request.POST.get("insurance_company")
    company = get_object_or_404(InsuranceCompany, id=company_id, organization=org)
    
    policy_number = request.POST.get("policy_number", "").strip()
    premium = request.POST.get("premium", "0.00").strip()
    broker_fee = request.POST.get("broker_fee", "0.00").strip()
    commission_rate = request.POST.get("commission_rate", "0.00").strip()
    stage = request.POST.get("stage", "quote")
    status = request.POST.get("status", "active")
    insurance_type = request.POST.get("insurance_type", "")
    source = request.POST.get("source", "walk_in")
    business_type = request.POST.get("business_type", "new_business")
    bound_date = request.POST.get("bound_date") or None
    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")
    insurance_period_months = request.POST.get("insurance_period_months", "6")
    inactive_date = request.POST.get("inactive_date")

    added_by = request.user

    try:
        InsurancePolicy.objects.create(
            organization=org,
            client=client,
            policy_number=policy_number,
            insurance_company=company,
            premium=Decimal(premium or "0.00"),
            broker_fee=Decimal(broker_fee or "0.00"),
            commission_rate=Decimal(commission_rate or "0.00"),
            stage=stage,
            status=status,
            insurance_type=insurance_type,
            source=source,
            business_type=business_type,
            bound_date=bound_date,
            start_date=start_date,
            end_date=end_date,
            insurance_period_months=int(insurance_period_months or 6),
            inactive_date=inactive_date or None,
            added_by=added_by,
        )
        messages.success(request, "Insurance policy created.")
    except Exception as e:
        messages.error(request, f"Error saving policy: {e}")

    return _redirect_to_insurance_detail(org)


@login_required
def edit_insurance_policy(request, policy_id):
    from .models import InsurancePolicy, Client, InsuranceCompany
    organizations = _get_user_organizations(request)
    policy = get_object_or_404(InsurancePolicy, id=policy_id, organization__in=organizations)
    
    if request.method == "POST":
        client_name = request.POST.get("client_name", "").strip()
        if not client_name:
            messages.error(request, "Client name is required.")
            return _redirect_to_insurance_detail(policy.organization)
            
        name_parts = client_name.split()
        if len(name_parts) >= 2:
            first_name = " ".join(name_parts[:-1])
            last_name = name_parts[-1]
        else:
            first_name = client_name
            last_name = "."
            
        client = Client.objects.filter(
            organization=policy.organization,
            first_name__iexact=first_name,
            last_name__iexact=last_name
        ).first()
        
        if not client:
            client = Client.objects.create(
                organization=policy.organization,
                first_name=first_name,
                last_name=last_name,
                source="insurance"
            )
        
        company_id = request.POST.get("insurance_company")
        company = get_object_or_404(InsuranceCompany, id=company_id, organization=policy.organization)
        
        policy.client = client
        policy.insurance_company = company
        policy.policy_number = request.POST.get("policy_number", "").strip()
        policy.premium = Decimal(request.POST.get("premium", "0.00").strip() or "0.00")
        policy.broker_fee = Decimal(request.POST.get("broker_fee", "0.00").strip() or "0.00")
        policy.commission_rate = Decimal(request.POST.get("commission_rate", "0.00").strip() or "0.00")
        policy.stage = request.POST.get("stage", "quote")
        policy.status = request.POST.get("status", "active")
        policy.insurance_type = request.POST.get("insurance_type", "")
        policy.source = request.POST.get("source", "walk_in")
        policy.business_type = request.POST.get("business_type", "new_business")
        policy.bound_date = request.POST.get("bound_date") or None
        policy.start_date = request.POST.get("start_date")
        policy.end_date = request.POST.get("end_date")
        policy.insurance_period_months = int(request.POST.get("insurance_period_months", "6") or 6)

        inactive_date = request.POST.get("inactive_date")
        policy.inactive_date = inactive_date or None

        if not policy.added_by:
            policy.added_by = request.user

        try:
            policy.save()
            messages.success(request, "Insurance policy updated.")
        except Exception as e:
            messages.error(request, f"Error updating policy: {e}")
        return _redirect_to_insurance_detail(policy.organization)

    return JsonResponse({
        "id": policy.id,
        "client_name": policy.client.name if policy.client else "",
        "client_id": policy.client_id,
        "insurance_company_id": policy.insurance_company_id,
        "policy_number": policy.policy_number,
        "premium": str(policy.premium),
        "broker_fee": str(policy.broker_fee),
        "commission_rate": str(policy.commission_rate),
        "stage": policy.stage,
        "status": policy.status,
        "insurance_type": policy.insurance_type,
        "source": policy.source,
        "business_type": policy.business_type,
        "bound_date": str(policy.bound_date) if policy.bound_date else "",
        "start_date": str(policy.start_date),
        "end_date": str(policy.end_date),
        "insurance_period_months": policy.insurance_period_months,
        "inactive_date": str(policy.inactive_date) if policy.inactive_date else "",
    })


@login_required
def delete_insurance_policy(request, policy_id):
    from .models import InsurancePolicy
    organizations = _get_user_organizations(request)
    policy = get_object_or_404(InsurancePolicy, id=policy_id, organization__in=organizations)
    org = policy.organization
    policy.delete()
    messages.success(request, "Policy deleted.")
    return _redirect_to_insurance_detail(org)


@login_required
@require_POST
def delete_document(request, doc_id):
    """Delete a ServiceDocument (uploaded file) by its ID."""
    doc = get_object_or_404(ServiceDocument, id=doc_id)
    
    # Permission check: user must belong to the org of the linked vehicle or service_record
    org = None
    if doc.vehicle:
        org = doc.vehicle.client.organization
    elif doc.service_record:
        org = doc.service_record.organization
    
    if org:
        organizations = _get_user_organizations(request)
        if not organizations.filter(id=org.id).exists():
            return JsonResponse({"status": "error", "message": "Access denied."}, status=403)
    
    try:
        # Delete the physical file from storage
        if doc.file:
            import os
            if os.path.isfile(doc.file.path):
                os.remove(doc.file.path)
    except Exception:
        pass  # File may already be gone; proceed with DB deletion
    
    doc.delete()
    return JsonResponse({"status": "ok", "message": "Document deleted."})


@login_required
@require_POST
def delete_service_record(request, service_id):
    """Delete a ServiceRecord. Only owners or agents with can_delete_receipt=True can do this."""
    record = get_object_or_404(ServiceRecord, id=service_id)

    # Resolve the membership for this user in the record's org
    membership = OrganizationMembership.objects.filter(
        user=request.user,
        organization=record.organization,
        is_active=True,
    ).first()

    if not membership:
        return JsonResponse({"status": "error", "message": "Access denied."}, status=403)

    is_owner = membership.role == OrganizationMembership.Role.OWNER
    can_delete = is_owner or membership.can_delete_receipt

    if not can_delete:
        return JsonResponse({"status": "error", "message": "You do not have permission to delete receipts."}, status=403)

    receipt_number = record.receipt_number
    record.delete()

    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        "Receipt %s (ID %s) deleted by %s",
        receipt_number, service_id, request.user.username,
    )

    return JsonResponse({"status": "ok", "message": "Receipt deleted successfully."})


@login_required
@require_POST
def add_insurance_company(request):
    from .models import InsuranceCompany
    org_id = request.POST.get("organization")
    organizations = _get_user_organizations(request)
    org = get_object_or_404(organizations, id=org_id)

    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"success": False, "error": "Company name cannot be empty."}, status=400)

    try:
        company, created = InsuranceCompany.objects.get_or_create(organization=org, name=name)
        return JsonResponse({"success": True, "id": company.id, "name": company.name, "created": created})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def delete_insurance_company(request, company_id):
    from .models import InsuranceCompany
    organizations = _get_user_organizations(request)
    company = get_object_or_404(InsuranceCompany, id=company_id, organization__in=organizations)
    org = company.organization
    company.delete()
    messages.success(request, "Company deleted.")
    return _redirect_to_insurance_detail(org)


@login_required
@require_POST
def add_bank_account(request):
    from .models import BankAccount
    org_id = request.POST.get("organization")
    organizations = _get_user_organizations(request)
    org = get_object_or_404(organizations, id=org_id)
    
    account_name = request.POST.get("account_name", "").strip()
    bank_name = request.POST.get("bank_name", "").strip()
    account_number = request.POST.get("account_number", "").strip()
    balance = request.POST.get("balance", "0.00").strip()
    
    if account_name:
        try:
            BankAccount.objects.create(
                organization=org,
                account_name=account_name,
                bank_name=bank_name,
                account_number=account_number,
                balance=Decimal(balance or "0.00")
            )
            messages.success(request, "Bank account added.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return _redirect_to_insurance_detail(org)


@login_required
def delete_bank_account(request, account_id):
    from .models import BankAccount
    organizations = _get_user_organizations(request)
    account = get_object_or_404(BankAccount, id=account_id, organization__in=organizations)
    org = account.organization
    account.delete()
    messages.success(request, "Bank account deleted.")
    return _redirect_to_insurance_detail(org)


@login_required
@require_POST
def add_bank_transaction(request):
    from .models import BankTransaction, BankAccount, InsuranceCompany
    org_id = request.POST.get("organization")
    organizations = _get_user_organizations(request)
    org = get_object_or_404(organizations, id=org_id)
    
    account_id = request.POST.get("bank_account")
    account = get_object_or_404(BankAccount, id=account_id, organization=org)
    
    transaction_type = request.POST.get("transaction_type")
    amount = request.POST.get("amount", "0.00").strip()
    category = request.POST.get("category", "").strip()
    description = request.POST.get("description", "").strip()
    date = request.POST.get("date")
    
    company_id = request.POST.get("insurance_company")
    company = None
    if company_id:
        company = get_object_or_404(InsuranceCompany, id=company_id, organization=org)
    
    try:
        BankTransaction.objects.create(
            bank_account=account,
            transaction_type=transaction_type,
            amount=Decimal(amount or "0.00"),
            category=category,
            description=description,
            date=date or timezone.now().date(),
            insurance_company=company
        )
        messages.success(request, "Transaction recorded.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
        
    return _redirect_to_insurance_detail(org)


@login_required
def delete_bank_transaction(request, transaction_id):
    from .models import BankTransaction
    organizations = _get_user_organizations(request)
    transaction = get_object_or_404(
        BankTransaction, 
        id=transaction_id, 
        bank_account__organization__in=organizations
    )
    org = transaction.bank_account.organization
    transaction.delete()
    messages.success(request, "Transaction deleted.")
    return _redirect_to_insurance_detail(org)


@login_required
def export_insurance_report_pdf(request):
    from .models import InsurancePolicy, InsuranceCompany, BankTransaction
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    
    organizations = _get_user_organizations(request)
    active_org_id = request.session.get('active_org_id')
    org = get_object_or_404(organizations, id=active_org_id)
    
    is_locked = org.insurance_space_locked and org.insurance_space_password
    unlocked_session_key = f"insurance_unlocked_{org.id}"
    is_unlocked = request.session.get(unlocked_session_key, False)
    if is_locked and not is_unlocked:
        return HttpResponseForbidden("Access denied. Insurance Space is locked.")
        
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    policies = InsurancePolicy.objects.filter(organization=org).select_related("client", "insurance_company")
    
    if start_date_str:
        policies = policies.filter(start_date__gte=start_date_str)
    if end_date_str:
        policies = policies.filter(start_date__lte=end_date_str)
        
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="insurance-report-{org.id}.pdf"'
    
    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin_x = 40
    content_width = width - (margin_x * 2)
    y = height - 60
    
    pdf.setFillColorRGB(0.06, 0.24, 0.47)
    pdf.roundRect(margin_x, y - 40, content_width, 60, 8, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(width / 2, y - 8, f"{org.name} - Insurance & Commission Report")
    pdf.setFont("Helvetica", 9)
    date_range_label = f"Range: {start_date_str or 'All Time'} to {end_date_str or 'All Time'}"
    pdf.drawCentredString(width / 2, y - 24, date_range_label)
    
    y -= 80
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin_x, y, "Operational Metrics Summary:")
    
    # Convert querysets to lists to safely mutate Python attributes
    policies_list = list(policies)
    
    # Calculate adjusted unearned commissions using the same distribution logic
    insurance_companies = InsuranceCompany.objects.filter(organization=org)
    all_inactive_policies = InsurancePolicy.objects.filter(
        organization=org,
        stage="bound",
        status="inactive"
    ).order_by('inactive_date', 'id')
    
    # Pre-fetch all bank transactions for the company (both income and expense)
    refunds = BankTransaction.objects.filter(
        insurance_company__in=insurance_companies
    )
    if start_date_str:
        refunds = refunds.filter(date__gte=start_date_str)
    if end_date_str:
        refunds = refunds.filter(date__lte=end_date_str)
        
    adjusted_unearned_map = {}
    for company in insurance_companies:
        company_refunds = refunds.filter(insurance_company=company)
        company_refunded = sum(r.amount for r in company_refunds)
        
        comp_inactive = all_inactive_policies.filter(insurance_company=company)
        if start_date_str:
            comp_inactive = comp_inactive.filter(start_date__gte=start_date_str)
        if end_date_str:
            comp_inactive = comp_inactive.filter(start_date__lte=end_date_str)
            
        remaining_refund = company_refunded
        for p in comp_inactive:
            raw_val = p.unearned_commission
            if remaining_refund >= raw_val:
                adjusted_unearned_map[p.id] = Decimal("0.00")
                remaining_refund -= raw_val
            else:
                adjusted_unearned_map[p.id] = raw_val - remaining_refund
                remaining_refund = Decimal("0.00")
                
    # Apply adjusted unearned commissions to the policies list
    for p in policies_list:
        if p.id in adjusted_unearned_map:
            p.unearned_commission = adjusted_unearned_map[p.id]
            
    active_policies_list = [p for p in policies_list if p.stage == "bound" and p.status == "active"]
    inactive_policies_list = [p for p in policies_list if p.stage == "bound" and p.status == "inactive"]
    
    tot_premium = sum(p.premium for p in active_policies_list)
    tot_commission = sum(p.commission_amount for p in active_policies_list)
    tot_unearned = sum(p.unearned_commission for p in inactive_policies_list)
    
    y -= 18
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margin_x, y, f"Active Policies: {len(active_policies_list)}")
    pdf.drawString(margin_x + 150, y, f"Total Active Premiums: ${tot_premium:,.2f}")
    pdf.drawString(margin_x + 350, y, f"Total Active Commissions: ${tot_commission:,.2f}")
    
    y -= 14
    pdf.drawString(margin_x, y, f"Inactive Policies: {len(inactive_policies_list)}")
    pdf.drawString(margin_x + 150, y, f"Total Unearned Commissions (Due back): ${tot_unearned:,.2f}")
    
    y -= 30
    pdf.setFillColorRGB(0.9, 0.9, 0.95)
    pdf.rect(margin_x, y - 4, content_width, 16, fill=1, stroke=0)
    pdf.setFillColorRGB(0.06, 0.24, 0.47)
    pdf.setFont("Helvetica-Bold", 8)
    
    cols = [
        ("Client", 110),
        ("Policy #", 80),
        ("Company", 90),
        ("Premium", 60),
        ("Rate", 45),
        ("Comm Amount", 70),
        ("Status", 55),
    ]
    
    current_x = margin_x + 4
    for title, w in cols:
        pdf.drawString(current_x, y, title)
        current_x += w
        
    y -= 4
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica", 8)
    
    for p in policies_list:
        y -= 16
        if y < 40:
            pdf.showPage()
            y = height - 60
            pdf.setFont("Helvetica-Bold", 8)
            pdf.setFillColorRGB(0.06, 0.24, 0.47)
            pdf.setFillColorRGB(0.9, 0.9, 0.95)
            pdf.rect(margin_x, y - 4, content_width, 16, fill=1, stroke=0)
            pdf.setFillColorRGB(0.06, 0.24, 0.47)
            current_x = margin_x + 4
            for title, w in cols:
                pdf.drawString(current_x, y, title)
                current_x += w
            y -= 20
            pdf.setFillColorRGB(0.1, 0.1, 0.1)
            pdf.setFont("Helvetica", 8)
            
        current_x = margin_x + 4
        client_name = p.client.name if p.client else "N/A"
        if len(client_name) > 22:
            client_name = client_name[:20] + ".."
            
        pdf.drawString(current_x, y, client_name)
        current_x += 110
        pdf.drawString(current_x, y, p.policy_number)
        current_x += 80
        pdf.drawString(current_x, y, p.insurance_company.name if p.insurance_company else "N/A")
        current_x += 90
        pdf.drawString(current_x, y, f"${p.premium:,.2f}")
        current_x += 60
        pdf.drawString(current_x, y, f"{p.commission_rate}%")
        current_x += 45
        pdf.drawString(current_x, y, f"${p.commission_amount:,.2f}")
        current_x += 70
        
        status_label = f"{p.stage.upper()} / {p.status.upper()}"
        if p.stage == "bound" and p.status == "inactive":
            status_label += f" (${p.unearned_commission:,.2f} unearned)"
        pdf.drawString(current_x, y, status_label)
        
    pdf.save()
    return response


# ─────────────────────────────────────────────────────────────────────────────
# INSURANCE COMPANY DETAIL PAGE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def insurance_company_detail(request, company_id):
    from .models import InsuranceCompany, InsurancePolicy, InsuranceCompanyDocument, BankTransaction
    organizations = _get_user_organizations(request)
    company = get_object_or_404(InsuranceCompany, id=company_id, organization__in=organizations)
    active_org = company.organization

    # Permission check
    if not request.user.is_superuser:
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=active_org, is_active=True
        ).first()
        if not membership:
            return HttpResponseForbidden("Access denied.")

    # Lock check
    is_locked = active_org.insurance_space_locked and active_org.insurance_space_password
    unlocked_session_key = f"insurance_unlocked_{active_org.id}"
    is_unlocked = request.session.get(unlocked_session_key, False)
    if is_locked and not is_unlocked:
        return redirect("inventory-detail", inventory_id=_get_insurance_space_id(active_org))

    # Policy filters
    search_query = request.GET.get("q", "").strip()
    stage_filter = request.GET.get("stage", "").strip()
    status_filter = request.GET.get("status", "").strip()
    type_filter = request.GET.get("insurance_type", "").strip()
    agent_filter = request.GET.get("agent", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    min_premium = request.GET.get("min_premium", "").strip()
    max_premium = request.GET.get("max_premium", "").strip()

    policies = InsurancePolicy.objects.filter(
        organization=active_org, insurance_company=company
    ).select_related("client", "added_by")

    if search_query:
        from django.db.models import Q
        policies = policies.filter(
            Q(policy_number__icontains=search_query) |
            Q(client__first_name__icontains=search_query) |
            Q(client__last_name__icontains=search_query)
        )
    if stage_filter:
        policies = policies.filter(stage=stage_filter)
    if status_filter:
        policies = policies.filter(status=status_filter)
    if type_filter:
        policies = policies.filter(insurance_type=type_filter)
    if agent_filter:
        policies = policies.filter(added_by_id=agent_filter)
    if date_from:
        policies = policies.filter(start_date__gte=date_from)
    if date_to:
        policies = policies.filter(start_date__lte=date_to)
    if min_premium:
        try:
            policies = policies.filter(premium__gte=Decimal(min_premium))
        except Exception:
            pass
    if max_premium:
        try:
            policies = policies.filter(premium__lte=Decimal(max_premium))
        except Exception:
            pass

    # Pagination for policies
    policy_page_num = request.GET.get("page", 1)
    policy_paginator = Paginator(policies, 15)
    try:
        policies_page = policy_paginator.page(policy_page_num)
    except Exception:
        policies_page = policy_paginator.page(1)

    # Metrics
    all_policies = InsurancePolicy.objects.filter(organization=active_org, insurance_company=company)
    active_count = all_policies.filter(stage="bound", status="active").count()
    quote_count = all_policies.filter(stage="quote").count()
    bound_count = all_policies.filter(stage="bound").count()
    inactive_count = all_policies.filter(stage="bound", status="inactive").count()
    pending_count = all_policies.filter(status="pending").count()
    rejected_count = all_policies.filter(status="rejected").count()
    total_premium = sum(p.premium for p in all_policies.filter(stage="bound", status="active"))
    total_commission = sum(p.commission_amount for p in all_policies.filter(stage="bound", status="active"))
    total_unearned = sum(p.unearned_commission for p in all_policies.filter(stage="bound", status="inactive"))

    # Documents
    documents = InsuranceCompanyDocument.objects.filter(insurance_company=company)

    # Bank transactions for this company
    company_transactions = BankTransaction.objects.filter(
        insurance_company=company
    ).select_related("bank_account").order_by("-date", "-created_at")

    # Bank accounts for deposit modal
    from .models import BankAccount
    bank_accounts = BankAccount.objects.filter(organization=active_org)

    import json
    income_categories = json.dumps(["Insurance Premium Receipt", "Commission Payment", "Interest", "Other Income"])
    expense_categories = json.dumps(["Rent", "Utilities", "Payroll", "Office Supplies", "Marketing", "Other Expense"])

    # Insurance agents for agent filter
    insurance_agents = OrganizationMembership.objects.filter(
        organization=active_org,
        can_deal_with_insurance=True,
        is_active=True,
        user__is_active=True
    ).select_related("user")

    return render(request, "core/insurance_company_detail.html", {
        "company": company,
        "active_org": active_org,
        "policies_page": policies_page,
        "documents": documents,
        "company_transactions": company_transactions,
        "bank_accounts": bank_accounts,
        "active_count": active_count,
        "quote_count": quote_count,
        "bound_count": bound_count,
        "inactive_count": inactive_count,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "total_premium": total_premium,
        "total_commission": total_commission,
        "total_unearned": total_unearned,
        "insurance_agents": insurance_agents,
        "income_categories": income_categories,
        "expense_categories": expense_categories,
        "insurance_space_id": _get_insurance_space_id(active_org),
        # Filter persistence
        "search_query": search_query,
        "stage_filter": stage_filter,
        "status_filter": status_filter,
        "type_filter": type_filter,
        "agent_filter": agent_filter,
        "date_from": date_from,
        "date_to": date_to,
        "min_premium": min_premium,
        "max_premium": max_premium,
    })


def _get_insurance_space_id(org):
    from .models import Space
    space = Space.objects.filter(organization=org, key="insurance").first()
    return space.id if space else 0


@login_required
@require_POST
def insurance_company_upload_document(request, company_id):
    from .models import InsuranceCompany, InsuranceCompanyDocument
    organizations = _get_user_organizations(request)
    company = get_object_or_404(InsuranceCompany, id=company_id, organization__in=organizations)

    title = request.POST.get("title", "").strip()
    document_date = request.POST.get("document_date", "") or None
    uploaded_file = request.FILES.get("document")

    if not uploaded_file:
        messages.error(request, "Please select a file to upload.")
        return redirect("insurance-company-detail", company_id=company.id)

    try:
        InsuranceCompanyDocument.objects.create(
            insurance_company=company,
            title=title,
            document=uploaded_file,
            document_date=document_date or None,
        )
        messages.success(request, "Document uploaded successfully.")
    except Exception as e:
        messages.error(request, f"Upload error: {e}")

    return redirect("insurance-company-detail", company_id=company.id)


@login_required
def insurance_company_delete_document(request, doc_id):
    from .models import InsuranceCompanyDocument
    organizations = _get_user_organizations(request)
    doc = get_object_or_404(InsuranceCompanyDocument, id=doc_id, insurance_company__organization__in=organizations)
    company_id = doc.insurance_company_id
    try:
        import os
        if doc.document and os.path.isfile(doc.document.path):
            os.remove(doc.document.path)
    except Exception:
        pass
    doc.delete()
    messages.success(request, "Document deleted.")
    return redirect("insurance-company-detail", company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# INSURANCE AGENT DETAIL PAGE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def insurance_agent_detail(request, user_id):
    from django.contrib.auth import get_user_model
    from .models import InsurancePolicy, InsuranceCompany
    from datetime import date as _date
    import calendar as _calendar
    User = get_user_model()
    organizations = _get_user_organizations(request)

    agent = get_object_or_404(User, id=user_id, is_active=True)

    # Determine active org from session
    active_org_id = request.session.get("active_org_id")
    active_org = None
    if active_org_id:
        active_org = organizations.filter(id=active_org_id).first()
    if not active_org:
        active_org = organizations.filter(
            memberships__user=agent,
            memberships__is_active=True
        ).first()
    if not active_org:
        return HttpResponseForbidden("No organization context found.")

    # Permission check
    if not request.user.is_superuser:
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=active_org, is_active=True
        ).first()
        if not membership:
            return HttpResponseForbidden("Access denied.")

    # Lock check
    is_locked = active_org.insurance_space_locked and active_org.insurance_space_password
    unlocked_session_key = f"insurance_unlocked_{active_org.id}"
    is_unlocked = request.session.get(unlocked_session_key, False)
    if is_locked and not is_unlocked:
        return redirect("inventory-detail", inventory_id=_get_insurance_space_id(active_org))

    # ── Period Auditing ──────────────────────────────────────────────────────
    today = _date.today()
    period = request.GET.get("period", "today").strip()
    custom_from_str = request.GET.get("date_from", "").strip()
    custom_to_str = request.GET.get("date_to", "").strip()

    audit_start = None
    audit_end = None

    if period == "today":
        audit_start = today
        audit_end = today
    elif period == "month":
        audit_start = today.replace(day=1)
        audit_end = today.replace(day=_calendar.monthrange(today.year, today.month)[1])
    elif period == "year":
        audit_start = today.replace(month=1, day=1)
        audit_end = today.replace(month=12, day=31)
    elif period == "custom" and custom_from_str and custom_to_str:
        try:
            from django.utils import timezone as tz
            audit_start = tz.datetime.strptime(custom_from_str, "%Y-%m-%d").date()
            audit_end = tz.datetime.strptime(custom_to_str, "%Y-%m-%d").date()
        except Exception:
            audit_start = today
            audit_end = today
    # period == "all" leaves audit_start/audit_end as None (no date filter)

    # All agent policies (unfiltered by date – used for lifetime metrics)
    all_agent_policies = InsurancePolicy.objects.filter(
        organization=active_org, added_by=agent
    ).select_related("client", "insurance_company")

    # Period-scoped policies (for auditing metrics)
    if audit_start and audit_end:
        period_policies = all_agent_policies.filter(
            created_at__date__gte=audit_start,
            created_at__date__lte=audit_end,
        )
    else:
        period_policies = all_agent_policies

    # ── CRM Table Filters ─────────────────────────────────────────────────────
    search_query = request.GET.get("q", "").strip()
    stage_filter = request.GET.get("stage", "").strip()
    status_filter = request.GET.get("status", "").strip()
    type_filter = request.GET.get("insurance_type", "").strip()
    source_filter = request.GET.get("source", "").strip()
    business_type_filter = request.GET.get("business_type", "").strip()
    company_filter = request.GET.get("insurance_company", "").strip()
    table_date_from = request.GET.get("tbl_date_from", "").strip()
    table_date_to = request.GET.get("tbl_date_to", "").strip()

    policies = all_agent_policies
    if search_query:
        from django.db.models import Q
        policies = policies.filter(
            Q(policy_number__icontains=search_query) |
            Q(client__first_name__icontains=search_query) |
            Q(client__last_name__icontains=search_query)
        )
    if stage_filter:
        policies = policies.filter(stage=stage_filter)
    if status_filter:
        policies = policies.filter(status=status_filter)
    if type_filter:
        policies = policies.filter(insurance_type=type_filter)
    if source_filter:
        policies = policies.filter(source=source_filter)
    if business_type_filter:
        policies = policies.filter(business_type=business_type_filter)
    if company_filter:
        policies = policies.filter(insurance_company_id=company_filter)
    if table_date_from:
        policies = policies.filter(start_date__gte=table_date_from)
    if table_date_to:
        policies = policies.filter(start_date__lte=table_date_to)

    # Pagination
    page_num = request.GET.get("page", 1)
    paginator = Paginator(policies, 15)
    try:
        policies_page = paginator.page(page_num)
    except Exception:
        policies_page = paginator.page(1)

    # ── Period Metrics ────────────────────────────────────────────────────────
    bound_policies_period = period_policies.filter(stage="bound")
    active_policies_period = period_policies.filter(stage="bound", status="active")
    inactive_policies_period = period_policies.filter(stage="bound", status="inactive")
    pending_policies_period = period_policies.filter(status="pending")
    rejected_policies_period = period_policies.filter(status="rejected")

    quote_count = period_policies.filter(stage="quote").count()
    bound_count = bound_policies_period.count()
    active_count = active_policies_period.count()
    inactive_count = inactive_policies_period.count()
    pending_count = pending_policies_period.count()
    rejected_count = rejected_policies_period.count()

    total_premium = sum(p.premium for p in active_policies_period)
    total_commission = sum(p.commission_amount for p in bound_policies_period)
    total_broker_fees = sum(p.broker_fee for p in bound_policies_period)
    total_profit = total_commission + total_broker_fees
    conversion_rate = (bound_count / (quote_count + bound_count) * 100) if (quote_count + bound_count) > 0 else 0

    insurance_companies = InsuranceCompany.objects.filter(organization=active_org)
    insurance_space_id = _get_insurance_space_id(active_org)

    return render(request, "core/insurance_agent_detail.html", {
        "agent": agent,
        "active_org": active_org,
        "insurance_space_id": insurance_space_id,
        "policies_page": policies_page,
        "insurance_companies": insurance_companies,
        # Period auditing
        "period": period,
        "audit_start": audit_start,
        "audit_end": audit_end,
        "custom_from_str": custom_from_str,
        "custom_to_str": custom_to_str,
        # Metrics
        "quote_count": quote_count,
        "bound_count": bound_count,
        "active_count": active_count,
        "inactive_count": inactive_count,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "total_premium": total_premium,
        "total_commission": total_commission,
        "total_broker_fees": total_broker_fees,
        "total_profit": total_profit,
        "conversion_rate": conversion_rate,
        # Filter persistence
        "search_query": search_query,
        "stage_filter": stage_filter,
        "status_filter": status_filter,
        "type_filter": type_filter,
        "source_filter": source_filter,
        "business_type_filter": business_type_filter,
        "company_filter": company_filter,
        "table_date_from": table_date_from,
        "table_date_to": table_date_to,
    })


@login_required
@require_POST
def add_knowledge_material(request, space_id):
    from .models import Space, KnowledgeHubMaterial, OrganizationMembership
    organizations = _get_user_organizations(request)
    space = get_object_or_404(Space, id=space_id, organization__in=organizations)
    
    # Check if user is owner, superuser, or has can_manage_knowledge_hub
    can_manage = False
    if request.user.is_superuser:
        can_manage = True
    else:
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=space.organization, is_active=True
        ).first()
        if membership:
            is_owner = (membership.role == OrganizationMembership.Role.OWNER)
            has_space_access = membership.accessible_spaces.filter(id=space.id).exists()
            can_manage = is_owner or (membership.can_manage_knowledge_hub and has_space_access)

    if not can_manage:
        return HttpResponseForbidden("You do not have permission to add training materials.")
        
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    step_number = request.POST.get("step_number", "1").strip()
    external_url = request.POST.get("external_url", "").strip()
    roadmap_name = request.POST.get("roadmap_name", "General Roadmap").strip() or "General Roadmap"
    parent_id = request.POST.get("parent_id", "").strip()
    
    try:
        step_number = int(step_number)
    except ValueError:
        step_number = 1
        
    file_attachment = request.FILES.get("file")
    
    if not title:
        messages.error(request, "Material title is required.")
        return redirect("inventory-detail", inventory_id=space.id)
    
    parent_obj = None
    if parent_id:
        try:
            parent_obj = KnowledgeHubMaterial.objects.get(id=int(parent_id), space=space)
        except (KnowledgeHubMaterial.DoesNotExist, ValueError):
            parent_obj = None
        
    KnowledgeHubMaterial.objects.create(
        space=space,
        parent=parent_obj,
        roadmap_name=roadmap_name if not parent_obj else parent_obj.roadmap_name,
        title=title,
        description=description,
        step_number=step_number,
        external_url=external_url,
        file=file_attachment
    )
    messages.success(request, f"Successfully added '{title}' to '{roadmap_name}'.")
    return redirect("inventory-detail", inventory_id=space.id)


@login_required
@require_POST
def delete_knowledge_material(request, material_id):
    from .models import KnowledgeHubMaterial, OrganizationMembership
    material = get_object_or_404(KnowledgeHubMaterial, id=material_id)
    space = material.space
    
    # Check if user is owner, superuser, or has can_manage_knowledge_hub
    can_manage = False
    if request.user.is_superuser:
        can_manage = True
    else:
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=space.organization, is_active=True
        ).first()
        if membership:
            is_owner = (membership.role == OrganizationMembership.Role.OWNER)
            has_space_access = membership.accessible_spaces.filter(id=space.id).exists()
            can_manage = is_owner or (membership.can_manage_knowledge_hub and has_space_access)

    if not can_manage:
        return HttpResponseForbidden("You do not have permission to delete training materials.")
        
    title = material.title
    material.delete()
    messages.success(request, f"Deleted material '{title}'.")
    return redirect("inventory-detail", inventory_id=space.id)


