"""Bind quotes, record policy transactions, match commission statements, and open the morning queue."""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .insurance_desk_models import (
    InsuranceCertificate,
    InsuranceCertificateHolder,
    InsuranceClaim,
    InsuranceCommissionStatement,
    InsuranceCommissionStatementLine,
    InsuranceCoverage,
    InsuranceIssuedForm,
    InsurancePolicyTransaction,
    InsuranceQuoteOption,
)
from .insurance_desk_pdf import certificate_pdf, compensation_disclosure_pdf, temporary_id_card_pdf
from .insurance_producer_models import InsurancePolicyPremiumChange
from .models import (
    InsuranceCompany,
    InsurancePolicy,
    InsurancePolicyDocument,
    InsurancePolicyDriver,
    InsurancePolicyVehicle,
)

ZERO = Decimal("0.00")
TEMPORARY_ID_TITLE = "Temporary insurance ID card"
DISCLOSURE_TITLE = "Compensation disclosure"
PHYSICAL_DAMAGE = {InsuranceCoverage.Code.COMP, InsuranceCoverage.Code.COLL}
POLICY_COVERAGE_CODES = [code for code, _label in InsuranceCoverage.Code.choices]


def _money(raw) -> Decimal | None:
    text = (raw or "").strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(raw) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def save_policy_coverages(policy, post) -> None:
    """Replace policy-level coverages from the desk form. Blank rows are removed."""
    policy.coverages.filter(vehicle__isnull=True).delete()
    rows = []
    for code in POLICY_COVERAGE_CODES:
        limit_text = (post.get(f"coverage_{code}_limit") or "").strip()[:80]
        deductible = _money(post.get(f"coverage_{code}_deductible"))
        if not limit_text and deductible is None:
            continue
        rows.append(InsuranceCoverage(policy=policy, code=code, limit_text=limit_text, deductible=deductible))
    if rows:
        InsuranceCoverage.objects.bulk_create(rows)
    policy.coverages_need_review = False
    policy.save(update_fields=["coverages_need_review", "updated_at"])
    mark_photo_inspection_required(policy)


def add_vehicle_coverage(policy, vehicle, code, limit_text, deductible) -> None:
    if code not in POLICY_COVERAGE_CODES:
        return
    InsuranceCoverage.objects.update_or_create(
        policy=policy,
        vehicle=vehicle,
        code=code,
        defaults={"limit_text": (limit_text or "")[:80], "deductible": deductible},
    )
    mark_photo_inspection_required(policy)


def mark_photo_inspection_required(policy) -> None:
    has_physical = policy.coverages.filter(code__in=PHYSICAL_DAMAGE).exists()
    if has_physical and not policy.photo_inspection_status:
        policy.photo_inspection_status = InsurancePolicy.PhotoInspection.REQUIRED
        policy.save(update_fields=["photo_inspection_status", "updated_at"])
    elif not has_physical and policy.photo_inspection_status == InsurancePolicy.PhotoInspection.REQUIRED:
        policy.photo_inspection_status = ""
        policy.photo_inspection_on = None
        policy.save(update_fields=["photo_inspection_status", "photo_inspection_on", "updated_at"])


def apply_parsed_coverages(policy, coverages) -> None:
    if not coverages:
        return
    policy.coverages.filter(vehicle__isnull=True).delete()
    InsuranceCoverage.objects.bulk_create(
        [
            InsuranceCoverage(
                policy=policy,
                code=row.code,
                limit_text=(row.limit_text or "")[:80],
                deductible=row.deductible,
            )
            for row in coverages
            if row.code in POLICY_COVERAGE_CODES
        ]
    )
    mark_photo_inspection_required(policy)


def _store_pdf(policy, *, document_type, title, pdf_bytes, user) -> InsurancePolicyDocument:
    existing = policy.documents.filter(title=title).order_by("-id").first()
    content = ContentFile(pdf_bytes, name=f"{title.lower().replace(' ', '-')}.pdf")
    if existing:
        existing.file.save(content.name, content, save=True)
        return existing
    return InsurancePolicyDocument.objects.create(
        policy=policy,
        document_type=document_type,
        title=title,
        file=content,
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
    )


def issue_temporary_id_card(policy, user=None, *, force=False) -> InsurancePolicyDocument | None:
    if policy.stage != InsurancePolicy.StageChoices.BOUND:
        return None
    existing = policy.documents.filter(title=TEMPORARY_ID_TITLE).order_by("-id").first()
    carrier_card = (
        policy.documents.filter(document_type=InsurancePolicyDocument.DocumentType.ID_CARDS)
        .exclude(title=TEMPORARY_ID_TITLE)
        .exists()
    )
    if carrier_card and not force:
        return existing
    if existing and not force:
        return existing
    pdf = temporary_id_card_pdf(policy)
    return _store_pdf(
        policy,
        document_type=InsurancePolicyDocument.DocumentType.ID_CARDS,
        title=TEMPORARY_ID_TITLE,
        pdf_bytes=pdf,
        user=user,
    )


def issue_compensation_disclosure(policy, user=None) -> InsurancePolicyDocument:
    pdf = compensation_disclosure_pdf(policy)
    document = _store_pdf(
        policy,
        document_type=InsurancePolicyDocument.DocumentType.OTHER,
        title=DISCLOSURE_TITLE,
        pdf_bytes=pdf,
        user=user,
    )
    policy.compensation_disclosed_at = timezone.now()
    policy.save(update_fields=["compensation_disclosed_at", "updated_at"])
    return document


def _record_premium_change(policy, old_premium, new_premium, effective, user, note):
    if old_premium == new_premium:
        return
    InsurancePolicyPremiumChange.objects.create(
        policy=policy,
        old_premium=old_premium,
        new_premium=new_premium,
        effective_date=effective,
        note=(note or "")[:255],
        changed_by=user if getattr(user, "is_authenticated", False) else None,
    )


@transaction.atomic
def record_transaction(
    policy,
    *,
    kind: str,
    user=None,
    effective_date: date | None = None,
    new_premium: Decimal | None = None,
    reason: str = "",
    requested_by: str = "",
    notice_date: date | None = None,
    note: str = "",
) -> InsurancePolicyTransaction:
    today = timezone.localdate()
    effective = effective_date or today
    old_premium = policy.premium or ZERO
    updated_premium = old_premium if new_premium is None else new_premium
    if kind == InsurancePolicyTransaction.Kind.CANCELLATION:
        policy.status = InsurancePolicy.StatusChoices.INACTIVE
        policy.inactive_date = effective
    elif kind == InsurancePolicyTransaction.Kind.REINSTATEMENT:
        policy.status = InsurancePolicy.StatusChoices.ACTIVE
        policy.inactive_date = None
        policy.stage = InsurancePolicy.StageChoices.BOUND
    elif kind == InsurancePolicyTransaction.Kind.ENDORSEMENT:
        policy.stage = InsurancePolicy.StageChoices.ENDORSEMENT
        policy.premium = updated_premium
    elif kind == InsurancePolicyTransaction.Kind.NEW_BUSINESS:
        policy.stage = InsurancePolicy.StageChoices.BOUND
        policy.status = InsurancePolicy.StatusChoices.ACTIVE
        if new_premium is not None:
            policy.premium = updated_premium
    policy.save()
    _record_premium_change(policy, old_premium, policy.premium or ZERO, effective, user, note or kind)
    return InsurancePolicyTransaction.objects.create(
        policy=policy,
        kind=kind,
        effective_date=effective,
        old_premium=old_premium,
        new_premium=policy.premium or ZERO,
        reason=reason,
        requested_by=requested_by,
        notice_date=notice_date,
        note=(note or "")[:500],
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )


def _coverage_rows_from_option(option: InsuranceQuoteOption):
    rows = [
        ("bi", option.bi_limit, None),
        ("pd", option.pd_limit, None),
        ("pip", option.pip_limit, None),
        ("um", option.um_limit, None),
        ("comp", "ACV" if option.comp_deductible is not None else "", option.comp_deductible),
        ("coll", "ACV" if option.coll_deductible is not None else "", option.coll_deductible),
    ]
    return [(code, limit, ded) for code, limit, ded in rows if limit or ded is not None]


@transaction.atomic
def bind_quote_option(option: InsuranceQuoteOption, user) -> InsurancePolicy:
    from datetime import timedelta as _td

    from .insurance_quote_crm import sync_quote_lead_to_crm
    from .insurance_quote_pipeline_models import InsuranceQuoteLead

    lead = option.lead
    policy = lead.crm_policy or sync_quote_lead_to_crm(lead)
    if policy is None:
        raise ValueError("This lead has no client record to bind.")
    lead.options.exclude(id=option.id).filter(decision=InsuranceQuoteOption.Decision.PENDING).update(
        decision=InsuranceQuoteOption.Decision.DECLINED
    )
    option.decision = InsuranceQuoteOption.Decision.ACCEPTED
    option.save(update_fields=["decision"])

    company = option.company
    if company is None and option.carrier_name:
        company, _ = InsuranceCompany.objects.get_or_create(
            organization=lead.organization,
            name=option.carrier_name.strip()[:120],
        )
        option.company = company
        option.save(update_fields=["company"])
    today = timezone.localdate()
    months = option.term_months or 6
    policy.insurance_company = company
    policy.premium = option.term_premium or ZERO
    policy.stage = InsurancePolicy.StageChoices.BOUND
    policy.status = InsurancePolicy.StatusChoices.ACTIVE
    policy.bound_date = today
    policy.start_date = today
    policy.end_date = today + _td(days=30 * months)
    policy.renewal_date = policy.end_date
    policy.insurance_period_months = months
    if lead.insurance_type:
        policy.insurance_type = lead.insurance_type[:30]
    policy.named_insured = (lead.client_name or "")[:255]
    if lead.vin:
        policy.vin = lead.vin[:17]
    policy.save()

    policy.coverages.filter(vehicle__isnull=True).delete()
    InsuranceCoverage.objects.bulk_create(
        [
            InsuranceCoverage(policy=policy, code=code, limit_text=(limit or "")[:80], deductible=ded)
            for code, limit, ded in _coverage_rows_from_option(option)
        ]
    )
    mark_photo_inspection_required(policy)
    _copy_risk_from_lead(policy, lead)
    record_transaction(
        policy,
        kind=InsurancePolicyTransaction.Kind.NEW_BUSINESS,
        user=user,
        effective_date=today,
        new_premium=policy.premium,
        note=f"Bound from {option.carrier_label}",
    )
    lead.stage = InsuranceQuoteLead.Stage.WON
    lead.save(update_fields=["stage", "updated_at"])
    issue_temporary_id_card(policy, user)
    issue_compensation_disclosure(policy, user)
    return policy


def _copy_risk_from_lead(policy, lead) -> None:
    if not policy.policy_drivers.exists() and (lead.client_name or lead.dl_number):
        InsurancePolicyDriver.objects.create(
            policy=policy,
            name=(lead.client_name or "Named insured")[:200],
            date_of_birth=lead.date_of_birth,
            license_number=(lead.dl_number or "")[:40],
        )
        for extra in lead.additional_drivers.all():
            InsurancePolicyDriver.objects.create(
                policy=policy,
                name=(extra.full_name or "Driver")[:200],
                date_of_birth=extra.date_of_birth,
                license_number=(extra.dl_number or "")[:40],
            )
    if not policy.policy_vehicles.exists() and (lead.vin or lead.vehicle_make):
        year = int(lead.vehicle_year) if (lead.vehicle_year or "").isdigit() else None
        InsurancePolicyVehicle.objects.create(
            policy=policy,
            auto_number=1,
            year=year,
            make=(lead.vehicle_make or "")[:60],
            vin=(lead.vin or "")[:17],
        )
        number = 2
        for extra in lead.additional_vehicles.all():
            extra_year = int(extra.year) if (extra.year or "").isdigit() else None
            InsurancePolicyVehicle.objects.create(
                policy=policy,
                auto_number=number,
                year=extra_year,
                make=(extra.make or "")[:60],
                vin=(extra.vin or "")[:17],
            )
            number += 1


def _statement_rows(upload) -> list[tuple[str, Decimal]]:
    name = (getattr(upload, "name", "") or "").lower()
    raw = upload.read()
    if name.endswith(".pdf") or raw[:4] == b"%PDF":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            text = ""
    else:
        text = raw.decode("utf-8-sig", errors="replace")
        if "," in text.splitlines()[0] if text.splitlines() else "":
            rows = []
            for cells in csv.reader(io.StringIO(text)):
                if not cells or not any(cell.strip() for cell in cells):
                    continue
                policy_number = cells[0].strip()
                if policy_number.lower() in {"policy", "policy number", "policy_number", "policynumber"}:
                    continue
                amount = _money(cells[1] if len(cells) > 1 else "")
                if policy_number and amount is not None:
                    rows.append((policy_number[:100], amount))
            if hasattr(upload, "seek"):
                upload.seek(0)
            return rows
    rows = []
    for line in text.splitlines():
        amounts = re.findall(r"\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})", line)
        policy_number = ""
        for token in re.findall(r"\b([A-Za-z][A-Za-z0-9\-]{4,})\b", line):
            if any(ch.isdigit() for ch in token):
                policy_number = token
                break
        if not policy_number or not amounts:
            continue
        amount = _money(amounts[-1])
        if amount is None:
            continue
        rows.append((policy_number[:100], amount))
    if hasattr(upload, "seek"):
        upload.seek(0)
    return rows


def import_commission_csv(organization, upload, user, company=None, statement_date=None):
    rows = _statement_rows(upload)
    statement = InsuranceCommissionStatement.objects.create(
        organization=organization,
        company=company,
        statement_date=statement_date,
        source_name=getattr(upload, "name", "")[:200],
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    if not rows:
        statement.delete()
        return None
    if hasattr(upload, "seek"):
        try:
            upload.seek(0)
            statement.file.save(getattr(upload, "name", "statement.csv"), upload, save=True)
        except Exception:
            pass
    policies = (
        InsurancePolicy.objects.filter(organization=organization)
        .order_by("-start_date", "-id")
    )
    by_number: dict[str, InsurancePolicy] = {}
    for policy in policies:
        by_number.setdefault(policy.policy_number.strip().upper(), policy)
    for policy_number, paid in rows:
        policy = by_number.get(policy_number.upper())
        expected = policy.commission_amount if policy else None
        if policy is None:
            status = InsuranceCommissionStatementLine.Status.UNMATCHED
        elif expected is not None and paid + Decimal("0.01") < expected:
            status = InsuranceCommissionStatementLine.Status.SHORT
        else:
            status = InsuranceCommissionStatementLine.Status.MATCHED
        InsuranceCommissionStatementLine.objects.create(
            statement=statement,
            policy_number=policy_number,
            paid_amount=paid,
            expected_amount=expected,
            status=status,
            policy=policy,
        )
        if policy is not None:
            policy.commission_paid = paid
            policy.commission_received = True
            policy.save()
    return statement


def issue_certificate(certificate, user) -> InsuranceCertificate:
    pdf = certificate_pdf(certificate)
    certificate.file.save(f"certificate-{certificate.id}.pdf", ContentFile(pdf), save=False)
    certificate.status = InsuranceCertificate.Status.ISSUED
    certificate.issued_at = timezone.now()
    certificate.save(update_fields=["file", "status", "issued_at"])
    InsurancePolicyDocument.objects.create(
        policy=certificate.policy,
        document_type=InsurancePolicyDocument.DocumentType.OTHER,
        title=f"Certificate — {certificate.holder.name}"[:200],
        file=ContentFile(pdf, name=f"certificate-{certificate.id}.pdf"),
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
    )
    return certificate


def holder_for(organization, name, address="") -> InsuranceCertificateHolder:
    clean = (name or "").strip()[:200]
    holder, created = InsuranceCertificateHolder.objects.get_or_create(
        organization=organization,
        name=clean,
        defaults={"address": (address or "")[:400]},
    )
    if not created and address and not holder.address:
        holder.address = address[:400]
        holder.save(update_fields=["address"])
    return holder


def open_claim(policy, *, loss_date, description="", other_party="", police_report="", vehicle=None, user=None, by_client=False):
    return InsuranceClaim.objects.create(
        policy=policy,
        vehicle=vehicle,
        loss_date=loss_date,
        description=description,
        other_party=(other_party or "")[:200],
        police_report=(police_report or "")[:80],
        opened_by_client=by_client,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )


def issue_standard_form(policy, form_key: str, user, extra: dict | None = None):
    from .insurance_standard_forms import form_title, standard_form_pdf

    extra = extra or {}
    pdf = standard_form_pdf(policy, form_key, extra)
    title = form_title(form_key)
    holder = (extra.get("holder_name") or "")[:200]
    issued = InsuranceIssuedForm.objects.create(
        policy=policy,
        form_key=form_key,
        title=title[:160],
        holder_name=holder,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    filename = f"{form_key}-{issued.id}.pdf"
    issued.file.save(filename, ContentFile(pdf), save=True)
    InsurancePolicyDocument.objects.create(
        policy=policy,
        document_type=InsurancePolicyDocument.DocumentType.OTHER,
        title=f"{title}"[:200] if not holder else f"{title} — {holder}"[:200],
        file=ContentFile(pdf, name=filename),
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
    )
    return issued


def notify_client(policy, user, body: str) -> str:
    """Log the message in the client app and email it when the client has an address."""
    from django.core.mail import EmailMessage

    from .email_branding import outbound_from_email
    from .insurance_renewals import email_problem
    from .models import ClientChatMessage

    text = (body or "").strip()
    if not text or not policy.client_id:
        return "Write a message first."
    ClientChatMessage.objects.create(
        organization=policy.organization,
        client=policy.client,
        sender_role=ClientChatMessage.SenderRole.STAFF,
        staff_user=user if getattr(user, "is_authenticated", False) else None,
        body=text[:5000],
        is_read_by_staff=True,
    )
    problem = email_problem(policy.client)
    if problem:
        return "Saved in the client app. No email was sent."
    try:
        EmailMessage(
            f"Message from your agency about policy {policy.policy_number}",
            text,
            from_email=outbound_from_email() or None,
            to=[policy.client.email.strip()],
        ).send(fail_silently=False)
    except Exception:
        return "Saved in the client app. Email could not be sent."
    return "Sent to the client app and by email."


def desk_today(organization, user, *, mine: bool) -> dict:
    policies = InsurancePolicy.objects.filter(organization=organization)
    if mine:
        policies = policies.filter(added_by=user)
    policy_ids = policies.values("id")
    claims = list(
        InsuranceClaim.objects.filter(policy_id__in=policy_ids)
        .exclude(status=InsuranceClaim.Status.CLOSED)
        .select_related("policy", "policy__client")
        .order_by("-loss_date")[:8]
    )
    certificates = list(
        InsuranceCertificate.objects.filter(
            policy_id__in=policy_ids,
            status=InsuranceCertificate.Status.REQUESTED,
        )
        .select_related("policy", "policy__client", "holder")
        .order_by("created_at")[:8]
    )
    sr22 = list(
        InsurancePolicyDriver.objects.filter(
            policy_id__in=policy_ids,
            sr22_required=True,
            sr22_filed_on__isnull=True,
            policy__status=InsurancePolicy.StatusChoices.ACTIVE,
        )
        .select_related("policy", "policy__client")
        .order_by("name")[:8]
    )
    reviews = list(
        policies.filter(coverages_need_review=True, client__isnull=False)
        .select_related("client")
        .order_by("-updated_at")[:8]
    )
    return {
        "coverage_reviews": reviews,
        "coverage_review_count": policies.filter(coverages_need_review=True, client__isnull=False).count(),
        "claims": claims,
        "claim_count": InsuranceClaim.objects.filter(policy_id__in=policy_ids).exclude(status=InsuranceClaim.Status.CLOSED).count(),
        "certificates": certificates,
        "certificate_count": InsuranceCertificate.objects.filter(
            policy_id__in=policy_ids, status=InsuranceCertificate.Status.REQUESTED
        ).count(),
        "sr22": sr22,
        "sr22_count": InsurancePolicyDriver.objects.filter(
            policy_id__in=policy_ids,
            sr22_required=True,
            sr22_filed_on__isnull=True,
            policy__status=InsurancePolicy.StatusChoices.ACTIVE,
        ).count(),
    }


def recent_statements(organization, limit=8):
    return list(
        InsuranceCommissionStatement.objects.filter(organization=organization)
        .prefetch_related("lines")
        .order_by("-created_at")[:limit]
    )


def coverage_form_rows(policy) -> list[dict]:
    found = {row.code: row for row in policy.coverages.filter(vehicle__isnull=True)}
    rows = []
    for code, label in InsuranceCoverage.Code.choices:
        row = found.get(code)
        rows.append(
            {
                "code": code,
                "label": label,
                "limit": row.limit_text if row else "",
                "deductible": "" if row is None or row.deductible is None else f"{row.deductible:.2f}",
            }
        )
    return rows


def client_coverages(policy) -> list[dict]:
    rows = []
    for row in policy.coverages.all():
        rows.append(
            {
                "code": row.code,
                "label": row.get_code_display(),
                "limit": row.limit_text,
                "deductible": f"{row.deductible:.2f}" if row.deductible is not None else None,
                "vehicle_id": row.vehicle_id,
            }
        )
    return rows


def client_claims(policy) -> list[dict]:
    return [
        {
            "id": claim.id,
            "loss_date": claim.loss_date.isoformat(),
            "description": claim.description,
            "other_party": claim.other_party,
            "police_report": claim.police_report,
            "carrier_claim_number": claim.carrier_claim_number,
            "status": claim.status,
            "status_display": claim.get_status_display(),
        }
        for claim in policy.claims.all()[:20]
    ]
