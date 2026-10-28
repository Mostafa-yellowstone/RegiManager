import os
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.dateparse import parse_date

from core.models import (
    ServiceDocument,
    OrganizationMembership,
    SpaceDocumentRecord,
    InsurancePolicyDocument,
)
from core.views import _get_user_organizations


@login_required
def dashboard_documents_crm(request):
    """
    Dedicated CRM Document Search & Advanced Filter Section.
    Allows searching files/custom names (e.g. 'correction'), filtering by date,
    agent, document type, source space, and preserving filter state across pagination.
    """
    user = request.user
    organizations = _get_user_organizations(request)
    memberships = OrganizationMembership.objects.filter(
        user=user,
        is_active=True,
        organization__is_active=True,
        organization__in=organizations,
    ).select_related("organization")

    is_owner = memberships.filter(role=OrganizationMembership.Role.OWNER).exists()

    # Query params
    search_q = request.GET.get("q", "").strip()
    doc_type = request.GET.get("doc_type", "").strip()
    agent_id = request.GET.get("agent", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    file_ext = request.GET.get("file_ext", "").strip()
    sort_by = request.GET.get("sort", "-uploaded_at").strip()
    page_num = request.GET.get("page", 1)

    # Base QuerySet restricted to user's authorized organizations
    # ServiceDocument links to service_record (which has organization & handled_by) OR vehicle (which has client.organization)
    org_filter = Q(service_record__organization__in=organizations) | Q(vehicle__client__organization__in=organizations)
    docs_qs = ServiceDocument.objects.filter(org_filter).select_related(
        "service_record",
        "service_record__organization",
        "service_record__handled_by",
        "vehicle",
        "vehicle__client",
        "vehicle__client__organization",
    )

    # 1. Search Query (matches custom_name, file name, client name, plate, vin, receipt number)
    if search_q:
        docs_qs = docs_qs.filter(
            Q(custom_name__icontains=search_q)
            | Q(file__icontains=search_q)
            | Q(service_record__client_name__icontains=search_q)
            | Q(vehicle__client__first_name__icontains=search_q)
            | Q(vehicle__client__last_name__icontains=search_q)
            | Q(vehicle__client__business_name__icontains=search_q)
            | Q(service_record__receipt_number__icontains=search_q)
            | Q(service_record__plate_number__icontains=search_q)
            | Q(vehicle__plate_number__icontains=search_q)
            | Q(service_record__vin__icontains=search_q)
            | Q(vehicle__vin__icontains=search_q)
        )

    # 2. Document Type Filter
    if doc_type:
        docs_qs = docs_qs.filter(document_type=doc_type)

    # 3. Agent Filter
    if agent_id:
        if agent_id.isdigit():
            docs_qs = docs_qs.filter(service_record__handled_by_id=int(agent_id))

    # 4. Date Range Filter
    if date_from:
        parsed_from = parse_date(date_from)
        if parsed_from:
            docs_qs = docs_qs.filter(uploaded_at__date__gte=parsed_from)

    if date_to:
        parsed_to = parse_date(date_to)
        if parsed_to:
            docs_qs = docs_qs.filter(uploaded_at__date__lte=parsed_to)

    # 5. File Extension Filter (e.g. pdf, png, jpg)
    if file_ext:
        clean_ext = file_ext.lower().replace(".", "")
        docs_qs = docs_qs.filter(file__iendswith=f".{clean_ext}")

    # Sorting
    allowed_sorts = {
        "-uploaded_at": "-uploaded_at",
        "uploaded_at": "uploaded_at",
        "custom_name": "custom_name",
        "-custom_name": "-custom_name",
        "doc_type": "document_type",
    }
    docs_qs = docs_qs.order_by(allowed_sorts.get(sort_by, "-uploaded_at"))

    # Total counts and aggregates
    total_matching_count = docs_qs.count()

    # Pagination: 15 per page
    paginator = Paginator(docs_qs, 15)
    page_obj = paginator.get_page(page_num)

    # Preserve all filter parameters for pagination links
    query_params = request.GET.copy()
    if "page" in query_params:
        query_params.pop("page")
    preserved_query_string = query_params.urlencode()

    # Agents list for dropdown
    agent_memberships = OrganizationMembership.objects.filter(
        organization__in=organizations,
        is_active=True,
    ).select_related("user").order_by("user__first_name", "user__username")
    
    unique_agents = []
    seen_user_ids = set()
    for m in agent_memberships:
        if m.user_id not in seen_user_ids:
            seen_user_ids.add(m.user_id)
            unique_agents.append(m.user)

    # Document types options
    doc_types = ServiceDocument.DOCUMENT_TYPES

    context = {
        "page_obj": page_obj,
        "documents": page_obj.object_list,
        "total_count": total_matching_count,
        "preserved_query_string": preserved_query_string,
        "search_q": search_q,
        "doc_type": doc_type,
        "agent_id": agent_id,
        "date_from": date_from,
        "date_to": date_to,
        "file_ext": file_ext,
        "sort_by": sort_by,
        "agents": unique_agents,
        "doc_types": doc_types,
        "is_owner": is_owner,
    }
    return render(request, "core/dashboard_documents_crm.html", context)
