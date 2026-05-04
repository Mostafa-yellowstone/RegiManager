from decimal import Decimal

from django.db.models import Count, Sum, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
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
)
from .models import (
    Organization, OrganizationMembership, ServiceAuditLog, ServiceRecord, 
    ServiceDocument, CustomServiceType, CarDealer, DealerPayment, Client, Vehicle
)
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from datetime import timedelta
from .tasks import send_automation_email
from .models import AutomationLog


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


def home(request):
    return render(request, "core/home.html")


def contact(request):
    return render(request, "core/contact.html")



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
                messages.error(request, f"Cannot register: Agency '{organization.name}' has reached its maximum limit of {organization.max_agents} agents.")
                return render(
                    request,
                    "core/auth_form.html",
                    {
                        "title": "Create Agent Account",
                        "subtitle": "Create a separate agent account inside an existing Agency.",
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
    return render(
        request,
        "core/auth_form.html",
        {
            "title": "Create Agent Account",
            "subtitle": "Create a separate agent account inside an existing Agency.",
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
            "title": "Sign In to DMV Portal",
            "subtitle": "Access vehicle registrations, renewals, plate transfers, and insurance lapse payments.",
            "form": form,
            "submit_text": "Sign In",
            "switch_label": "Need an agent account?",
            "switch_url": "member-signup",
            "switch_text": "Create agent account",
        },
    )


@login_required
def add_client(request):
    organizations = Organization.objects.filter(memberships__user=request.user).distinct()
    if request.method == "POST":
        form = ClientForm(request.POST, organizations=organizations)
        if form.is_valid():
            client = form.save(commit=False)
            
            # If organization field was disabled, it might not be in cleaned_data
            if not client.organization_id and organizations.count() == 1:
                client.organization = organizations.first()
            
            # Dealer logic
            source = form.cleaned_data.get('source')
            if source == 'car dealer':
                dealer_select = form.cleaned_data.get('dealer_select')
                if dealer_select and dealer_select != 'new':
                    try:
                        dealer = CarDealer.objects.get(id=dealer_select, organization=client.organization)
                        client.dealer = dealer
                    except CarDealer.DoesNotExist:
                        pass
                else:
                    dealer_name = form.cleaned_data.get('dealer_name')
                    if dealer_name:
                        dealer, _ = CarDealer.objects.get_or_create(
                            organization=client.organization,
                            name=dealer_name,
                            defaults={
                                'address': form.cleaned_data.get('dealer_address', ''),
                                'phone_no': form.cleaned_data.get('dealer_phone_no', ''),
                                'email': form.cleaned_data.get('dealer_email', ''),
                                'is_partner': form.cleaned_data.get('is_partner', False),
                            }
                        )
                        client.dealer = dealer
            
            client.save()
            messages.success(request, f"Client {client} added successfully.")
            return redirect("client-detail", client_id=client.id)
    else:
        form = ClientForm(organizations=organizations)
    
    return render(request, "core/add_client.html", {"form": form})


@login_required
def client_detail(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if not OrganizationMembership.objects.filter(user=request.user, organization=client.organization).exists():
        return HttpResponseForbidden("Access denied.")
    
    vehicles = client.vehicles.all()
    records = ServiceRecord.objects.filter(vehicle__client=client).order_by("-created_at")
    
    total_spend = sum(r.service_fee for r in records)
    total_services = records.count()
    last_service_date = records.first().created_at if records.exists() else None
    
    from django.db.models import Q
    all_docs = ServiceDocument.objects.filter(
        Q(vehicle__client=client) | Q(service_record__vehicle__client=client)
    ).distinct().order_by("-uploaded_at")
    
    return render(request, "core/client_profile.html", {
        "client": client, 
        "vehicles": vehicles,
        "records": records,
        "documents": all_docs,
        "total_spend": total_spend,
        "total_services": total_services,
        "last_service_date": last_service_date
    })


@login_required
def all_clients(request):
    owner_org_ids = OrganizationMembership.objects.filter(
        user=request.user
    ).values_list("organization_id", flat=True)
    
    clients = Client.objects.filter(organization_id__in=owner_org_ids).order_by("-created_at")
    
    query = request.GET.get('q')
    if query:
        clients = clients.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone_number__icontains=query) |
            Q(city__icontains=query)
        ).distinct()
        
    return render(request, "core/all_clients.html", {
        "clients": clients,
        "search_query": query or "",
    })


@login_required
def add_vehicle(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == "POST":
        form = VehicleForm(request.POST)
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
        form = VehicleForm(initial={'vehicle_number': auto_vnum})
    
    return render(request, "core/add_vehicle.html", {"client": client, "form": form})


@login_required
def check_vin_ajax(request):
    vin = request.GET.get("vin", "").strip().upper()
    if not vin:
        return JsonResponse({"exists": False, "is_valid": False})
    
    # Structural check (Modern VINs are 17 characters and don't contain I, O, or Q)
    is_valid_format = len(vin) == 17 and not any(c in vin for c in "IOQ")
    
    # 1. Check for duplicates in our system
    vehicle = Vehicle.objects.filter(vin=vin).first()
    if vehicle:
        return JsonResponse({
            "exists": True,
            "is_valid": is_valid_format,
            "owner": str(vehicle.client),
            "vehicle": f"{vehicle.year} {vehicle.make} {vehicle.model}",
            "plate": vehicle.plate_number or "N/A",
        })
    
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
                    "weight": data.get("GVWR"),
                    "seats": data.get("Seats"),
                    "color": data.get("ExteriorColor"),
                }
        except Exception as e:
            print(f"VIN Decoding Error: {e}")

    return JsonResponse({
        "exists": False, 
        "is_valid": is_valid_format,
        "decoded": decoded_data
    })


@login_required
def check_client_name_ajax(request):
    first_name = request.GET.get("first_name", "").strip()
    last_name = request.GET.get("last_name", "").strip()
    org_id = request.GET.get("org_id")
    
    if not first_name or not last_name or not org_id:
        return JsonResponse({"exists": False})
    
    exists = Client.objects.filter(
        first_name__iexact=first_name,
        last_name__iexact=last_name,
        organization_id=org_id
    ).exists()
    
    return JsonResponse({"exists": exists})


@login_required
def vehicle_detail(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    if not OrganizationMembership.objects.filter(user=request.user, organization=vehicle.client.organization).exists():
        return HttpResponseForbidden("Access denied.")
    
    from django.db.models import Q
    # Show all docs for this client's fleet
    documents = ServiceDocument.objects.filter(
        Q(vehicle__client=vehicle.client) | 
        Q(service_record__vehicle__client=vehicle.client)
    ).distinct()
    service_records = vehicle.service_records.all()
    
    return render(request, "core/vehicle_detail.html", {
        "vehicle": vehicle,
        "documents": documents,
        "service_records": service_records
    })


@login_required
def start_process(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    if not OrganizationMembership.objects.filter(user=request.user, organization=vehicle.client.organization).exists():
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
            
            # Auto-link to dealer if this client came from a dealership
            if vehicle.client.dealer:
                record.dealer = vehicle.client.dealer
                
                # Logic for automated ledger
                total_paid = form.cleaned_data.get('total_paid') or 0
                total_fees = record.processing_fee + record.dmv_fee + record.sales_tax + record.credit_card_fee
                
                # Automatically calculate the balance if dealer is selected
                if total_paid < total_fees:
                    record.dealer_balance = total_fees - total_paid
                else:
                    record.dealer_balance = 0
                    # If balance is 0, we can ensure the record looks clean
            
            record.save()
            
            # If dealer and there is a balance, create a DealerPayment ledger record
            if record.dealer and record.dealer_balance > 0:
                from .models import DealerPayment
                DealerPayment.objects.create(
                    dealer=record.dealer,
                    service_record=record,
                    amount=record.dealer_balance,
                    payment_type="debt",
                    notes=f"Initial debt from {record.service_type_label}"
                )

            ServiceAuditLog.objects.create(
                organization=record.organization,
                service_record=record,
                actor=request.user,
                action="created",
                details=f"Service {record.service_type} started for vehicle {vehicle}. Paid: {form.cleaned_data.get('total_paid', 0)}, Balance: {record.dealer_balance}"
            )
            
            messages.success(request, f"Service {record.service_type} created successfully.")
            
            # Send Confirmation Email and Log
            if vehicle.client.email:
                subject = f"Case Confirmation: {record.case_id} - {record.service_type_label}"
                context = {
                    "client_name": vehicle.client.name,
                    "service_type": record.service_type_label,
                    "case_id": record.case_id,
                }
                send_automation_email.delay(vehicle.client.email, subject, "core/emails/confirmation.html", context)
                
                AutomationLog.objects.create(
                    organization=record.organization,
                    service_record=record,
                    vehicle=vehicle,
                    client=vehicle.client,
                    log_type="confirmation",
                    sent_to=vehicle.client.email,
                    details=f"Initial case confirmation sent for {record.case_id}."
                )
            return redirect("client-detail", client_id=vehicle.client.id)
    else:
        form = VehicleServiceForm(organization=vehicle.client.organization)
    
    return render(request, "core/start_process.html", {"vehicle": vehicle, "form": form})


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect("/admin/")
        
    memberships = OrganizationMembership.objects.filter(user=request.user).select_related(
        "organization"
    )
    organizations = Organization.objects.filter(memberships__user=request.user).distinct()
    
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
    if not is_owner:
        scope_qs = scope_qs.filter(handled_by=request.user)

    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    service_records = scope_qs.select_related("organization", "handled_by")[:3]
    audit_logs = ServiceAuditLog.objects.filter(service_record__in=scope_qs).select_related(
        "actor", "organization", "service_record"
    )[:5]

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
    
    yearly_report = yearly_qs.aggregate(total_records=Count("id"))
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
    user_can_manage_dealers = any(m.can_manage_dealers for m in memberships)
    user_can_trigger_automation = any(m.can_trigger_automation for m in memberships)

    total_outstanding_dealer_balance = Decimal("0")
    if is_owner or user_can_manage_dealers:
        total_outstanding_dealer_balance = scope_qs.filter(
            dealer__isnull=False, 
            is_dealer_paid=False
        ).aggregate(
            total=Sum('dealer_balance')
        )['total'] or Decimal("0")

    # Automation data
    automation_logs = AutomationLog.objects.filter(organization__in=organizations).select_related("vehicle", "client").order_by("-timestamp")[:5]
    
    # Upcoming expirations (next 45 days)
    upcoming_expirations = Vehicle.objects.filter(
        client__organization__in=organizations,
        registration_expiration_date__gte=today,
        registration_expiration_date__lte=today + timedelta(days=45)
    ).select_related("client").order_by("registration_expiration_date")[:5]

    return render(
        request,
        "core/dashboard.html",
        {
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
            "yearly_report": yearly_report,
            "monthly_report": monthly_report,
            "daily_report": daily_report,
            "service_cards": service_cards,
            "show_all_services_card": show_all_services_card,
            "today": today,
            "overall_card_fees": overall_totals["total_card"] or Decimal("0"),
            "total_outstanding_dealer_balance": total_outstanding_dealer_balance,
            "automation_logs": automation_logs,
            "upcoming_expirations": upcoming_expirations,
            "custom_types": custom_types,
            "user_can_trigger_automation": user_can_trigger_automation,
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
        ("Total", 58),
        ("Processing", 58),
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
            _currency(row["amount"]),
            _currency(row["processing"]),
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
    pdf.drawCentredString(width / 2, y, f"Gross Collections: {_currency(totals['total_amount'])}")
    y -= 16
    pdf.drawCentredString(width / 2, y, f"Net Profit (Processing Fees): {_currency(totals['total_processing'])}")
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
        pdf.drawString(margin_x + 80, height - 80, f"Agency Performance Dashboard | {month_start.strftime('%B %Y')}")
        
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
        ("Gross Sales", _currency(totals['total_amount'] or 0), electric_blue, "Revenue generated"),
        ("Net Revenue", _currency(totals['total_processing'] or 0), emerald, "Agency commission"),
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
        pdf.drawString(margin_x + 80, height - 80, f"Agency Activity Audit | {today.strftime('%A, %B %d, %Y')}")
        
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
        ("Today's Revenue", _currency(totals['total_amount'] or 0), charcoal, "Total collections"),
        ("Processing", _currency(totals['total_processing'] or 0), vibrant_amber, "Agency profit"),
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
        f'attachment; filename="receipt-{service_record.receipt_number}.pdf"'
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
    dt = service_record.created_at
    date_str = dt.strftime("%b %d, %Y")
    time_str = dt.strftime("%I:%M %p")
    
    x = margin_x
    draw_box(x, y, 80, 16, "Transaction Date", date_str)
    x += 85
    draw_box(x, y, 60, 16, "Time", time_str)
    x += 65
    draw_box(x, y, 80, 16, "Terminal Number", service_record.terminal_number)
    x += 85
    draw_box(x, y, 80, 16, "Receipt number", receipt_short)
    x += 85
    draw_box(x, y, 80, 16, "Vehicle number", service_record.vehicle_number)
    x += 85
    draw_box(x, y, 70, 16, "Transaction type", service_record.transaction_type)

    y -= 45
    draw_box(margin_x, y, 380, 16, "Client", service_record.client_name.upper())

    y -= 45
    draw_box(margin_x, y, 380, 16, "Client Address", service_record.client_address.upper())

    y -= 40
    
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(margin_x, y, "SERVICES PROVIDED")
    pdf.drawString(margin_x + 220, y, "DMV FEE")
    org_first_word = org_name.split()[0][:10] if org_name else "XPRESS"
    pdf.drawString(margin_x + 340, y, f"{org_first_word} FEE")

    y -= 15

    standard_choices = dict(ServiceRecord.SERVICE_TYPES)
    all_service_names = [v.upper() for k, v in standard_choices.items()]
    custom_services = CustomServiceType.objects.filter(organization=service_record.organization)
    all_service_names.extend([s.label.upper() for s in custom_services])

    actual_svc_display = standard_choices.get(service_record.service_type, service_record.service_type).upper()

    rows = all_service_names

    for row in rows:
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margin_x, y - 8, row)
        
        dmv_val = "$ 0.00"
        org_val = "$ 0.00"
        
        if row == actual_svc_display:
            dmv_val = _currency(service_record.dmv_fee)
            org_val = _currency(service_record.processing_fee)

        # DMV Box
        pdf.rect(margin_x + 220, y - 16, 80, 16)
        pdf.drawRightString(margin_x + 296, y - 11, dmv_val)

        # ORG Box
        pdf.rect(margin_x + 340, y - 16, 80, 16)
        pdf.drawRightString(margin_x + 416, y - 11, org_val)
        
        y -= 25

    # Sales Tax
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(margin_x + 180, y - 8, "SALES TAX")
    pdf.rect(margin_x + 220, y - 16, 80, 16)
    pdf.drawRightString(margin_x + 296, y - 11, "$ 0.00")
    pdf.rect(margin_x + 340, y - 16, 80, 16)
    pdf.drawRightString(margin_x + 416, y - 11, _currency(service_record.sales_tax) if service_record.sales_tax else "$ 0.00")

    y -= 30

    # Sub total
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawRightString(margin_x + 180, y - 8, "SUB TOTAL :::")
    pdf.rect(margin_x + 220, y - 16, 80, 16)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawRightString(margin_x + 296, y - 11, _currency(service_record.dmv_fee))
    pdf.rect(margin_x + 340, y - 16, 80, 16)
    pdf.drawRightString(margin_x + 416, y - 11, _currency(service_record.processing_fee + service_record.sales_tax))

    y -= 40
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawRightString(margin_x + 180, y - 8, "GRAND TOTAL :::")
    pdf.rect(margin_x + 280, y - 16, 100, 18)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawRightString(margin_x + 376, y - 11, _currency(service_record.service_fee))

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
    pdf.line(margin_x + 440, sig_y, margin_x + 550, sig_y)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(margin_x + 495, sig_y - 12, "AGENT SIGNATURE")

    # Payment details table
    py = 150
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
    pdf.drawRightString(margin_x + 526, py + 5, _currency(service_record.service_fee))

    # bottom totals
    py -= 35
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(margin_x, py + 4, "Total CC Fees")
    pdf.rect(margin_x + 60, py, 60, 16)
    pdf.drawRightString(margin_x + 116, py + 4, _currency(service_record.credit_card_fee))

    pdf.drawString(margin_x + 130, py + 4, "Total Paid")
    pdf.rect(margin_x + 180, py, 70, 16)
    pdf.drawRightString(margin_x + 246, py + 4, _currency(service_record.service_fee))

    pdf.drawString(margin_x + 260, py + 4, "Outstanding Balance")
    pdf.rect(margin_x + 355, py, 60, 16)
    outstanding_str = _currency(service_record.dealer_balance) if service_record.dealer_balance and service_record.dealer_balance > 0 else "$ 0.00"
    pdf.drawRightString(margin_x + 411, py + 4, outstanding_str)

    # Footer
    pdf.setFont("Helvetica-Bold", 8)
    footer_text = "This is a licensed Private Service Bureau but is not an official agency of the Department of Motor Vehicles, State of New York."
    pdf.drawCentredString(width / 2, 40, footer_text)

    pdf.save()
    return response


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def service_list(request, service_type):
    organizations = Organization.objects.filter(memberships__user=request.user).distinct()
    scope_qs = ServiceRecord.objects.filter(organization__in=organizations)

    memberships = OrganizationMembership.objects.filter(user=request.user)
    owner_org_ids = list(
        memberships.filter(role=OrganizationMembership.Role.OWNER).values_list(
            "organization_id", flat=True
        )
    )
    is_owner = bool(owner_org_ids)

    if not is_owner:
        scope_qs = scope_qs.filter(handled_by=request.user)

    if service_type != "all":
        scope_qs = scope_qs.filter(service_type=service_type)

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if search_query:
        scope_qs = scope_qs.filter(
            Q(client_name__icontains=search_query) |
            Q(client_identifier__icontains=search_query) |
            Q(receipt_number__icontains=search_query)
        )

    if status_filter in dict(ServiceRecord.STATUS_CHOICES):
        scope_qs = scope_qs.filter(status=status_filter)
        
    if date_from:
        scope_qs = scope_qs.filter(created_at__date__gte=date_from)
    if date_to:
        scope_qs = scope_qs.filter(created_at__date__lte=date_to)

    records = scope_qs.select_related("organization", "handled_by", "vehicle__client")

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

    return render(
        request,
        "core/service_list.html",
        {
            "records": records,
            "service_label": service_label,
            "service_type": service_type,
            "search_query": search_query,
            "status_filter": status_filter,
            "date_from": date_from,
            "date_to": date_to,
            "status_choices": ServiceRecord.STATUS_CHOICES,
        }
    )

@login_required
def service_search_ajax(request):
    service_type = request.GET.get('service_type', 'all')
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    organizations = Organization.objects.filter(memberships__user=request.user).distinct()
    scope_qs = ServiceRecord.objects.filter(organization__in=organizations)

    memberships = OrganizationMembership.objects.filter(user=request.user)
    is_owner = memberships.filter(role=OrganizationMembership.Role.OWNER).exists()

    if not is_owner:
        scope_qs = scope_qs.filter(handled_by=request.user)

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
    organizations = Organization.objects.filter(memberships__user=request.user)
    if not organizations.filter(id=service_record.organization_id).exists():
        return JsonResponse({"status": "error", "message": "Access denied"}, status=403)

    if 'file' not in request.FILES or 'document_type' not in request.POST:
        return JsonResponse({"status": "error", "message": "Missing file or document_type"}, status=400)

    file_obj = request.FILES['file']
    doc_type = request.POST['document_type']

    valid_types = [t[0] for t in ServiceDocument.DOCUMENT_TYPES]
    if doc_type not in valid_types:
        return JsonResponse({"status": "error", "message": "Invalid document type"}, status=400)

    try:
        doc = ServiceDocument.objects.create(
            service_record=service_record,
            vehicle=service_record.vehicle, # Automatically link to vehicle too
            document_type=doc_type,
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
    vehicle = get_object_or_404(Vehicle, pk=vehicle_id)
    # Verify access
    if not OrganizationMembership.objects.filter(user=request.user, organization=vehicle.client.organization).exists():
        return JsonResponse({"status": "error", "message": "Access denied"}, status=403)

    if 'file' not in request.FILES or 'document_type' not in request.POST:
        return JsonResponse({"status": "error", "message": "Missing file or document_type"}, status=400)

    file_obj = request.FILES['file']
    doc_type = request.POST['document_type']

    try:
        doc = ServiceDocument.objects.create(
            vehicle=vehicle,
            document_type=doc_type,
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
        is_owner = OrganizationMembership.objects.filter(
            user=request.user,
            organization=membership.organization,
            role=OrganizationMembership.Role.OWNER
        ).exists()
        
        if not is_owner:
            return JsonResponse({"status": "error", "message": "Unauthorized"})
            
        # Prevent demoting the last owner
        if new_role != OrganizationMembership.Role.OWNER and membership.role == OrganizationMembership.Role.OWNER:
            owner_count = OrganizationMembership.objects.filter(
                organization=membership.organization,
                role=OrganizationMembership.Role.OWNER
            ).count()
            if owner_count <= 1:
                return JsonResponse({"status": "error", "message": "Cannot demote the last owner of the Agency."})

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
        
        is_owner = OrganizationMembership.objects.filter(
            organization=membership.organization,
            user=request.user,
            role=OrganizationMembership.Role.OWNER
        ).exists()
        
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
        elif field == "can_manage_dealers":
            membership.can_manage_dealers = value
        elif field == "can_trigger_automation":
            membership.can_trigger_automation = value
            
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
            "type_label": doc_map.get(doc.document_type, doc.document_type),
            "url": doc.file.url
        }
        for doc in documents
    ]
    
    return JsonResponse({
        "status": "success",
        "documents": docs_data
    })


@login_required
def get_documents_vehicle(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    if not OrganizationMembership.objects.filter(user=request.user, organization=vehicle.client.organization).exists():
        return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)
        
    from django.db.models import Q
    # Get all docs belonging to the owner of this vehicle
    documents = ServiceDocument.objects.filter(
        Q(vehicle__client=vehicle.client) | 
        Q(service_record__vehicle__client=vehicle.client)
    ).distinct()
    doc_map = dict(ServiceDocument.DOCUMENT_TYPES)
    
    docs_data = [
        {
            "id": doc.id,
            "type": doc.document_type,
            "type_label": doc_map.get(doc.document_type, doc.document_type),
            "url": doc.file.url,
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
    
    is_owner = OrganizationMembership.objects.filter(
        organization=organization,
        user=request.user,
        role=OrganizationMembership.Role.OWNER
    ).exists()
    
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
    memberships = OrganizationMembership.objects.filter(user=request.user).select_related("organization")
    organizations = Organization.objects.filter(memberships__user=request.user).distinct()
    
    scope_qs = ServiceRecord.objects.filter(organization__in=organizations)
    
    owner_org_ids = list(
        memberships.filter(role=OrganizationMembership.Role.OWNER).values_list("organization_id", flat=True)
    )
    is_owner = bool(owner_org_ids)
    
    if not is_owner:
        scope_qs = scope_qs.filter(handled_by=request.user)

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
    owner_org_ids = list(
        OrganizationMembership.objects.filter(
            user=request.user, role=OrganizationMembership.Role.OWNER
        ).values_list("organization_id", flat=True)
    )
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
    
    is_owner = OrganizationMembership.objects.filter(
        organization=membership.organization,
        user=request.user,
        role=OrganizationMembership.Role.OWNER
    ).exists()
    
    if not is_owner:
        return HttpResponseForbidden("Owner access required.")

    today = timezone.localdate()
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
    
    total_revenue = round(records_qs.aggregate(rev=Sum("service_fee"))["rev"] or Decimal("0"), 2)
    
    badges = []
    if error_rate > 10:
        badges.append({"label": "Needs Improvement", "type": "danger", "icon": "⚠️"})
    elif total_records > 50 and error_rate < 2:
        badges.append({"label": "Top Performer", "type": "success", "icon": "🏆"})
        
    if total_revenue > 5000:
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

    recent_records = records_qs.order_by("-created_at")[:50]

    context = {
        "agent_membership": membership,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "total_records": total_records,
        "error_rate": round(error_rate, 1),
        "total_revenue": total_revenue,
        "badges": badges,
        "instructions": instructions,
        "chart_dates": json.dumps(chart_dates),
        "chart_counts": json.dumps(chart_counts),
        "pie_labels": json.dumps(pie_labels),
        "pie_counts": json.dumps(pie_counts),
        "recent_records": recent_records,
    }
    return render(request, "core/agent_audit.html", context)


@login_required
def audit_log_list(request):
    organizations = Organization.objects.filter(memberships__user=request.user).distinct()
    scope_qs = ServiceAuditLog.objects.filter(organization__in=organizations).select_related(
        "actor", "organization", "service_record"
    )

    memberships = OrganizationMembership.objects.filter(user=request.user)
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

    logs = scope_qs.order_by("-created_at")[:500]

    return render(
        request,
        "core/all_audit_logs.html",
        {
            "audit_logs": logs,
        }
    )

@login_required
def all_dealers(request):
    memberships = request.user.organization_memberships.select_related("organization")
    if not memberships.exists():
        return redirect("home")

    owner_org_ids = list(
        memberships.filter(role=OrganizationMembership.Role.OWNER).values_list(
            "organization_id", flat=True
        )
    )
    is_owner = bool(owner_org_ids)
    user_can_manage_dealers = any(m.can_manage_dealers for m in memberships)

    if not is_owner and not user_can_manage_dealers:
        return HttpResponseForbidden("You do not have permission to manage dealerships.")

    organizations = [m.organization for m in memberships]
    
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        address = request.POST.get("address")
        is_partner = request.POST.get("is_partner") == "on"
        
        if name:
            CarDealer.objects.create(
                organization=organizations[0],
                name=name,
                email=email,
                phone_no=phone,
                address=address,
                is_partner=is_partner
            )
            messages.success(request, f"Dealership '{name}' registered successfully.")
            return redirect("all-dealers")

    dealers = CarDealer.objects.filter(organization__in=organizations).annotate(
        record_count=Count('service_records')
    ).order_by('name')

    # Calculate outstanding balance per dealer
    for dealer in dealers:
        dealer.outstanding = ServiceRecord.objects.filter(
            dealer=dealer, 
            is_dealer_paid=False
        ).aggregate(total=Sum('dealer_balance'))['total'] or Decimal('0')

    return render(
        request,
        "core/all_dealers.html",
        {
            "dealers": dealers,
            "is_owner": is_owner,
        }
    )

@login_required
def dealer_profile(request, dealer_id):
    memberships = request.user.organization_memberships.select_related("organization")
    if not memberships.exists():
        return redirect("home")

    is_owner = memberships.filter(role=OrganizationMembership.Role.OWNER).exists()
    user_can_manage_dealers = any(m.can_manage_dealers for m in memberships)

    if not is_owner and not user_can_manage_dealers:
        return HttpResponseForbidden("You do not have permission to view dealership profiles.")

    organizations = [m.organization for m in memberships]
    dealer = get_object_or_404(CarDealer, id=dealer_id, organization__in=organizations)

    if request.method == "POST":
        if "mark_paid" in request.POST:
            record_id = request.POST.get("record_id")
            payment_amount_str = request.POST.get("payment_amount", "0")
            record = get_object_or_404(ServiceRecord, id=record_id, dealer=dealer)
            
            try:
                payment_amount = Decimal(payment_amount_str)
            except:
                payment_amount = Decimal("0")
                
            record.dealer_balance -= payment_amount
            if record.dealer_balance <= 0:
                record.dealer_balance = Decimal("0")
                record.is_dealer_paid = True
                
            record.save()
            
            # Create payment log
            DealerPayment.objects.create(
                dealer=dealer,
                amount=payment_amount,
                notes=f"Payment for specific invoice: {record.client_name}"
            )
            
            messages.success(request, f"Payment of ${payment_amount:.2f} applied to invoice for {record.client_name}.")
            return redirect("dealer-profile", dealer_id=dealer.id)
            
        elif "log_bulk_payment" in request.POST:
            payment_amount_str = request.POST.get("bulk_payment_amount", "0")
            notes = request.POST.get("payment_notes", "")
            try:
                payment_amount = Decimal(payment_amount_str)
            except:
                payment_amount = Decimal("0")
                
            if payment_amount > 0:
                # Create payment log
                DealerPayment.objects.create(
                    dealer=dealer,
                    amount=payment_amount,
                    notes=notes
                )
                
                # Apply to oldest unpaid records
                remaining = payment_amount
                unpaid_records = ServiceRecord.objects.filter(dealer=dealer, dealer_balance__gt=0).order_by("created_at")
                
                for rec in unpaid_records:
                    if remaining <= 0:
                        break
                    if rec.dealer_balance <= remaining:
                        remaining -= rec.dealer_balance
                        rec.dealer_balance = Decimal("0")
                        rec.is_dealer_paid = True
                        rec.save()
                    else:
                        rec.dealer_balance -= remaining
                        remaining = Decimal("0")
                        rec.save()
                
                messages.success(request, f"Bulk payment of ${payment_amount:.2f} applied to outstanding invoices.")
            return redirect("dealer-profile", dealer_id=dealer.id)

    # Show all records where dealer is directly set OR client is linked to this dealer
    records = ServiceRecord.objects.filter(
        Q(dealer=dealer) | Q(vehicle__client__dealer=dealer)
    ).select_related("vehicle__client").distinct().order_by("-created_at")

    outstanding_balance = records.filter(is_dealer_paid=False).aggregate(
        total=Sum('dealer_balance')
    )['total'] or Decimal('0')
    
    total_revenue = records.aggregate(total=Sum('service_fee'))['total'] or Decimal('0')
    
    # Analytics
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    monthly_volume = records.filter(created_at__gte=thirty_days_ago).count()
    
    # Service distribution
    service_distribution = list(records.values('service_type').annotate(count=Count('id')).order_by('-count')[:5])
    service_map = dict(ServiceRecord.SERVICE_TYPES)
    for item in service_distribution:
        item['label'] = service_map.get(item['service_type'], item['service_type'])
        
    import json
    chart_labels = [item['label'] for item in service_distribution]
    chart_data = [item['count'] for item in service_distribution]
    
    # Payment Ledger
    payments = DealerPayment.objects.filter(dealer=dealer).order_by("-payment_date", "-created_at")

    return render(
        request,
        "core/dealer_profile.html",
        {
            "dealer": dealer,
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
    memberships = OrganizationMembership.objects.filter(user=request.user)
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
    memberships = OrganizationMembership.objects.filter(user=request.user)
    organizations = Organization.objects.filter(memberships__user=request.user).distinct()
    logs = AutomationLog.objects.filter(organization__in=organizations).select_related('vehicle', 'client', 'organization').order_by('-timestamp')
    return render(request, 'core/all_automation_logs.html', {'logs': logs})

@login_required
@require_POST
def ocr_dl_ajax(request):
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
                        if val.startswith("1") or val.upper().startswith("M"):
                            data[field] = "male"
                        elif val.startswith("2") or val.upper().startswith("F"):
                            data[field] = "female"
                    else:
                        data[field] = val
                        
    elif 'file' in request.FILES:
        # Real OCR using OCR.space Free API
        import requests
        file_obj = request.FILES['file']
        
        try:
            # We use the 'helloworld' key for demonstration, or you can get a free key at ocr.space
            payload = {
                'isOverlayRequired': False,
                'apikey': 'helloworld',
                'language': 'eng',
                'OCREngine': 2, # Engine 2 is better for some documents
            }
            r = requests.post('https://api.ocr.space/parse/image',
                            files={'file': file_obj},
                            data=payload,
                            timeout=15)
            result = r.json()
            
            if result.get('OCRExitCode') == 1:
                text = result.get('ParsedResults')[0].get('ParsedText')
                
                # Simple parser for the extracted text
                # DLs are hard to parse from raw text without a specialized model, 
                # but we can look for keywords.
                
                # Look for DL Number (usually 9 digits or specific patterns)
                dl_match = re.search(r'\b[A-Z0-9]{8,12}\b', text)
                if dl_match: data['driver_license'] = dl_match.group(0)
                
                # Look for DOB (usually MM/DD/YYYY)
                dob_match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
                if dob_match: 
                    d_str = dob_match.group(1)
                    # Convert MM/DD/YYYY to YYYY-MM-DD
                    parts = d_str.split('/')
                    data['dob'] = f"{parts[2]}-{parts[0]}-{parts[1]}"
                
                # Look for names (Usually after "LN" or "FN" or just capitalized lines)
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                for line in lines:
                    if 'NAME' in line.upper() or 'LN' in line.upper():
                        # Heuristic: Name is usually the next word or line
                        pass
                
                # For demo purposes, we will still return some fields if not found, 
                # but indicate they were parsed.
                if not data:
                    data = {"status_msg": "Text extracted but could not be parsed automatically. Please fill manually.", "raw_text": text[:100]}
            else:
                return JsonResponse({"status": "error", "message": "OCR failed: " + str(result.get('ErrorMessage'))})
        except Exception as e:
            return JsonResponse({"status": "error", "message": "OCR Error: " + str(e)})
            
    return JsonResponse({"status": "success", "data": data})
