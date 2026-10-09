"""Directory space: companies, shared accounts, phone lines, and logins."""

import re
from difflib import SequenceMatcher

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import FloatField, Max, Q, Value
from django.db.models.functions import Coalesce, Greatest
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .directory_models import DirectoryCredential, DirectoryEntry, DirectoryNote, DirectoryPhone, format_us_phone
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


def _entry_base(card, kind):
    entries = DirectoryEntry.objects.filter(space=card).prefetch_related("phones", "credentials", "note_items")
    if kind in dict(DirectoryEntry.Kind.choices):
        entries = entries.filter(kind=kind)
    return entries


def _digits(value):
    return re.sub(r"\D", "", value or "")


def _direct_rank(entry, query):
    name = (entry.name or "").lower()
    email = (entry.email or "").lower()
    needle = query.lower()
    if name == needle or email == needle:
        return 0
    if name.startswith(needle) or email.startswith(needle):
        return 1
    if needle in name or needle in email:
        return 2
    return 3


def _near_score(entry, query):
    needle = query.lower()
    candidates = [entry.name or ""]
    candidates.extend((entry.name or "").split())
    if entry.email:
        candidates.append(entry.email)
        candidates.append(entry.email.split("@")[0])
    for phone in entry.phones.all():
        if phone.number:
            candidates.append(phone.number)
            candidates.append(_digits(phone.number))
    digit_needle = _digits(query)
    best = 0
    for candidate in candidates:
        text = (candidate or "").lower()
        if not text:
            continue
        best = max(best, SequenceMatcher(None, needle, text).ratio())
        if digit_needle and len(digit_needle) >= 3:
            best = max(best, SequenceMatcher(None, digit_needle, _digits(text)).ratio())
    return best


def _postgres_near(base, query):
    from django.contrib.postgres.search import TrigramSimilarity, TrigramWordSimilarity

    with connection.cursor() as cursor:
        cursor.execute("SET pg_trgm.similarity_threshold = 0.18")
        cursor.execute("SET pg_trgm.word_similarity_threshold = 0.3")
    return list(
        base.filter(
            Q(name__trigram_word_similar=query)
            | Q(email__trigram_similar=query)
            | Q(phones__number__trigram_similar=query)
        )
        .annotate(
            similarity=Greatest(
                TrigramWordSimilarity(query, "name"),
                TrigramSimilarity("email", query),
                Coalesce(Max(TrigramSimilarity("phones__number", query)), Value(0.0), output_field=FloatField()),
            )
        )
        .order_by("-similarity", "name")[:12]
    )


def _python_near(base, query):
    scored = []
    for entry in base:
        score = _near_score(entry, query)
        if score >= 0.55:
            scored.append((-score, entry.name.lower(), entry))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored[:12]]


def search_directory_entries(card, query, kind):
    """Return (entries, mode). Mode is all, exact, near, or none."""
    query = (query or "").strip()
    base = _entry_base(card, kind)
    if not query:
        return list(base.order_by("name")), "all"
    from .text_search import collapse_text, matching_compact_queryset, text_search_q

    query = collapse_text(query)
    digits = _digits(query)
    clauses = text_search_q(
        query,
        ["name", "email", "phones__number", "phones__label", "website", "portal_url", "category"],
    )
    compact_ids = matching_compact_queryset(base, query, ["name", "email", "category"]).values_list("id", flat=True)
    clauses |= Q(id__in=compact_ids)
    if len(digits) >= 3:
        clauses |= Q(phones__number__icontains=digits)
        phone_rows = DirectoryPhone.objects.filter(entry__in=base).only("entry_id", "number")
        digit_ids = [phone.entry_id for phone in phone_rows if digits in _digits(phone.number)]
        if digit_ids:
            clauses |= Q(id__in=digit_ids)
    matched_ids = list(base.filter(clauses).values_list("id", flat=True).distinct())
    if matched_ids:
        rows = list(DirectoryEntry.objects.filter(id__in=matched_ids).prefetch_related("phones", "credentials", "note_items"))
        rows.sort(key=lambda entry: (_direct_rank(entry, query), entry.name.lower()))
        return rows[:24], "exact"
    rows = []
    if connection.vendor == "postgresql" and len(query) >= 2:
        rows = _postgres_near(base, query)
    if not rows and len(query) >= 2:
        rows = _python_near(base, query)
    if rows:
        return rows, "near"
    return [], "none"


def directory_search_payload(card, entries, mode, query):
    return {
        "mode": mode,
        "query": query,
        "count": len(entries),
        "results": [
            {
                "id": entry.id,
                "name": entry.name,
                "phones": [phone.formatted_number() for phone in entry.phones.all() if phone.number],
                "email": entry.email,
                "url": f"?entry={entry.id}",
            }
            for entry in entries
        ],
    }


def build_directory_space_context(request, card, is_owner, membership):
    query = (request.GET.get("q") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    entries, search_mode = search_directory_entries(card, query, kind)
    entry_id = (request.GET.get("entry") or "").strip()
    selected = None
    if entry_id.isdigit():
        selected = DirectoryEntry.objects.filter(space=card, id=int(entry_id)).prefetch_related("phones", "credentials", "note_items").first()
    editing = request.GET.get("edit") == "1" and selected is not None
    creating = request.GET.get("new") == "1" and selected is None
    return {
        "card": card,
        "is_owner": is_owner,
        "can_manage_directory": bool(is_owner or membership or request.user.is_superuser),
        "entries": entries,
        "directory_search_mode": search_mode,
        "entry_count": DirectoryEntry.objects.filter(space=card).count(),
        "selected_entry": selected,
        "directory_query": query,
        "directory_kind": kind,
        "directory_kinds": DirectoryEntry.Kind.choices,
        "directory_form_kinds": (
            (DirectoryEntry.Kind.COMPANY, "Company"),
            (DirectoryEntry.Kind.LOGIN, "Login credentials"),
            (DirectoryEntry.Kind.SHARED_ACCOUNT, "Shared account"),
        ),
        "directory_creating": creating,
        "directory_editing": editing,
    }


@login_required
@require_GET
def directory_search(request, space_id):
    card, _is_owner, _membership = _resolve(request, space_id)
    query = (request.GET.get("q") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    entries, mode = search_directory_entries(card, query, kind)
    return JsonResponse(directory_search_payload(card, entries, mode, query))


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
    entry.save()
    _save_directory_notes(entry, request)
    if entry.kind == DirectoryEntry.Kind.COMPANY:
        _save_company_phones(entry, request)
    elif entry.kind in (DirectoryEntry.Kind.LOGIN, DirectoryEntry.Kind.SHARED_ACCOUNT):
        _save_account_login(entry, request)
    messages.success(request, f"{entry.name} saved.")
    return redirect(_url(card, entry.id))


def _save_directory_notes(entry, request):
    titles = request.POST.getlist("note_title")
    bodies = request.POST.getlist("note_body")
    note_ids = request.POST.getlist("note_id")
    if "note_title" not in request.POST and "note_body" not in request.POST:
        return
    kept = []
    for index, raw_title in enumerate(titles):
        title = (raw_title or "").strip()
        body = (bodies[index] if index < len(bodies) else "").strip()
        note_id = (note_ids[index] if index < len(note_ids) else "").strip()
        if not title and not body:
            continue
        if not title:
            title = f"Note {index + 1}"
        note = DirectoryNote.objects.filter(id=int(note_id), entry=entry).first() if note_id.isdigit() else None
        if note is None:
            note = DirectoryNote(entry=entry)
        note.title = title
        note.body = body
        note.position = len(kept)
        note.save()
        kept.append(note.id)
    DirectoryNote.objects.filter(entry=entry).exclude(id__in=kept).delete()
    if entry.notes:
        entry.notes = ""
        entry.save(update_fields=["notes"])


def _save_company_phones(entry, request):
    labels = request.POST.getlist("phone_label")
    numbers = request.POST.getlist("phone_number")
    extensions = request.POST.getlist("phone_extension")
    phone_ids = request.POST.getlist("phone_id")
    for index, number in enumerate(numbers):
        label = (labels[index] if index < len(labels) else "").strip()
        number = format_us_phone(number)
        extension = (extensions[index] if index < len(extensions) else "").strip()
        phone_id = (phone_ids[index] if index < len(phone_ids) else "").strip()
        if phone_id.isdigit():
            phone = DirectoryPhone.objects.filter(id=int(phone_id), entry=entry).first()
            if not phone:
                continue
            if label and number:
                phone.label = label
                phone.number = number
                phone.extension = extension
                phone.save()
            continue
        if label and number:
            DirectoryPhone.objects.create(entry=entry, label=label, number=number, extension=extension)


def _save_account_login(entry, request):
    username = (request.POST.get("username") or "").strip()
    secret = (request.POST.get("secret") or "").strip()
    login_url = _clean_url(request.POST.get("login_url"))
    notes = (request.POST.get("credential_notes") or "").strip()
    credential = entry.credentials.first()
    if credential is None:
        if not (username or secret or login_url or notes):
            return
        DirectoryCredential.objects.create(
            entry=entry,
            label=entry.name,
            username=username,
            secret=secret,
            login_url=login_url,
            notes=notes,
        )
        return
    credential.label = entry.name
    credential.username = username
    if secret:
        credential.secret = secret
    credential.login_url = login_url
    credential.notes = notes
    credential.save()


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
    number = format_us_phone(request.POST.get("number"))
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
