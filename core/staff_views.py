"""Views for the Staff HR space."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .http import deny_access
from .models import OrganizationMembership, Space, StaffDocument, StaffEmployee
from .space_access import require_space_access
from .space_important_docs import important_docs_context, user_can_manage_space_docs
from .staff_crm import enrich_employee, filter_employees, staff_dashboard_stats
from .views import _get_user_organizations


def _resolve_staff_access(request, space_id=None, card=None):
    organizations = _get_user_organizations(request)
    if card is None:
        card = get_object_or_404(
            Space,
            id=space_id,
            organization__in=organizations,
            key="staff",
        )

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


def _user_can_manage_staff(is_owner, membership):
    return is_owner or (membership and membership.can_manage_staff)


def _staff_url(card, tab=None, employee_id=None):
    from django.urls import reverse

    url = reverse("inventory-detail", kwargs={"inventory_id": card.id})
    params = []
    if tab:
        params.append(f"tab={tab}")
    if employee_id:
        params.append(f"employee={employee_id}")
    if params:
        url += "?" + "&".join(params)
    return url


def _redirect_staff(card, tab=None, employee_id=None, request=None):
    from .policies import redirect_back

    url = _staff_url(card, tab=tab, employee_id=employee_id)
    if request is not None:
        return redirect_back(request, url)
    return redirect(url)


def build_staff_space_context(request, card, is_owner, membership):
    active_org = card.organization
    stats = staff_dashboard_stats(card)
    search = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    employee_id = request.GET.get("employee", "").strip()

    employees_qs = (
        StaffEmployee.objects.filter(space=card)
        .annotate(annotated_doc_count=Count("documents"))
        .select_related("linked_user", "created_by")
        .order_by("last_name", "first_name")
    )
    employees_qs = filter_employees(employees_qs, search=search, status=status_filter)
    page = Paginator(employees_qs, 24).get_page(request.GET.get("page", 1))
    for emp in page:
        enrich_employee(emp)

    selected = None
    selected_docs = []
    if employee_id.isdigit():
        selected = (
            StaffEmployee.objects.filter(space=card, id=int(employee_id))
            .select_related("linked_user")
            .first()
        )
        if selected:
            enrich_employee(selected)
            selected_docs = list(selected.documents.select_related("uploaded_by"))

    can_manage = _user_can_manage_staff(is_owner, membership)
    docs_ctx = important_docs_context(
        card,
        can_manage=user_can_manage_space_docs(is_owner, membership, card),
        accent="#4f46e5",
    )

    return {
        "card": card,
        "active_org": active_org,
        "is_owner": is_owner,
        "can_manage_staff": can_manage,
        "stats": stats,
        "employees_page": page,
        "employees": page,
        "selected_employee": selected,
        "selected_docs": selected_docs,
        "active_tab": request.GET.get("tab", "directory"),
        "search": search,
        "status_filter": status_filter,
        "status_choices": StaffEmployee.StatusChoices.choices,
        "doc_categories": StaffDocument.Category.choices,
        **docs_ctx,
    }


def _parse_date(value):
    from datetime import datetime

    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@login_required
@require_POST
def save_staff_employee(request, space_id):
    card, is_owner, membership = _resolve_staff_access(request, space_id=space_id)
    if not _user_can_manage_staff(is_owner, membership):
        deny_access("You do not have permission to manage staff profiles.")

    employee_id = (request.POST.get("employee_id") or "").strip()
    first_name = (request.POST.get("first_name") or "").strip()
    last_name = (request.POST.get("last_name") or "").strip()
    if not first_name or not last_name:
        messages.error(request, "First and last name are required.")
        return _redirect_staff(card, tab="directory", request=request)

    status = request.POST.get("employment_status", StaffEmployee.StatusChoices.ACTIVE)
    if status not in dict(StaffEmployee.StatusChoices.choices):
        status = StaffEmployee.StatusChoices.ACTIVE

    fields = {
        "first_name": first_name,
        "last_name": last_name,
        "email": (request.POST.get("email") or "").strip(),
        "phone": (request.POST.get("phone") or "").strip(),
        "job_title": (request.POST.get("job_title") or "").strip(),
        "department": (request.POST.get("department") or "").strip(),
        "employment_status": status,
        "hire_date": _parse_date(request.POST.get("hire_date")),
        "date_of_birth": _parse_date(request.POST.get("date_of_birth")),
        "address": (request.POST.get("address") or "").strip(),
        "city": (request.POST.get("city") or "").strip(),
        "state": (request.POST.get("state") or "").strip(),
        "zip_code": (request.POST.get("zip_code") or "").strip(),
        "emergency_contact_name": (request.POST.get("emergency_contact_name") or "").strip(),
        "emergency_contact_phone": (request.POST.get("emergency_contact_phone") or "").strip(),
        "notes": (request.POST.get("notes") or "").strip(),
    }

    if employee_id:
        employee = get_object_or_404(
            StaffEmployee, id=employee_id, organization=card.organization, space=card
        )
        for key, value in fields.items():
            setattr(employee, key, value)
        if request.FILES.get("photo"):
            employee.photo = request.FILES["photo"]
        if request.POST.get("clear_photo") == "1" and employee.photo:
            employee.photo.delete(save=False)
            employee.photo = None
        employee.save()
        messages.success(request, f"Updated {employee.full_name}.")
        return _redirect_staff(
            card, tab="directory", employee_id=employee.id, request=request
        )

    employee = StaffEmployee.objects.create(
        organization=card.organization,
        space=card,
        created_by=request.user,
        **fields,
    )
    if request.FILES.get("photo"):
        employee.photo = request.FILES["photo"]
        employee.save(update_fields=["photo"])
    messages.success(request, f"Added {employee.full_name} to Staff.")
    return _redirect_staff(card, tab="directory", employee_id=employee.id, request=request)


@login_required
@require_POST
def delete_staff_employee(request, employee_id):
    employee = get_object_or_404(
        StaffEmployee.objects.select_related("space"), id=employee_id
    )
    card, is_owner, membership = _resolve_staff_access(request, card=employee.space)
    if not _user_can_manage_staff(is_owner, membership):
        deny_access("You do not have permission to delete staff profiles.")

    name = employee.full_name
    if employee.photo:
        employee.photo.delete(save=False)
    employee.delete()
    messages.success(request, f"Removed {name} from Staff.")
    return _redirect_staff(card, tab="directory", request=request)


@login_required
@require_POST
def upload_staff_document(request, employee_id):
    employee = get_object_or_404(
        StaffEmployee.objects.select_related("space"), id=employee_id
    )
    card, is_owner, membership = _resolve_staff_access(request, card=employee.space)
    if not _user_can_manage_staff(is_owner, membership):
        deny_access("You do not have permission to upload staff documents.")

    title = (request.POST.get("title") or "").strip()
    category = (request.POST.get("category") or "").strip()
    uploaded = request.FILES.get("file")
    if not title or not uploaded:
        messages.error(request, "Title and file are required.")
        return _redirect_staff(
            card, tab="directory", employee_id=employee.id, request=request
        )
    if category not in dict(StaffDocument.Category.choices):
        category = StaffDocument.Category.OTHER

    StaffDocument.objects.create(
        organization=card.organization,
        employee=employee,
        title=title,
        category=category,
        file=uploaded,
        notes=(request.POST.get("notes") or "").strip(),
        expires_at=_parse_date(request.POST.get("expires_at")),
        uploaded_by=request.user,
    )
    messages.success(request, f"Uploaded “{title}” for {employee.full_name}.")
    return _redirect_staff(
        card, tab="directory", employee_id=employee.id, request=request
    )


@login_required
@require_POST
def delete_staff_document(request, document_id):
    doc = get_object_or_404(
        StaffDocument.objects.select_related("employee", "employee__space"),
        id=document_id,
    )
    card, is_owner, membership = _resolve_staff_access(
        request, card=doc.employee.space
    )
    if not _user_can_manage_staff(is_owner, membership):
        deny_access("You do not have permission to delete staff documents.")

    employee_id = doc.employee_id
    title = doc.title
    if doc.file:
        doc.file.delete(save=False)
    doc.delete()
    messages.success(request, f"Deleted “{title}”.")
    return _redirect_staff(
        card, tab="directory", employee_id=employee_id, request=request
    )
