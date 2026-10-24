"""Renewals page of the Insurance area: card list, card detail, actions, and office settings."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .http import deny_access
from .insurance_area_views import _insurance_access, _render_page
from .insurance_producers import add_months
from .insurance_renewals import (
    EXPIRING_BUCKETS,
    assignable_users,
    close_lost,
    days_left,
    default_terms,
    fill_template,
    is_renewal_manager,
    link_existing,
    linkable_policies,
    log_event,
    message_values,
    record_contact,
    renew,
    renewal_history,
    reminder_due,
    reopen,
    retention,
    scoped_cards,
    send_renewal_email,
    settings_for,
    sync_renewals,
    terms_from_post,
)
from .insurance_renewal_models import InsuranceRenewal, InsuranceRenewalEvent

Stage = InsuranceRenewal.Stage
Event = InsuranceRenewalEvent.Kind

VIEWS = ("open", "closed", "retention")
WHEN_CHOICES = ("overdue",) + tuple(str(d) for d in EXPIRING_BUCKETS) + ("all",)
SNOOZE_CHOICES = (1, 3, 7, 14)
CONTACT_KINDS = {Event.CALL, Event.TEXT, Event.EMAIL, Event.NOTE}


def _can_work(user, membership, card) -> bool:
    return is_renewal_manager(user, membership) or card.assigned_to_id in (None, user.id)


def _card_for(request, renewal_id, *, work=True):
    organization, membership, _is_owner, _banking = _insurance_access(request)
    card = get_object_or_404(
        InsuranceRenewal.objects.select_related(
            "policy", "policy__client", "policy__insurance_company", "assigned_to", "new_policy", "organization"
        ),
        id=renewal_id,
        organization=organization,
    )
    if work and not _can_work(request.user, membership, card):
        deny_access("This renewal is assigned to another agent.")
    return card, membership


def _detail_url(card) -> str:
    return reverse("insurance-renewal-detail", args=[card.id])


def _back(request, card):
    target = (request.POST.get("next") or "").strip()
    if target.startswith("/insurance/") and not target.startswith("//"):
        return redirect(target)
    return redirect(_detail_url(card))


@login_required
def renewals_page(request):
    def extra(organization, membership):
        today = timezone.localdate()
        sync_renewals(organization, today=today)
        manager = is_renewal_manager(request.user, membership)
        view = request.GET.get("view") if request.GET.get("view") in VIEWS else "open"
        when = request.GET.get("when") if request.GET.get("when") in WHEN_CHOICES else "all"
        stage = request.GET.get("stage") or ""
        agent = (request.GET.get("agent") or "").strip()
        if manager:
            mine = agent == "me"
        else:
            mine = request.GET.get("scope", "mine") != "all"
        q = " ".join((request.GET.get("q") or "").split())[:80]

        cards = scoped_cards(organization, request.user, mine=mine)
        if manager and agent.isdigit():
            cards = cards.filter(assigned_to_id=int(agent))
        elif manager and agent == "none":
            cards = cards.filter(assigned_to__isnull=True)
        if q:
            name = Concat("policy__client__first_name", Value(" "), "policy__client__last_name", output_field=CharField())
            cards = cards.annotate(client_name=name).filter(
                Q(client_name__icontains=q) | Q(policy__policy_number__icontains=q)
            )

        settings = settings_for(organization)
        context = {
            "rn_view": view,
            "rn_when": when,
            "rn_stage": stage,
            "rn_agent": agent,
            "rn_q": q,
            "rn_mine": mine,
            "rn_is_manager": manager,
            "rn_settings": settings,
            "rn_buckets": EXPIRING_BUCKETS,
            "rn_stages": [(s.value, s.label) for s in Stage],
            "rn_open_stages": [(s.value, s.label) for s in Stage if s in InsuranceRenewal.OPEN_STAGES],
            "rn_lost_reasons": InsuranceRenewal.LostReason.choices,
            "rn_snooze_choices": SNOOZE_CHOICES,
            "rn_agents": assignable_users(organization) if manager else [],
        }

        if view == "retention":
            closed_or_due = cards.filter(expiration_date__lte=today + timedelta(days=settings.window_days))
            year_ago = today - timedelta(days=365)
            context["rn_retention"] = retention(closed_or_due.filter(expiration_date__gte=year_ago))
            return context

        if view == "closed":
            rows = cards.exclude(stage__in=InsuranceRenewal.OPEN_STAGES)
            if stage in {Stage.RENEWED, Stage.REWRITTEN, Stage.LOST}:
                rows = rows.filter(stage=stage)
            rows = rows.order_by("-closed_at", "-id")[:200]
        else:
            rows = cards.filter(stage__in=InsuranceRenewal.OPEN_STAGES)
            if stage in {s for s in InsuranceRenewal.OPEN_STAGES}:
                rows = rows.filter(stage=stage)
            if when == "overdue":
                rows = rows.filter(expiration_date__lt=today)
            elif when != "all":
                rows = rows.filter(expiration_date__gte=today, expiration_date__lte=today + timedelta(days=int(when)))
            rows = rows.order_by("expiration_date", "id")[:300]

        offsets = settings.reminder_offsets()
        open_all = cards.filter(stage__in=InsuranceRenewal.OPEN_STAGES)
        keep = {k: v for k, v in (("agent", agent), ("scope", request.GET.get("scope", "")), ("q", q)) if v}

        def chip_url(key):
            return "?" + urlencode({"view": "open", "when": key, **keep})

        chips = [{"key": "all", "label": "all open", "count": open_all.count(), "red": False}]
        overdue = open_all.filter(expiration_date__lt=today).count()
        if overdue:
            chips.append({"key": "overdue", "label": "expired", "count": overdue, "red": True})
        for d in EXPIRING_BUCKETS:
            chips.append({
                "key": str(d),
                "label": f"in {d} days",
                "count": open_all.filter(expiration_date__gte=today, expiration_date__lte=today + timedelta(days=d)).count(),
                "red": False,
            })
        for chip in chips:
            chip["url"] = chip_url(chip["key"])
        context.update(
            {
                "rn_rows": [
                    {
                        "card": c,
                        "days_left": days_left(c, today),
                        "reminder_due": reminder_due(c, offsets, today),
                        "snoozed": bool(c.snoozed_until and c.snoozed_until > today),
                        "phone": "".join(ch for ch in (c.policy.client.phone_number or "") if ch.isdigit() or ch == "+"),
                    }
                    for c in rows
                ],
                "rn_chips": chips,
            }
        )
        return context

    return _render_page(request, "renewals", "core/insurance_area/renewals.html", extra=extra)


@login_required
def renewal_detail(request, renewal_id):
    def extra(organization, membership):
        card, _ = _card_for(request, renewal_id, work=False)
        today = timezone.localdate()
        settings = settings_for(organization)
        values = message_values(card, request.user)
        terms = default_terms(card)
        return {
            "rn_card": card,
            "rn_can_work": _can_work(request.user, membership, card),
            "rn_is_manager": is_renewal_manager(request.user, membership),
            "rn_days_left": days_left(card, today),
            "rn_reminder_due": reminder_due(card, settings.reminder_offsets(), today),
            "rn_events": card.events.select_related("user")[:100],
            "rn_email_subject": fill_template(settings.email_subject, values),
            "rn_email_body": fill_template(settings.email_body, values),
            "rn_text_body": fill_template(settings.text_body, values),
            "rn_phone": "".join(ch for ch in (card.policy.client.phone_number or "") if ch.isdigit() or ch == "+"),
            "rn_terms": terms,
            "rn_terms_end": add_months(terms.start_date, terms.period_months),
            "rn_companies": organization.insurance_companies.order_by("name"),
            "rn_linkable": list(linkable_policies(card)[:10]) if card.is_open else [],
            "rn_history": renewal_history(card.policy),
            "rn_lost_reasons": InsuranceRenewal.LostReason.choices,
            "rn_snooze_choices": SNOOZE_CHOICES,
            "rn_open_stages": [(s.value, s.label) for s in Stage if s in InsuranceRenewal.OPEN_STAGES],
            "rn_agents": assignable_users(organization) if is_renewal_manager(request.user, membership) else [],
        }

    return _render_page(
        request, "renewals", "core/insurance_area/renewal_detail.html", extra=extra, label="Renewal"
    )


@login_required
@require_POST
def renewal_action(request, renewal_id):
    """Small card updates: log contact, move stage, snooze, reassign, lose, reopen."""
    card, membership = _card_for(request, renewal_id)
    action = request.POST.get("action") or ""
    user = request.user
    wants_json = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if action == "contact":
        kind = request.POST.get("kind") or Event.NOTE
        if kind not in CONTACT_KINDS:
            kind = Event.NOTE
        note = (request.POST.get("note") or "").strip()
        if kind == Event.NOTE:
            if not note:
                messages.error(request, "Write a note first.")
                return _back(request, card)
            log_event(card, Event.NOTE, user, note)
            card.save(update_fields=["updated_at"])
        else:
            record_contact(card, user, kind, note)
            card.save()
        if wants_json:
            return JsonResponse({"ok": True, "stage": card.stage})
        messages.success(request, "Saved to the renewal log.")
    elif action == "stage":
        stage = request.POST.get("stage") or ""
        if stage not in InsuranceRenewal.OPEN_STAGES or not card.is_open:
            messages.error(request, "Pick an open stage.")
            return _back(request, card)
        if stage != card.stage:
            old = card.get_stage_display()
            card.stage = stage
            card.save()
            log_event(card, Event.STAGE, user, f"{old} → {card.get_stage_display()}")
        messages.success(request, f"Moved to {card.get_stage_display()}.")
    elif action == "snooze":
        days = request.POST.get("days") or ""
        if days == "0":
            card.snoozed_until = None
            card.save()
            log_event(card, Event.SNOOZE, user, "Snooze cleared")
            messages.success(request, "Snooze cleared.")
        elif days.isdigit() and int(days) in SNOOZE_CHOICES:
            card.snoozed_until = timezone.localdate() + timedelta(days=int(days))
            card.save()
            log_event(card, Event.SNOOZE, user, f"Snoozed until {card.snoozed_until:%b %d, %Y}")
            messages.success(request, f"Snoozed until {card.snoozed_until:%b %d}.")
        else:
            messages.error(request, "Pick how long to snooze.")
    elif action == "assign":
        if not is_renewal_manager(user, membership):
            deny_access("Only owners and managers can reassign renewals.")
        target = (request.POST.get("assigned_to") or "").strip()
        new_user = None
        if target:
            match = assignable_users(card.organization).filter(user_id=target if target.isdigit() else 0).first()
            if match is None:
                messages.error(request, "Pick an agent with insurance access.")
                return _back(request, card)
            new_user = match.user
        card.assigned_to = new_user
        card.save()
        who = (new_user.get_full_name() or new_user.get_username()) if new_user else "nobody"
        log_event(card, Event.ASSIGN, user, f"Assigned to {who}")
        messages.success(request, f"Assigned to {who}.")
    elif action == "lost":
        reason = request.POST.get("reason") or ""
        if reason not in InsuranceRenewal.LostReason.values:
            messages.error(request, "Pick why the renewal was lost.")
            return _back(request, card)
        close_lost(card, user, reason, request.POST.get("note") or "")
        messages.success(request, "Marked as lost. The client stays on the win-back list.")
    elif action == "reopen":
        if card.is_open or card.new_policy_id:
            messages.error(request, "Only lost renewals can be reopened.")
            return _back(request, card)
        reopen(card, user)
        messages.success(request, "Renewal reopened.")
    else:
        messages.error(request, "Unknown action.")
    return _back(request, card)


@login_required
@require_POST
def renewal_renew(request, renewal_id):
    card, _membership = _card_for(request, renewal_id)
    if not card.is_open:
        messages.error(request, "This renewal is already closed.")
        return redirect(_detail_url(card))
    try:
        terms = terms_from_post(card, request.POST)
        new = renew(card, request.user, terms)
    except (ValidationError, InvalidOperation) as exc:
        messages.error(request, " ".join(getattr(exc, "messages", [str(exc)])))
        return redirect(_detail_url(card))
    messages.success(request, f"New term created ({new.start_date:%b %d, %Y} – {new.end_date:%b %d, %Y}).")
    return redirect(_detail_url(card))


@login_required
@require_POST
def renewal_link(request, renewal_id):
    card, _membership = _card_for(request, renewal_id)
    policy_id = request.POST.get("policy_id") or ""
    policy = linkable_policies(card).filter(id=int(policy_id) if policy_id.isdigit() else 0).first()
    if not card.is_open or policy is None:
        messages.error(request, "Pick one of this client's newer policies.")
        return redirect(_detail_url(card))
    link_existing(card, request.user, policy)
    messages.success(request, f"Linked policy {policy.policy_number or '#' + str(policy.id)} as the new term.")
    return redirect(_detail_url(card))


@login_required
@require_POST
def renewal_email(request, renewal_id):
    card, _membership = _card_for(request, renewal_id)
    error = send_renewal_email(card, request.user, request.POST.get("subject"), request.POST.get("body"))
    if error:
        messages.error(request, error)
    else:
        messages.success(request, f"Reminder emailed to {card.policy.client.email}.")
    return redirect(_detail_url(card))


@login_required
@require_POST
def renewal_settings_save(request):
    organization, membership, _is_owner, _banking = _insurance_access(request)
    if not is_renewal_manager(request.user, membership):
        deny_access("Only owners and managers can change renewal settings.")
    settings = settings_for(organization)
    errors = []

    window = (request.POST.get("window_days") or "").strip()
    if window.isdigit() and 7 <= int(window) <= 180:
        settings.window_days = int(window)
    else:
        errors.append("Show cards between 7 and 180 days before expiration.")

    offsets = []
    for part in (request.POST.get("reminder_days") or "").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or not 1 <= int(part) <= 180:
            errors.append("Reminder days must be numbers between 1 and 180, separated by commas.")
            break
        offsets.append(int(part))
    settings.reminder_days = ",".join(str(o) for o in sorted(set(offsets), reverse=True))

    target = (request.POST.get("daily_collection_target") or "0").replace(",", "").replace("$", "").strip() or "0"
    try:
        amount = Decimal(target)
        if amount < 0:
            raise InvalidOperation
        settings.daily_collection_target = amount.quantize(Decimal("0.01"))
    except InvalidOperation:
        errors.append("Daily collection goal must be a positive amount.")

    for name, limit in (("email_subject", 180), ("email_body", 5000), ("text_body", 1000)):
        value = (request.POST.get(name) or "").strip()
        if value:
            setattr(settings, name, value[:limit])

    if errors:
        for error in errors:
            messages.error(request, error)
    else:
        settings.save()
        sync_renewals(organization)
        messages.success(request, "Renewal settings saved.")
    return redirect(reverse("insurance-renewals") + "?view=" + (request.POST.get("view") or "open"))
