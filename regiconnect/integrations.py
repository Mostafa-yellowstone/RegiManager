"""Push RegiConnect results into existing Quote Pipeline, Policy, and Finance."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from core.insurance_quote_distribution import assign_lead
from core.insurance_quote_pipeline_models import InsuranceQuoteLead
from core.models import Client, DailyPaymentTransaction, InsurancePolicy, InsurancePolicyDriver, InsurancePolicyVehicle

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
        _apply_canonical_to_lead(lead, submission.canonical_payload or {})
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
    _copy_canonical_onto_policy(policy, submission.canonical_payload or {}, start, end)
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


def _apply_canonical_to_lead(lead, payload: dict) -> None:
    driver = payload.get("driver") or {}
    vehicle = payload.get("vehicle") or {}
    risk = payload.get("risk") or {}
    coverage = payload.get("coverage") or {}
    fields = []
    if not lead.dl_number and driver.get("driver_license"):
        lead.dl_number = str(driver["driver_license"])[:40]
        fields.append("dl_number")
    if not lead.date_of_birth and driver.get("dob"):
        raw = driver["dob"]
        parsed = raw if hasattr(raw, "year") else None
        if parsed is None:
            try:
                parsed = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
            except ValueError:
                parsed = None
        if parsed:
            lead.date_of_birth = parsed
            fields.append("date_of_birth")
    if not lead.vin and vehicle.get("vin"):
        lead.vin = str(vehicle["vin"])[:32]
        fields.append("vin")
    if not lead.vehicle_year and vehicle.get("year"):
        lead.vehicle_year = str(vehicle["year"])[:4]
        fields.append("vehicle_year")
    if not lead.vehicle_make and vehicle.get("make"):
        lead.vehicle_make = str(vehicle["make"])[:80]
        fields.append("vehicle_make")
    if not lead.vehicle_model and vehicle.get("model"):
        lead.vehicle_model = str(vehicle["model"])[:80]
        fields.append("vehicle_model")
    if not lead.coverage_type and coverage.get("type"):
        lead.coverage_type = str(coverage["type"])[:20]
        fields.append("coverage_type")
    if risk.get("has_accident") and not lead.has_accident:
        lead.has_accident = True
        fields.append("has_accident")
    if risk.get("has_prior") and not lead.has_prior:
        lead.has_prior = True
        fields.append("has_prior")
    addr = driver.get("address") or {}
    if not lead.zip_code and addr.get("zip_code"):
        lead.zip_code = str(addr["zip_code"])[:10]
        fields.append("zip_code")
    if not lead.city and addr.get("city"):
        lead.city = str(addr["city"])[:100]
        fields.append("city")
    if not lead.street_address and addr.get("street"):
        lead.street_address = str(addr["street"])[:200]
        fields.append("street_address")
    if fields:
        lead.save(update_fields=fields + ["updated_at"])


def _copy_canonical_onto_policy(policy, payload: dict, start, end) -> None:
    vehicle = payload.get("vehicle") or {}
    driver = payload.get("driver") or {}
    if vehicle.get("vin") or vehicle.get("make") or vehicle.get("year"):
        year = vehicle.get("year")
        try:
            year_int = int(year) if year else None
        except (TypeError, ValueError):
            year_int = None
        InsurancePolicyVehicle.objects.create(
            policy=policy,
            auto_number=1,
            year=year_int,
            make=(vehicle.get("make") or "")[:60],
            vin=(vehicle.get("vin") or "")[:17],
            plate_number=(vehicle.get("plate_number") or "")[:50],
            effective_date=start,
            expiration_date=end,
        )
    auto_n = 2
    for extra in payload.get("additional_vehicles") or []:
        if not (extra.get("vin") or extra.get("make") or extra.get("year")):
            continue
        try:
            extra_year = int(extra.get("year")) if extra.get("year") else None
        except (TypeError, ValueError):
            extra_year = None
        InsurancePolicyVehicle.objects.create(
            policy=policy,
            auto_number=auto_n,
            year=extra_year,
            make=(extra.get("make") or "")[:60],
            vin=(extra.get("vin") or "")[:17],
            plate_number=(extra.get("plate_number") or "")[:50],
            effective_date=start,
            expiration_date=end,
        )
        auto_n += 1
    name = driver.get("name") or payload.get("name") or ""
    if name:
        InsurancePolicyDriver.objects.create(
            policy=policy,
            name=str(name)[:200],
            effective_date=start,
            expiry_date=end,
        )
    for extra in payload.get("additional_drivers") or []:
        extra_name = extra.get("name") or extra.get("driver_license")
        if extra_name:
            InsurancePolicyDriver.objects.create(
                policy=policy,
                name=str(extra_name)[:200],
                effective_date=start,
                expiry_date=end,
            )


def store_documents(submission, docs: list) -> None:
    for item in docs:
        DocumentExchange.objects.create(
            organization=submission.organization,
            submission=submission,
            doc_type=str(item.get("doc_type") or "other")[:40],
            external_reference=str(item.get("external_reference") or ""),
        )
