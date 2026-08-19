"""Push RegiConnect results into existing Quote Pipeline, Policy, and Finance."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from core.insurance_quote_distribution import assign_lead
from core.insurance_quote_pipeline_models import InsuranceQuoteLead
from core.models import Client, DailyPaymentTransaction, InsurancePolicy

from .models import (
    BindTransaction,
    CanonicalQuote,
    DocumentExchange,
    PolicyConnectivity,
    QuoteLeadConnectivity,
)
from .runtime import audit


def ingest_quote(quote: CanonicalQuote) -> InsuranceQuoteLead:
    submission = quote.submission
    lead = submission.quote_lead
    if lead is None:
        name = (submission.canonical_payload or {}).get("name") or (
            submission.client.name if submission.client_id else "RegiConnect quote"
        )
        phone = "0000000000"
        email = ""
        if submission.client_id:
            phone = (submission.client.phone_number or phone)[:30]
            email = getattr(submission.client, "email", "") or ""
        lead = InsuranceQuoteLead.objects.create(
            organization=submission.organization,
            client_name=name[:200],
            phone=phone,
            email=email,
            state=submission.state or "NY",
            insurance_type=submission.line_of_business or "",
            stage=InsuranceQuoteLead.Stage.QUOTED,
            notes="Created from RegiConnect quote.",
        )
        submission.quote_lead = lead
        submission.save(update_fields=["quote_lead", "updated_at"])
        if submission.created_by_id:
            try:
                from core.models import OrganizationMembership

                membership = OrganizationMembership.objects.filter(
                    organization=submission.organization,
                    user_id=submission.created_by_id,
                    is_active=True,
                ).first()
                if membership:
                    assign_lead(lead, membership, actor=submission.created_by, mode=InsuranceQuoteLead.AssignmentMode.MANUAL)
            except Exception:
                pass
    else:
        if lead.stage in {InsuranceQuoteLead.Stage.NEW, InsuranceQuoteLead.Stage.ASSIGNED, InsuranceQuoteLead.Stage.QUOTING}:
            lead.stage = InsuranceQuoteLead.Stage.QUOTED
            lead.save(update_fields=["stage", "updated_at"])

    QuoteLeadConnectivity.objects.update_or_create(
        lead=lead,
        defaults={
            "submission": submission,
            "market": quote.market,
            "quote": quote,
            "quote_source": QuoteLeadConnectivity.QuoteSource.REGI_CONNECT,
            "premium": quote.premium,
            "external_reference": quote.external_reference,
            "connectivity_status": "quoted",
        },
    )
    audit(
        organization=quote.organization,
        action="quote_ingested_pipeline",
        resource_type="InsuranceQuoteLead",
        resource_id=lead.id,
        correlation_id=submission.correlation_id,
    )
    return lead


def ingest_bind(bind: BindTransaction, *, policy_number: str) -> InsurancePolicy:
    submission = bind.submission
    client = submission.client
    if client is None:
        client = Client.objects.create(
            organization=submission.organization,
            first_name=(submission.canonical_payload or {}).get("name") or "RegiConnect",
            last_name="Insured",
        )
        submission.client = client
        submission.save(update_fields=["client", "updated_at"])

    company = submission.market.company
    start = bind.quote.effective_date or date.today()
    end = bind.quote.expiration_date or (start + timedelta(days=180))
    policy = InsurancePolicy.objects.create(
        organization=submission.organization,
        client=client,
        policy_number=(policy_number or f"RC-{bind.id}")[:100],
        insurance_company=company,
        premium=bind.quote.premium,
        broker_fee=Decimal("0.00"),
        commission_rate=Decimal("0.00"),
        insurance_type=(submission.line_of_business or "auto_personal")[:30],
        stage=InsurancePolicy.StageChoices.BOUND,
        status=InsurancePolicy.StatusChoices.ACTIVE,
        bound_date=date.today(),
        start_date=start,
        end_date=end,
        added_by=submission.created_by,
    )
    PolicyConnectivity.objects.update_or_create(
        policy=policy,
        defaults={
            "submission": submission,
            "bind": bind,
            "external_policy_number": policy_number,
            "carrier_reference": bind.external_reference,
            "last_sync_at": timezone.now(),
            "connectivity_status": "bound",
        },
    )
    if submission.quote_lead_id:
        QuoteLeadConnectivity.objects.update_or_create(
            lead_id=submission.quote_lead_id,
            defaults={
                "submission": submission,
                "market": submission.market,
                "quote": bind.quote,
                "quote_source": QuoteLeadConnectivity.QuoteSource.REGI_CONNECT,
                "premium": bind.quote.premium,
                "external_reference": bind.external_reference,
                "connectivity_status": "bound",
            },
        )
        lead = submission.quote_lead
        lead.stage = InsuranceQuoteLead.Stage.WON
        lead.save(update_fields=["stage", "updated_at"])

    DailyPaymentTransaction.objects.create(
        organization=submission.organization,
        client=client,
        insurance_policy=policy,
        insurance_company=company,
        transaction_date=date.today(),
        amount=bind.quote.premium,
        payment_type=DailyPaymentTransaction.PaymentType.NEW_BUSINESS,
        payment_method=DailyPaymentTransaction.PaymentMethod.CASH,
        recorded_by=submission.created_by,
        notes=f"RegiConnect bind {bind.id} (correlation {bind.correlation_id})",
    )
    audit(
        organization=bind.organization,
        action="policy_bound",
        resource_type="InsurancePolicy",
        resource_id=policy.id,
        correlation_id=bind.correlation_id,
    )
    return policy


def store_documents(submission, docs: list) -> None:
    for item in docs:
        DocumentExchange.objects.create(
            organization=submission.organization,
            submission=submission,
            doc_type=str(item.get("doc_type") or "other")[:40],
            external_reference=str(item.get("external_reference") or ""),
        )
