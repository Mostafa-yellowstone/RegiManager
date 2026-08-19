"""Send a selected Regi Rater quote into the existing Quote Pipeline. Not a second pipeline."""

from __future__ import annotations

from django.core.exceptions import ValidationError

from core.insurance_quote_distribution import assign_lead
from core.insurance_quote_pipeline_models import InsuranceQuoteLead
from core.models import OrganizationMembership

from regiconnect.integrations import _apply_canonical_to_lead
from regiconnect.models import CanonicalQuote, QuoteLeadConnectivity
from regiconnect.runtime import audit, enqueue_outbox


def select_quote(quote: CanonicalQuote, *, actor=None) -> InsuranceQuoteLead:
    if quote.rating_request_id is None:
        raise ValidationError("This quote is not part of a Regi Rater session.")
    request = quote.rating_request
    if quote.organization_id != request.organization_id:
        raise ValidationError("Quote does not belong to this rating request.")

    CanonicalQuote.objects.filter(rating_request=request, status=CanonicalQuote.Status.SELECTED).exclude(
        pk=quote.pk
    ).update(status=CanonicalQuote.Status.QUOTED)
    quote.status = CanonicalQuote.Status.SELECTED
    quote.save(update_fields=["status", "updated_at"])

    snapshot = request.canonical_snapshot or {}
    lead = request.quote_lead
    if lead is None:
        name = snapshot.get("name") or (request.client.name if request.client_id else "Regi Rater quote")
        phone = (request.client.phone_number if request.client_id else "") or "0000000000"
        email = getattr(request.client, "email", "") if request.client_id else ""
        notes = "Selected from Regi Rater."
        if quote.quote_source == CanonicalQuote.QuoteSource.MOCK:
            notes += " MOCK / TEST — not a real carrier premium."
        if quote.premium_class == CanonicalQuote.PremiumClass.ESTIMATED:
            notes += " Premium is estimated, not a bindable final rate."
        lead = InsuranceQuoteLead.objects.create(
            organization=request.organization,
            client_name=str(name)[:200],
            phone=str(phone)[:30],
            email=email or "",
            state=request.state or "NY",
            insurance_type=request.line_of_business or "",
            stage=InsuranceQuoteLead.Stage.QUOTED,
            notes=notes,
        )
        _apply_canonical_to_lead(lead, snapshot)
        request.quote_lead = lead
        request.save(update_fields=["quote_lead", "updated_at"])
        if actor is not None and getattr(actor, "pk", None):
            membership = OrganizationMembership.objects.filter(
                organization=request.organization,
                user_id=actor.pk,
                is_active=True,
            ).first()
            if membership:
                try:
                    assign_lead(lead, membership, actor=actor, mode=InsuranceQuoteLead.AssignmentMode.MANUAL)
                except Exception:
                    pass
    else:
        if lead.stage in {
            InsuranceQuoteLead.Stage.NEW,
            InsuranceQuoteLead.Stage.ASSIGNED,
            InsuranceQuoteLead.Stage.QUOTING,
        }:
            lead.stage = InsuranceQuoteLead.Stage.QUOTED
            lead.save(update_fields=["stage", "updated_at"])

    QuoteLeadConnectivity.objects.update_or_create(
        lead=lead,
        defaults={
            "submission": quote.submission,
            "market": quote.market,
            "quote": quote,
            "quote_source": QuoteLeadConnectivity.QuoteSource.REGI_RATER,
            "premium": quote.premium,
            "external_reference": quote.external_reference,
            "connectivity_status": "selected",
        },
    )
    audit(
        organization=quote.organization,
        action="quote_selected",
        actor=actor,
        resource_type="CanonicalQuote",
        resource_id=quote.id,
        correlation_id=request.correlation_id,
        after={"lead_id": lead.id, "quote_source": quote.quote_source, "premium_class": quote.premium_class},
    )
    enqueue_outbox(
        organization=quote.organization,
        event_type="QuoteSelected",
        payload={"quote_id": quote.id, "lead_id": lead.id, "rating_request_id": request.id},
        aggregate_type="CanonicalQuote",
        aggregate_id=quote.id,
        correlation_id=request.correlation_id,
    )
    return lead
