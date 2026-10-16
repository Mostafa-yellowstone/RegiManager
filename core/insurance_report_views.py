"""Insurance Space Reporting Center export views."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET

from .access import organizations_for_user
from .http import deny_access
from .insurance_report_pdf import (
    parse_iso_date,
    render_agent_production_pdf,
    render_aging_pdf,
    render_book_of_business_pdf,
    render_cashout_pdf,
    render_commission_production_pdf,
    render_compliance_pdf,
    render_payment_receipt_pdf,
    render_quote_conversion_pdf,
    render_remittance_pdf,
    render_targets_pdf,
    render_unearned_pdf,
)
from .insurance_permissions import membership_for_org
from .insurance_targets_metrics import resolve_target_month
from .models import DailyPaymentTransaction, OrganizationMembership


def _org(request, *, finance=False):
    """
    Active PSB for the export. Everyone needs Insurance Space access; commission, remittance,
    production and book-of-business exports also need finance or reports rights.
    """
    orgs = organizations_for_user(request)
    active_id = request.session.get("active_org_id")
    org = orgs.filter(id=active_id).first() if active_id else orgs.first()
    if org is None:
        deny_access("Organization required.")
    if request.user.is_superuser:
        return org
    membership = membership_for_org(request.user, org)
    if membership is None:
        deny_access("Organization required.")
    is_owner = membership.role == OrganizationMembership.Role.OWNER
    finance_ok = is_owner or membership.can_view_banking or membership.can_view_reports
    if finance and not finance_ok:
        deny_access("You do not have permission to export insurance finance reports.")
    if not (finance_ok or membership.can_deal_with_insurance):
        deny_access("You do not have access to the Insurance Space.")
    return org


def _prepared_by(request) -> str:
    return request.user.get_full_name() or request.user.username


def _range(request):
    return parse_iso_date(request.GET.get("start_date")), parse_iso_date(request.GET.get("end_date"))


def _company_id(request):
    raw = (request.GET.get("company") or "").strip()
    return int(raw) if raw.isdigit() else None


def _pdf(content: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@login_required
@require_GET
def export_insurance_remittance_pdf(request):
    org = _org(request, finance=True)
    start, end = _range(request)
    company_id = _company_id(request)
    pdf = render_remittance_pdf(
        org, start=start, end=end, company_id=company_id, prepared_by=_prepared_by(request)
    )
    return _pdf(pdf, f"carrier-remittance-{org.id}.pdf")


@login_required
@require_GET
def export_insurance_payment_receipt_pdf(request, payment_id: int):
    org = _org(request)
    payment = get_object_or_404(
        DailyPaymentTransaction.objects.select_related(
            "client", "insurance_company", "insurance_policy", "recorded_by"
        ),
        id=payment_id,
        organization=org,
    )
    pdf = render_payment_receipt_pdf(org, payment, prepared_by=_prepared_by(request))
    return _pdf(pdf, f"payment-receipt-PMT-{payment.id:06d}.pdf")


@login_required
@require_GET
def export_insurance_agent_production_pdf(request):
    org = _org(request, finance=True)
    start, end = _range(request)
    pdf = render_agent_production_pdf(org, start=start, end=end, prepared_by=_prepared_by(request))
    return _pdf(pdf, f"producer-production-{org.id}.pdf")


@login_required
@require_GET
def export_insurance_unearned_pdf(request):
    org = _org(request, finance=True)
    start, end = _range(request)
    pdf = render_unearned_pdf(org, start=start, end=end, prepared_by=_prepared_by(request))
    return _pdf(pdf, f"unearned-commission-{org.id}.pdf")


@login_required
@require_GET
def export_insurance_cashout_pdf(request):
    org = _org(request)
    day = parse_iso_date(request.GET.get("date")) or timezone.localdate()
    pdf = render_cashout_pdf(org, day=day, prepared_by=_prepared_by(request))
    return _pdf(pdf, f"daily-cashout-{day.isoformat()}.pdf")


@login_required
@require_GET
def export_insurance_book_pdf(request):
    org = _org(request, finance=True)
    start, end = _range(request)
    pdf = render_book_of_business_pdf(
        org, prepared_by=_prepared_by(request), start=start, end=end
    )
    return _pdf(pdf, f"book-of-business-{org.id}.pdf")


@login_required
@require_GET
def export_insurance_aging_pdf(request):
    org = _org(request)
    pdf = render_aging_pdf(org, prepared_by=_prepared_by(request))
    return _pdf(pdf, f"installment-aging-{org.id}.pdf")


@login_required
@require_GET
def export_insurance_quote_conversion_pdf(request):
    org = _org(request)
    start, end = _range(request)
    pdf = render_quote_conversion_pdf(org, start=start, end=end, prepared_by=_prepared_by(request))
    return _pdf(pdf, f"quote-conversion-{org.id}.pdf")


@login_required
@require_GET
def export_insurance_compliance_pdf(request):
    org = _org(request)
    pdf = render_compliance_pdf(org, prepared_by=_prepared_by(request))
    return _pdf(pdf, f"license-compliance-{org.id}.pdf")


@login_required
@require_GET
def export_insurance_targets_pdf(request):
    org = _org(request, finance=True)
    year, month = resolve_target_month(request.GET.get("month") or "")
    pdf = render_targets_pdf(org, year=year, month=month, prepared_by=_prepared_by(request))
    return _pdf(pdf, f"targets-{year:04d}-{month:02d}.pdf")


@login_required
@require_GET
def export_insurance_commission_register_pdf(request):
    org = _org(request, finance=True)
    start, end = _range(request)
    pdf = render_commission_production_pdf(org, start=start, end=end, prepared_by=_prepared_by(request))
    return _pdf(pdf, f"commission-register-{org.id}.pdf")
