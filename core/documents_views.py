"""Views for the Documents space — folder-based document records."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .http import deny_access
from .models import (
    DocumentFolder,
    OrganizationMembership,
    Space,
    SpaceDocumentRecord,
    SpaceDocumentType,
)
from .space_access import require_space_access
from .views import _get_user_organizations

def _documents_url(card, folder_id=None):
    from django.urls import reverse

    url = reverse("inventory-detail", kwargs={"inventory_id": card.id})
    if folder_id:
        url += f"?folder={folder_id}"
    return url


def _redirect_documents(card, folder_id=None, request=None):
    from .policies import redirect_back
    url = _documents_url(card, folder_id)
    if request is not None:
        return redirect_back(request, url)
    return redirect(url)


def _resolve_documents_access(request, space_id=None, card=None):
    organizations = _get_user_organizations(request)
    if card is None:
        card = get_object_or_404(
            Space,
            id=space_id,
            organization__in=organizations,
            key="documents",
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


def _can_manage_documents(is_owner, membership):
    return is_owner or (membership and membership.can_manage_documents)


def _parse_quantity(value, default=0):
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _folder_breadcrumbs(folder):
    crumbs = []
    current = folder
    while current:
        crumbs.insert(0, current)
        current = current.parent
    return crumbs


def _folder_in_space(folder, space):
    if folder is None:
        return True
    return folder.space_id == space.id


def build_documents_space_context(request, card, is_owner, membership):
    active_org = card.organization
    can_manage = _can_manage_documents(is_owner, membership)

    folder_id = request.GET.get("folder", "").strip()
    current_folder = None
    if folder_id.isdigit():
        current_folder = DocumentFolder.objects.filter(
            id=int(folder_id),
            space=card,
        ).first()

    search = request.GET.get("q", "").strip()
    type_filter = request.GET.get("doc_type", "").strip()

    subfolders = DocumentFolder.objects.filter(
        space=card,
        parent=current_folder,
    ).select_related("created_by").order_by("name")

    records_qs = (
        SpaceDocumentRecord.objects.filter(space=card, folder=current_folder)
        .select_related("document_type", "added_by", "folder")
        .order_by("-created_at")
    )
    if search:
        records_qs = records_qs.filter(
            Q(record_number__icontains=search)
            | Q(order_number__icontains=search)
            | Q(range_start__icontains=search)
            | Q(range_end__icontains=search)
            | Q(document_type__name__icontains=search)
            | Q(notes__icontains=search)
        )
    if type_filter.isdigit():
        records_qs = records_qs.filter(document_type_id=int(type_filter))

    folder_totals = records_qs.aggregate(total=Sum("quantity"))
    paginator = Paginator(records_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    document_types = SpaceDocumentType.objects.filter(space=card).order_by("name")
    breadcrumbs = _folder_breadcrumbs(current_folder) if current_folder else []

    stats = {
        "folder_count": DocumentFolder.objects.filter(space=card).count(),
        "record_count": SpaceDocumentRecord.objects.filter(space=card).count(),
        "type_count": document_types.count(),
        "folder_record_count": records_qs.count(),
        "folder_total_quantity": folder_totals.get("total") or 0,
    }

    return {
        "card": card,
        "active_org": active_org,
        "is_owner": is_owner,
        "can_manage_documents": can_manage,
        "current_folder": current_folder,
        "breadcrumbs": breadcrumbs,
        "subfolders": subfolders,
        "records": page_obj,
        "page_obj": page_obj,
        "document_types": document_types,
        "search": search,
        "type_filter": type_filter,
        "stats": stats,
    }


@login_required
@require_POST
def add_document_folder(request, space_id):
    card, is_owner, membership = _resolve_documents_access(request, space_id=space_id)
    if not _can_manage_documents(is_owner, membership):
        deny_access("You do not have permission to manage documents.")

    name = request.POST.get("name", "").strip()
    parent_id = request.POST.get("parent_id", "").strip()
    if not name:
        messages.error(request, "Folder name is required.")
        return _redirect_documents(card, parent_id if parent_id.isdigit() else None, request=request)

    parent = None
    if parent_id.isdigit():
        parent = get_object_or_404(DocumentFolder, id=int(parent_id), space=card)

    if DocumentFolder.objects.filter(space=card, parent=parent, name__iexact=name).exists():
        messages.error(request, f"A folder named “{name}” already exists here.")
        return _redirect_documents(card, parent.id if parent else None, request=request)

    DocumentFolder.objects.create(
        space=card,
        organization=card.organization,
        parent=parent,
        name=name,
        created_by=request.user,
    )
    messages.success(request, f"Folder “{name}” created.")
    return _redirect_documents(card, parent.id if parent else None, request=request)


@login_required
@require_POST
def edit_document_folder(request, folder_id):
    folder = get_object_or_404(DocumentFolder, id=folder_id)
    card, is_owner, membership = _resolve_documents_access(request, card=folder.space)
    if not _can_manage_documents(is_owner, membership):
        deny_access("You do not have permission to manage documents.")

    name = request.POST.get("name", "").strip()
    redirect_folder_id = request.POST.get("redirect_folder_id", "").strip()
    if redirect_folder_id.isdigit():
        redirect_to = int(redirect_folder_id)
    else:
        redirect_to = folder.id

    if not name:
        messages.error(request, "Folder name cannot be empty.")
        return _redirect_documents(card, redirect_to, request=request)

    if (
        DocumentFolder.objects.filter(space=card, parent=folder.parent, name__iexact=name)
        .exclude(pk=folder.pk)
        .exists()
    ):
        messages.error(request, f"A folder named “{name}” already exists here.")
        return _redirect_documents(card, redirect_to, request=request)

    old_name = folder.name
    folder.name = name
    folder.save(update_fields=["name"])
    messages.success(request, f"Folder renamed from “{old_name}” to “{name}”.")
    return _redirect_documents(card, redirect_to, request=request)


@login_required
@require_POST
def add_document_type(request, space_id):
    card, is_owner, membership = _resolve_documents_access(request, space_id=space_id)
    if not _can_manage_documents(is_owner, membership):
        deny_access("You do not have permission to manage documents.")

    name = request.POST.get("name", "").strip()
    folder_id = request.POST.get("folder_id", "").strip()
    if not name:
        messages.error(request, "Document type name is required.")
        return _redirect_documents(card, folder_id if folder_id.isdigit() else None, request=request)

    if SpaceDocumentType.objects.filter(space=card, name__iexact=name).exists():
        messages.error(request, f"Document type “{name}” already exists.")
        return _redirect_documents(card, folder_id if folder_id.isdigit() else None, request=request)

    SpaceDocumentType.objects.create(
        space=card,
        organization=card.organization,
        name=name,
    )
    messages.success(request, f"Document type “{name}” added.")
    return _redirect_documents(card, folder_id if folder_id.isdigit() else None, request=request)


@login_required
@require_POST
def edit_document_type(request, type_id):
    doc_type = get_object_or_404(SpaceDocumentType, id=type_id)
    card, is_owner, membership = _resolve_documents_access(request, card=doc_type.space)
    if not _can_manage_documents(is_owner, membership):
        deny_access("You do not have permission to manage documents.")

    name = request.POST.get("name", "").strip()
    folder_id = request.POST.get("folder_id", "").strip()
    if not name:
        messages.error(request, "Document type name cannot be empty.")
        return _redirect_documents(card, folder_id if folder_id.isdigit() else None, request=request)

    if (
        SpaceDocumentType.objects.filter(space=card, name__iexact=name)
        .exclude(pk=doc_type.pk)
        .exists()
    ):
        messages.error(request, f"Document type “{name}” already exists.")
        return _redirect_documents(card, folder_id if folder_id.isdigit() else None, request=request)

    old_name = doc_type.name
    doc_type.name = name
    doc_type.save(update_fields=["name"])
    messages.success(request, f"Document type renamed from “{old_name}” to “{name}”.")
    return _redirect_documents(card, folder_id if folder_id.isdigit() else None, request=request)


@login_required
@require_POST
def add_document_record(request, space_id):
    card, is_owner, membership = _resolve_documents_access(request, space_id=space_id)
    if not _can_manage_documents(is_owner, membership):
        deny_access("You do not have permission to manage documents.")

    folder_id = request.POST.get("folder_id", "").strip()
    doc_type_id = request.POST.get("document_type", "").strip()
    order_number = request.POST.get("order_number", "").strip()
    range_start = request.POST.get("range_start", "").strip()
    range_end = request.POST.get("range_end", "").strip()
    quantity = _parse_quantity(request.POST.get("quantity"))
    notes = request.POST.get("notes", "").strip()
    uploaded_file = request.FILES.get("file")

    folder = None
    if folder_id.isdigit():
        folder = get_object_or_404(DocumentFolder, id=int(folder_id), space=card)

    if not doc_type_id.isdigit():
        messages.error(request, "Select a document type.")
        return _redirect_documents(card, folder.id if folder else None, request=request)

    doc_type = get_object_or_404(SpaceDocumentType, id=int(doc_type_id), space=card)

    SpaceDocumentRecord.objects.create(
        space=card,
        organization=card.organization,
        folder=folder,
        document_type=doc_type,
        order_number=order_number,
        range_start=range_start,
        range_end=range_end,
        quantity=quantity,
        notes=notes,
        file=uploaded_file,
        added_by=request.user,
    )
    messages.success(request, "Document record saved.")
    return _redirect_documents(card, folder.id if folder else None, request=request)


@login_required
@require_POST
def delete_document_record(request, record_id):
    record = get_object_or_404(SpaceDocumentRecord, id=record_id)
    card, is_owner, membership = _resolve_documents_access(request, card=record.space)
    if not _can_manage_documents(is_owner, membership):
        deny_access("You do not have permission to manage documents.")

    folder_id = record.folder_id
    record_number = record.record_number
    if record.file:
        record.file.delete(save=False)
    record.delete()
    messages.success(request, f"Record {record_number} deleted.")
    return _redirect_documents(card, folder_id, request=request)
