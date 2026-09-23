"""Shared space-level important documents (contracts, licenses, agreements)."""

from __future__ import annotations

import mimetypes
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST

from .http import deny_access
from .models import OrganizationMembership, Space, SpaceImportantDocument
from .views import _get_user_organizations

# Spaces that host the shared Important Documents UI and their manage flags.
SPACE_DOC_PERMISSION_FLAGS = {
    "motorclub": "can_deal_with_motorclub",
    "defense_driving": "can_deal_with_defense_driving",
}


def space_supports_important_docs(space: Space) -> bool:
    return space.key in SPACE_DOC_PERMISSION_FLAGS


def user_can_manage_space_docs(is_owner, membership, space: Space) -> bool:
    if is_owner:
        return True
    if not membership:
        return False
    flag = SPACE_DOC_PERMISSION_FLAGS.get(space.key)
    if not flag:
        return False
    return bool(getattr(membership, flag, False))


def list_important_documents(space: Space):
    return list(
        SpaceImportantDocument.objects.filter(space=space)
        .select_related("uploaded_by")
        .order_by("-created_at")
    )


def important_docs_context(space: Space, *, can_manage: bool, accent: str | None = None):
    docs = list_important_documents(space)
    return {
        "important_docs": docs,
        "important_docs_count": len(docs),
        "important_doc_categories": SpaceImportantDocument.Category.choices,
        "can_manage_important_docs": can_manage,
        "important_docs_accent": accent or "#2563eb",
        "important_docs_space": space,
    }


def _resolve_space_docs_access(request, space_id):
    organizations = _get_user_organizations(request)
    space = get_object_or_404(
        Space,
        id=space_id,
        organization__in=organizations,
    )
    if not space_supports_important_docs(space):
        deny_access("Important documents are not available for this space.")

    if request.user.is_superuser:
        return space, True, None

    membership = OrganizationMembership.objects.filter(
        user=request.user,
        organization=space.organization,
        is_active=True,
        organization__is_active=True,
    ).first()
    if not membership:
        deny_access("Access denied.")

    is_owner = membership.role == OrganizationMembership.Role.OWNER
    from .space_access import require_space_access

    require_space_access(membership, space)
    return space, is_owner, membership


def _space_detail_url(space, tab="documents"):
    from django.urls import reverse

    return reverse("inventory-detail", kwargs={"inventory_id": space.id}) + f"?tab={tab}"


def _redirect_to_docs(request, space):
    from .policies import redirect_back

    return redirect_back(request, _space_detail_url(space, tab="documents"))


@login_required
@require_POST
def upload_space_important_document(request, space_id):
    space, is_owner, membership = _resolve_space_docs_access(request, space_id)
    if not user_can_manage_space_docs(is_owner, membership, space):
        deny_access("You do not have permission to upload documents for this space.")

    title = (request.POST.get("title") or "").strip()
    category = (request.POST.get("category") or "").strip()
    notes = (request.POST.get("notes") or "").strip()
    uploaded = request.FILES.get("file")

    if not title:
        messages.error(request, "Document title is required.")
        return _redirect_to_docs(request, space)
    if not uploaded:
        messages.error(request, "Please choose a file to upload.")
        return _redirect_to_docs(request, space)
    if category not in dict(SpaceImportantDocument.Category.choices):
        category = SpaceImportantDocument.Category.OTHER

    SpaceImportantDocument.objects.create(
        space=space,
        organization=space.organization,
        title=title,
        category=category,
        file=uploaded,
        notes=notes,
        uploaded_by=request.user,
    )
    messages.success(request, f"Uploaded “{title}”.")
    return _redirect_to_docs(request, space)


@login_required
@require_GET
def download_space_important_document(request, document_id):
    organizations = _get_user_organizations(request)
    doc = get_object_or_404(
        SpaceImportantDocument.objects.select_related("space", "organization"),
        id=document_id,
        organization__in=organizations,
    )
    _space, _is_owner, _membership = _resolve_space_docs_access(request, doc.space_id)

    if not doc.file:
        raise Http404("File not found.")

    filename = os.path.basename(doc.file.name)
    content_type, _ = mimetypes.guess_type(filename)
    as_attachment = request.GET.get("download") == "1"
    response = FileResponse(
        doc.file.open("rb"),
        as_attachment=as_attachment,
        filename=filename,
        content_type=content_type or "application/octet-stream",
    )
    return response


@login_required
@require_POST
def delete_space_important_document(request, document_id):
    organizations = _get_user_organizations(request)
    doc = get_object_or_404(
        SpaceImportantDocument.objects.select_related("space"),
        id=document_id,
        organization__in=organizations,
    )
    space, is_owner, membership = _resolve_space_docs_access(request, doc.space_id)
    if not user_can_manage_space_docs(is_owner, membership, space):
        deny_access("You do not have permission to delete documents for this space.")

    title = doc.title
    if doc.file:
        doc.file.delete(save=False)
    doc.delete()
    messages.success(request, f"Deleted “{title}”.")
    return _redirect_to_docs(request, space)
