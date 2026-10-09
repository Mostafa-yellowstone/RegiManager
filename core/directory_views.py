"""Directory space: companies, shared accounts, phone lines, and logins."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .directory_models import DirectoryCredential, DirectoryEntry, DirectoryPhone
from .http import deny_access
from .models import OrganizationMembership, Space
from .space_access import require_space_access
from .views import _get_user_organizations


def _resolve(request, space_id):
    organizations = _get_user_organizations(request)
    card = get_object_or_404(Space, id=space_id, organization__in=organizations, key="directory")
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


def _url(card, entry_id=None):
    url = reverse("inventory-detail", kwargs={"inventory_id": card.id})
    if entry_id:
        return f"{url}?entry={entry_id}"
    return url


def _clean_url(value):
    value = (value or "").strip()
    if value and "://" not in value:
        value = "https://" + value
    return value


def build_directory_space_context(request, card, is_owner, membership):
    query = (request.GET.get("q") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    entries = DirectoryEntry.objects.filter(space=card).prefetch_related("phones", "credentials")
    if kind in dict(DirectoryEntry.Kind.choices):
        entries = entries.filter(kind=kind)
    if query:
        entries = entries.filter(
            Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(email__icontains=query)
            | Q(website__icontains=query)
            | Q(portal_url__icontains=query)
            | Q(notes__icontains=query)
            | Q(phones__label__icontains=query)
            | Q(phones__number__icontains=query)
            | Q(credentials__label__icontains=query)
            | Q(credentials__username__icontains=query)
        ).distinct()
    entry_id = (request.GET.get("entry") or "").strip()
    selected = None
    if entry_id.isdigit():
        selected = DirectoryEntry.objects.filter(space=card, id=int(entry_id)).prefetch_related("phones", "credentials").first()
    return {
        "card": card,
        "is_owner": is_owner,
        "can_manage_directory": bool(is_owner or membership or request.user.is_superuser),
        "entries": list(entries.order_by("name")),
        "entry_count": DirectoryEntry.objects.filter(space=card).count(),
        "selected_entry": selected,
        "directory_query": query,
        "directory_kind": kind,
        "directory_kinds": DirectoryEntry.Kind.choices,
    }


@login_required
@require_POST
def save_directory_entry(request, space_id):
    card, is_owner, membership = _resolve(request, space_id)
    if not (is_owner or membership or request.user.is_superuser):
        deny_access("You cannot edit the directory.")
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, "A name is required.")
        return redirect(_url(card))
    kind = (request.POST.get("kind") or DirectoryEntry.Kind.COMPANY).strip()
    if kind not in dict(DirectoryEntry.Kind.choices):
        kind = DirectoryEntry.Kind.COMPANY
    entry_id = (request.POST.get("entry_id") or "").strip()
    if entry_id.isdigit():
        entry = get_object_or_404(DirectoryEntry, id=int(entry_id), space=card)
    else:
        entry = DirectoryEntry(organization=card.organization, space=card, created_by=request.user)
    entry.kind = kind
    entry.name = name
    entry.category = (request.POST.get("category") or "").strip()
    entry.website = _clean_url(request.POST.get("website"))
    entry.portal_url = _clean_url(request.POST.get("portal_url"))
    entry.email = (request.POST.get("email") or "").strip()
    entry.address = (request.POST.get("address") or "").strip()
    entry.notes = (request.POST.get("notes") or "").strip()
    entry.save()
    messages.success(request, f"{entry.name} saved.")
    return redirect(_url(card, entry.id))


@login_required
@require_POST
def delete_directory_entry(request, entry_id):
    entry = get_object_or_404(DirectoryEntry, id=entry_id)
    card, is_owner, membership = _resolve(request, entry.space_id)
    if not (is_owner or membership or request.user.is_superuser):
        deny_access("You cannot edit the directory.")
    name = entry.name
    entry.delete()
    messages.success(request, f"{name} removed.")
    return redirect(_url(card))


@login_required
@require_POST
def save_directory_phone(request, space_id):
    card, is_owner, membership = _resolve(request, space_id)
    if not (is_owner or membership or request.user.is_superuser):
        deny_access("You cannot edit the directory.")
    entry = get_object_or_404(DirectoryEntry, id=request.POST.get("entry_id"), space=card)
    label = (request.POST.get("label") or "").strip()
    number = (request.POST.get("number") or "").strip()
    if not label or not number:
        messages.error(request, "Phone line needs a name and a number.")
        return redirect(_url(card, entry.id))
    DirectoryPhone.objects.create(
        entry=entry,
        label=label,
        number=number,
        extension=(request.POST.get("extension") or "").strip(),
    )
    messages.success(request, "Phone line added.")
    return redirect(_url(card, entry.id))


@login_required
@require_POST
def delete_directory_phone(request, phone_id):
    phone = get_object_or_404(DirectoryPhone, id=phone_id)
    card, is_owner, membership = _resolve(request, phone.entry.space_id)
    if not (is_owner or membership or request.user.is_superuser):
        deny_access("You cannot edit the directory.")
    entry_id = phone.entry_id
    phone.delete()
    messages.success(request, "Phone line removed.")
    return redirect(_url(card, entry_id))


@login_required
@require_POST
def save_directory_credential(request, space_id):
    card, is_owner, membership = _resolve(request, space_id)
    if not (is_owner or membership or request.user.is_superuser):
        deny_access("You cannot edit the directory.")
    entry = get_object_or_404(DirectoryEntry, id=request.POST.get("entry_id"), space=card)
    label = (request.POST.get("label") or "").strip()
    if not label:
        messages.error(request, "Login needs a name, such as Gmail or portal.")
        return redirect(_url(card, entry.id))
    DirectoryCredential.objects.create(
        entry=entry,
        label=label,
        username=(request.POST.get("username") or "").strip(),
        secret=(request.POST.get("secret") or "").strip(),
        login_url=_clean_url(request.POST.get("login_url")),
        notes=(request.POST.get("notes") or "").strip(),
    )
    messages.success(request, "Login saved.")
    return redirect(_url(card, entry.id))


@login_required
@require_POST
def delete_directory_credential(request, credential_id):
    credential = get_object_or_404(DirectoryCredential, id=credential_id)
    card, is_owner, membership = _resolve(request, credential.entry.space_id)
    if not (is_owner or membership or request.user.is_superuser):
        deny_access("You cannot edit the directory.")
    entry_id = credential.entry_id
    credential.delete()
    messages.success(request, "Login removed.")
    return redirect(_url(card, entry_id))
