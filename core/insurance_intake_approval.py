"""Approve insurance intakes into clients and quote-stage policies."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .models import Client, ClientNote, InsuranceCompany, InsuranceIntake, InsurancePolicy


def _default_insurance_company(organization):
    company = InsuranceCompany.objects.filter(organization=organization).order_by("name").first()
    if company:
        return company
    return InsuranceCompany.objects.create(
        organization=organization,
        name="Intake — Assign Carrier",
    )


def _find_existing_client(intake: InsuranceIntake):
    qs = Client.objects.filter(organization=intake.organization)
    if intake.email:
        match = qs.filter(email__iexact=intake.email.strip()).first()
        if match:
            return match
    if intake.phone_number:
        match = qs.filter(phone_number=intake.phone_number.strip()).first()
        if match:
            return match
    return qs.filter(
        first_name__iexact=intake.first_name.strip(),
        last_name__iexact=intake.last_name.strip(),
    ).first()


def approve_insurance_intake(intake: InsuranceIntake, user):
    client = intake.created_client or _find_existing_client(intake)
    if not client:
        client = Client.objects.create(
            organization=intake.organization,
            first_name=intake.first_name,
            last_name=intake.last_name,
            email=intake.email or "",
            phone_number=intake.phone_number,
            dob=intake.dob,
            driver_license=intake.driver_license,
            street_address=intake.street_address,
            city=intake.city,
            state=intake.state,
            zip_code=intake.zip_code,
            source=intake.source,
        )

    if intake.business_name and not client.business_name:
        client.business_name = intake.business_name
        client.save(update_fields=["business_name"])

    effective = intake.requested_effective_date or timezone.localdate()
    end_date = effective + timedelta(days=183)

    policy_number = f"INTAKE-{intake.id}"
    if intake.prior_policy_number:
        policy_number = intake.prior_policy_number[:100]

    company = _default_insurance_company(intake.organization)
    policy = InsurancePolicy.objects.create(
        organization=intake.organization,
        client=client,
        policy_number=policy_number,
        insurance_company=company,
        premium=Decimal("0.00"),
        broker_fee=Decimal("0.00"),
        commission_rate=Decimal("0.00"),
        stage=InsurancePolicy.StageChoices.QUOTE,
        status=InsurancePolicy.StatusChoices.PENDING,
        insurance_type=intake.insurance_type,
        source=intake.source,
        business_type=intake.business_type or InsurancePolicy.BusinessTypeChoices.NEW_BUSINESS,
        bound_date=effective,
        start_date=effective,
        end_date=end_date,
        insurance_period_months=6,
        added_by=user,
    )

    note_lines = []
    if intake.intake_note:
        note_lines.append(intake.intake_note.strip())
    vehicle_bits = [intake.vin, str(intake.year or ""), intake.make, intake.model]
    vehicle_summary = " ".join(part for part in vehicle_bits if part).strip()
    if vehicle_summary:
        note_lines.append(f"Vehicle: {vehicle_summary}")
    if intake.business_ein:
        note_lines.append(f"EIN: {intake.business_ein}")
    if intake.dot_number:
        note_lines.append(f"DOT: {intake.dot_number}")
    if intake.fleet_vehicle_count:
        note_lines.append(f"Fleet size: {intake.fleet_vehicle_count}")
    if intake.current_carrier:
        note_lines.append(f"Current carrier: {intake.current_carrier}")

    if note_lines:
        ClientNote.objects.create(
            client=client,
            content="\n".join(note_lines),
            created_by=user,
        )

    intake.status = InsuranceIntake.Status.APPROVED
    intake.processed_by = user
    intake.processed_at = timezone.now()
    intake.created_client = client
    intake.created_policy = policy
    intake.save()

    return client, policy
