"""Radar page of the Insurance area: DMV-to-insurance opportunities."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import CharField, Count, Q, Value
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .http import deny_access
from .insurance_area_views import _insurance_access, _render_page
from .insurance_radar import (
    assign,
    close,
    now_insured,
    radar_enabled,
    reopen,
    scoped_items,
    scoreboard,
    sync_radar,
)
from .insurance_radar_models import InsuranceRadarItem
from .insurance_renewals import assignable_users, is_renewal_manager

Signal = InsuranceRadarItem.Signal
Status = InsuranceRadarItem.Status
PAGE_LIMIT = 200
SCOREBOARD_DAYS = 90


def _phone(value) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit() or ch == "+")


@login_required
def radar_page(request):
    def extra(organization, membership):
        if not radar_enabled(organization):
            deny_access("The radar needs both the PSB portal and Insurance.")
        manager = is_renewal_manager(request.user, membership)
        sync_radar(organization)

        status = request.GET.get("status") or Status.OPEN
        if status not in Status.values:
            status = Status.OPEN
        signal = request.GET.get("signal") or ""
        agent = request.GET.get("agent") or ""
        q = " ".join((request.GET.get("q") or "").split())[:80]

        base = scoped_items(organization, request.user, manager=manager)
        if manager and agent == "none":
            base = base.filter(assigned_to__isnull=True)
        elif manager and agent == "me":
            base = base.filter(assigned_to=request.user)
        elif manager and agent.isdigit():
            base = base.filter(assigned_to_id=int(agent))
        if q:
            full_name = Concat("client__first_name", Value(" "), "client__last_name", output_field=CharField())
            base = base.annotate(client_full=full_name).filter(
                Q(client_full__icontains=q)
                | Q(client__business_name__icontains=q)
                | Q(vehicle__plate_number__iexact=q)
                | Q(client__phone_number__contains=q)
            )

        by_status = base.filter(status=status)
        counts = dict(by_status.values_list("signal").annotate(n=Count("id")))
        rows_qs = by_status.filter(signal=signal) if signal in Signal.values else by_status
        order = ("signal_date", "id") if status == Status.OPEN else ("-closed_at", "-id")
        items = list(rows_qs.order_by(*order)[:PAGE_LIMIT])
        insured = now_insured(items, organization) if status == Status.OPEN else set()

        def chip_url(key):
            params = {k: v for k, v in {"status": status, "agent": agent, "q": q, "signal": key}.items() if v}
            return "?" + urlencode(params)

        chips = [{"key": "", "label": "All", "count": sum(counts.values()), "url": chip_url("")}]
        chips += [
            {"key": key, "label": label, "count": counts.get(key, 0), "url": chip_url(key)}
            for key, label in Signal.choices
        ]
        tab_counts = dict(base.values_list("status").annotate(n=Count("id")))
        return {
            "rd_is_manager": manager,
            "rd_status": status,
            "rd_signal": signal,
            "rd_agent": agent,
            "rd_q": q,
            "rd_chips": chips,
            "rd_tabs": [(value, label, tab_counts.get(value, 0)) for value, label in Status.choices],
            "rd_rows": [
                {"item": i, "now_insured": i.id in insured, "phone": _phone(i.client.phone_number)} for i in items
            ],
            "rd_truncated": rows_qs.count() > PAGE_LIMIT,
            "rd_agents": assignable_users(organization) if manager else [],
            "rd_scoreboard": scoreboard(organization, since=timezone.localdate() - timedelta(days=SCOREBOARD_DAYS)),
            "rd_scoreboard_days": SCOREBOARD_DAYS,
        }

    return _render_page(request, "radar", "core/insurance_area/radar.html", extra=extra)


def _radar_access(request):
    organization, membership, _is_owner, _banking = _insurance_access(request)
    if not radar_enabled(organization):
        deny_access("The radar needs both the PSB portal and Insurance.")
    return organization, is_renewal_manager(request.user, membership)


def _back(request):
    nxt = request.POST.get("next") or ""
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect("insurance-radar")


def _assignee(organization, raw):
    if not raw:
        return None
    if not str(raw).isdigit():
        return False
    member = assignable_users(organization).filter(user_id=int(raw)).first()
    return member.user if member else False


@login_required
@require_POST
def radar_action(request, item_id):
    organization, manager = _radar_access(request)
    item = get_object_or_404(InsuranceRadarItem.objects.select_related("client"), id=item_id, organization=organization)
    if not manager and item.assigned_to_id != request.user.id:
        deny_access("This radar item is not assigned to you.")
    action = request.POST.get("action") or ""
    note = (request.POST.get("note") or "").strip()

    if action == "assign":
        if not manager:
            deny_access("Only managers can assign radar items.")
        assignee = _assignee(organization, request.POST.get("assigned_to"))
        if assignee is False:
            messages.error(request, "Pick an agent who can use Insurance.")
        else:
            assign([item], assignee, request.user)
            messages.success(
                request,
                f"Assigned to {assignee.get_full_name() or assignee.username}." if assignee else "Unassigned.",
            )
    elif action in ("done", "dismiss") and item.is_open:
        won = request.POST.get("won") == "1"
        close(item, request.user, status=Status.DONE if action == "done" else Status.DISMISSED, won=won, note=note)
        label = "Marked won" if won and action == "done" else ("Marked done" if action == "done" else "Dismissed")
        messages.success(request, f"{label}: {item.client.name}.")
    elif action == "reopen" and not item.is_open:
        reopen(item)
        messages.success(request, f"Reopened: {item.client.name}.")
    elif action == "note":
        item.note = note[:4000]
        item.save(update_fields=["note", "updated_at"])
        messages.success(request, "Note saved.")
    return _back(request)


@login_required
@require_POST
def radar_bulk_assign(request):
    organization, manager = _radar_access(request)
    if not manager:
        deny_access("Only managers can assign radar items.")
    ids = [int(i) for i in request.POST.getlist("items") if i.isdigit()]
    assignee = _assignee(organization, request.POST.get("assigned_to"))
    if not ids:
        messages.error(request, "Select at least one item.")
    elif assignee is False:
        messages.error(request, "Pick an agent who can use Insurance.")
    else:
        items = list(
            InsuranceRadarItem.objects.filter(organization=organization, id__in=ids, status=Status.OPEN).select_related(
                "organization"
            )
        )
        changed = assign(items, assignee, request.user)
        who = (assignee.get_full_name() or assignee.username) if assignee else "nobody"
        messages.success(request, f"{changed} item{'s' if changed != 1 else ''} assigned to {who}.")
    return _back(request)
