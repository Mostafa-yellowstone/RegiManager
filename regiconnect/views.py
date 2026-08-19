"""Insurance Space session views + inbound webhook."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from core.access import organizations_for_user
from core.http import deny_access
from core.models import Client, InsuranceCompany, Space

from .catalog import ensure_builtin_connectors
from .certification import run_certification
from .engines import create_submission, request_bind, submit_and_quote, ValidationError
from .exceptions import MissingCarrierSpec, TerminalConnectorError
from .models import CanonicalQuote, Connection, DeadLetterItem, MarketProfile
from .permissions import can_manage_regiconnect, can_view_regiconnect, require_insurance_space
from .runtime import retry_dead_letter
from .webhooks import verify_and_store


def _org(request, org_id=None):
    orgs = organizations_for_user(request)
    if org_id:
        org = orgs.filter(id=org_id).first()
        if org is None:
            deny_access("Organization not found.")
        return org
    return orgs.first()


@login_required
@require_POST
def create_mock_market_bundle(request):
    """Owner/manager helper: attach MarketProfile + sandbox mock connection to a company."""
    from .models import Appointment, Connection, Connector, ProducerCode
    from django.utils import timezone

    org_id = request.POST.get("organization") or request.POST.get("org")
    org = _org(request, org_id)
    membership = require_insurance_space(request, org)
    if not can_manage_regiconnect(request.user, org, membership):
        deny_access("You cannot manage connectivity.")
    ensure_builtin_connectors()
    company = get_object_or_404(
        InsuranceCompany, id=request.POST.get("company_id"), organization=org
    )
    profile, _ = MarketProfile.objects.get_or_create(
        company=company,
        defaults={
            "organization": org,
            "market_type": MarketProfile.MarketType.CARRIER,
            "status": MarketProfile.Status.ACTIVE,
            "states": ["NY"],
            "lines_of_business": ["auto_personal"],
            "requires_appointment": True,
            "requires_producer_code": True,
        },
    )
    if profile.status != MarketProfile.Status.ACTIVE:
        profile.status = MarketProfile.Status.ACTIVE
        profile.save(update_fields=["status"])
    appt, _ = Appointment.objects.get_or_create(
        organization=org,
        market=profile,
        state="NY",
        line_of_business="auto_personal",
        defaults={"status": Appointment.Status.ACTIVE, "effective_date": timezone.localdate()},
    )
    if appt.status != Appointment.Status.ACTIVE:
        appt.status = Appointment.Status.ACTIVE
        appt.effective_date = appt.effective_date or timezone.localdate()
        appt.save(update_fields=["status", "effective_date"])
    ProducerCode.objects.get_or_create(
        organization=org,
        market=profile,
        code=request.POST.get("producer_code") or "MOCK-1",
        state="NY",
        line_of_business="auto_personal",
    )
    connector = Connector.objects.get(slug="mock")
    connection, _ = Connection.objects.get_or_create(
        organization=org,
        market=profile,
        connector=connector,
        environment=Connection.Environment.SANDBOX,
        defaults={"status": Connection.Status.ACTIVE, "capabilities": connector.capabilities},
    )
    if connection.status != Connection.Status.ACTIVE:
        connection.status = Connection.Status.ACTIVE
        connection.save(update_fields=["status", "updated_at"])
    messages.success(
        request,
        f"تم تجهيز التجربة الوهمية لـ {company.name}. المفروض تلاقي صف للشركة في الجدول تحت.",
    )
    space = Space.objects.filter(organization=org, key="insurance").first()
    if space:
        return redirect(f"{reverse('inventory-detail', args=[space.id])}?tab=regi-markets")
    return redirect("spaces-home")


@login_required
@require_POST
def submit_to_market(request):
    org = _org(request, request.POST.get("organization"))
    membership = require_insurance_space(request, org)
    if not can_manage_regiconnect(request.user, org, membership) and not can_view_regiconnect(request.user, org, membership):
        deny_access("You cannot create submissions.")
    if not can_manage_regiconnect(request.user, org, membership):
        deny_access("You cannot create submissions.")
    connection = get_object_or_404(
        Connection.objects.select_related("market", "connector"),
        id=request.POST.get("connection_id"),
        organization=org,
    )
    client = None
    if request.POST.get("client_id"):
        client = get_object_or_404(Client, id=request.POST.get("client_id"), organization=org)
    try:
        submission = create_submission(
            organization=org,
            market=connection.market,
            connection=connection,
            actor=request.user,
            client=client,
            state=request.POST.get("state") or "NY",
            line_of_business=request.POST.get("line_of_business") or "auto_personal",
            extra={"name": request.POST.get("name") or (client.name if client else "Quote")},
            scenario=request.POST.get("scenario") or "quote",
        )
        submit_and_quote(submission)
        submission.refresh_from_db()
        quote = submission.quotes.order_by("-version").first()
        if quote:
            messages.success(
                request,
                f"الكوت الوهمي جاهز: ${quote.premium} — شوف الجدول تحت، وبعدين Quote Pipeline.",
            )
        else:
            messages.warning(
                request,
                f"الطلب اتسجل بحالة {submission.get_status_display()}."
                + (f" السبب: {submission.last_error}" if submission.last_error else ""),
            )
    except ValidationError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, f"فشل الإرسال: {exc}")
    space = Space.objects.filter(organization=org, key="insurance").first()
    if space:
        from django.urls import reverse

        return redirect(f"{reverse('inventory-detail', args=[space.id])}?tab=regi-submissions")
    return redirect("spaces-home")


@login_required
@require_POST
def bind_quote(request, quote_id):
    org = _org(request, request.POST.get("organization"))
    membership = require_insurance_space(request, org)
    if not can_manage_regiconnect(request.user, org, membership):
        deny_access("You cannot bind quotes.")
    quote = get_object_or_404(CanonicalQuote, id=quote_id, organization=org)
    try:
        bind = request_bind(quote, actor=request.user)
        bind.refresh_from_db()
        if bind.status == bind.Status.BOUND:
            messages.success(request, "البوليسي اتسجلت في Insurance CRM (رقم MOCK-POL).")
        else:
            messages.warning(
                request,
                f"الربط لسه {bind.get_status_display()}."
                + (f" {bind.last_error}" if bind.last_error else ""),
            )
    except ValidationError as exc:
        messages.error(request, str(exc))
    space = Space.objects.filter(organization=org, key="insurance").first()
    if space:
        from django.urls import reverse

        return redirect(f"{reverse('inventory-detail', args=[space.id])}?tab=regi-submissions")
    return redirect("spaces-home")


@login_required
@require_POST
def retry_dlq_item(request, item_id):
    org = _org(request, request.POST.get("organization"))
    membership = require_insurance_space(request, org)
    if not can_manage_regiconnect(request.user, org, membership):
        deny_access("You cannot retry connectivity jobs.")
    item = get_object_or_404(DeadLetterItem, id=item_id, organization=org)
    retry_dead_letter(item, actor=request.user)
    messages.success(request, "Dead-letter job queued for retry.")
    space = Space.objects.filter(organization=org, key="insurance").first()
    if space:
        from django.urls import reverse

        return redirect(f"{reverse('inventory-detail', args=[space.id])}?tab=regi-connectivity")
    return redirect("spaces-home")


@login_required
@require_POST
def certify_connection(request, connection_id):
    org = _org(request, request.POST.get("organization"))
    membership = require_insurance_space(request, org)
    if not can_manage_regiconnect(request.user, org, membership):
        deny_access("You cannot run certification.")
    connection = get_object_or_404(Connection, id=connection_id, organization=org)
    try:
        run = run_certification(connection)
        messages.success(request, f"Certification {run.status}.")
    except MissingCarrierSpec as exc:
        messages.error(request, str(exc))
    space = Space.objects.filter(organization=org, key="insurance").first()
    if space:
        from django.urls import reverse

        return redirect(f"{reverse('inventory-detail', args=[space.id])}?tab=regi-connectivity")
    return redirect("spaces-home")


@csrf_exempt
@require_http_methods(["POST"])
def inbound_webhook(request, connection_id):
    connection = get_object_or_404(Connection, id=connection_id)
    try:
        event = verify_and_store(
            connection=connection,
            body=request.body,
            headers=request.headers,
        )
    except TerminalConnectorError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True, "duplicate": event.status == event.Status.DUPLICATE, "id": event.id})
