"""Duplicate detection for public intake submissions and approvals."""

from __future__ import annotations

import re
from typing import Any

from .models import Client, ClientIntake, Vehicle

ACTIVE_INTAKE_STATUSES = (
    ClientIntake.Status.PENDING,
    ClientIntake.Status.PROCESSING,
)


def normalize_phone_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _client_queryset(organization):
    return Client.objects.filter(organization=organization)


def _intake_field(data, field: str, default=""):
    if hasattr(data, field):
        return getattr(data, field) or default
    if isinstance(data, dict):
        return data.get(field) or default
    return default


def _is_commercial(data) -> bool:
    return bool(_intake_field(data, "is_commercial", False))


def find_existing_client_for_intake(intake) -> Client | None:
    """
    Match intake to an existing client using strong identifiers.

    Blank driver license must not match arbitrary profiles.
    """
    qs = _client_queryset(intake.organization)

    if intake.is_commercial:
        ein = (intake.business_ein or "").strip()
        if ein:
            match = qs.filter(is_commercial=True, business_ein__iexact=ein).first()
            if match:
                return match
        business_name = (intake.business_name or "").strip()
        if not business_name and (intake.first_name or "").strip().lower() == "commercial":
            business_name = (intake.last_name or "").strip()
        if business_name:
            return qs.filter(is_commercial=True, business_name__iexact=business_name).first()
        return None

    dl = (intake.driver_license or "").strip()
    if dl:
        match = qs.filter(driver_license__iexact=dl, is_commercial=False).first()
        if match:
            return match

    email = (intake.email or "").strip()
    if email:
        match = qs.filter(email__iexact=email, is_commercial=False).first()
        if match:
            return match

    phone_digits = normalize_phone_digits(intake.phone_number)
    if len(phone_digits) >= 10:
        for client in qs.filter(is_commercial=False).only("id", "phone_number"):
            if normalize_phone_digits(client.phone_number) == phone_digits:
                return client

    first_name = (intake.first_name or "").strip()
    last_name = (intake.last_name or "").strip()
    if first_name and last_name and intake.dob:
        match = qs.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
            dob=intake.dob,
            is_commercial=False,
        ).first()
        if match:
            return match

    if first_name and last_name:
        return qs.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
            is_commercial=False,
        ).first()

    return None


def find_pending_intake_duplicate(
    organization,
    data,
    *,
    exclude_intake_id: int | None = None,
) -> ClientIntake | None:
    """Return an active intake that looks like the same submission."""
    qs = ClientIntake.objects.filter(
        organization=organization,
        status__in=ACTIVE_INTAKE_STATUSES,
    )
    if exclude_intake_id:
        qs = qs.exclude(pk=exclude_intake_id)

    vin = (_intake_field(data, "vin") or "").strip()
    if vin:
        match = qs.filter(vin__iexact=vin).first()
        if match:
            return match

    if _is_commercial(data):
        ein = (_intake_field(data, "business_ein") or "").strip()
        if ein:
            match = qs.filter(is_commercial=True, business_ein__iexact=ein).first()
            if match:
                return match
        business_name = (_intake_field(data, "business_name") or "").strip()
        if business_name:
            return qs.filter(is_commercial=True, business_name__iexact=business_name).first()
        return None

    dl = (_intake_field(data, "driver_license") or "").strip()
    if dl:
        match = qs.filter(driver_license__iexact=dl).first()
        if match:
            return match

    email = (_intake_field(data, "email") or "").strip()
    if email:
        match = qs.filter(email__iexact=email).first()
        if match:
            return match

    phone_digits = normalize_phone_digits(_intake_field(data, "phone_number"))
    if len(phone_digits) >= 10:
        for intake in qs.only("id", "phone_number"):
            if normalize_phone_digits(intake.phone_number) == phone_digits:
                return intake

    first_name = (_intake_field(data, "first_name") or "").strip()
    last_name = (_intake_field(data, "last_name") or "").strip()
    dob = _intake_field(data, "dob", None)
    if first_name and last_name and dob:
        match = qs.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
            dob=dob,
        ).first()
        if match:
            return match

    if first_name and last_name and phone_digits:
        match = qs.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
        ).first()
        if match and normalize_phone_digits(match.phone_number) == phone_digits:
            return match

    return None


class _IntakeIdentity:
    """Lightweight adapter so form dicts can reuse client matching."""

    def __init__(self, data: Any, organization=None):
        self.organization = organization or (
            data.organization if hasattr(data, "organization") else None
        )
        self.is_commercial = _is_commercial(data)
        self.business_name = _intake_field(data, "business_name")
        self.business_ein = _intake_field(data, "business_ein")
        self.driver_license = _intake_field(data, "driver_license")
        self.email = _intake_field(data, "email")
        self.phone_number = _intake_field(data, "phone_number")
        self.first_name = _intake_field(data, "first_name")
        self.last_name = _intake_field(data, "last_name")
        self.dob = _intake_field(data, "dob", None)


def validate_intake_submission(organization, data) -> str | None:
    """
    Return a user-facing error when a duplicate intake should be blocked.

    Returning customers may submit a new vehicle, but not the same VIN twice
    and not while another application is already pending.
    """
    vin = (_intake_field(data, "vin") or "").strip()
    pending = find_pending_intake_duplicate(organization, data)
    if pending:
        if vin and (pending.vin or "").strip().upper() == vin.upper():
            return (
                "An application for this vehicle is already being reviewed. "
                "Please contact the office if you need to make changes."
            )
        return (
            "You already submitted an application that is being reviewed. "
            "Please contact the office instead of submitting again."
        )

    existing_client = find_existing_client_for_intake(_IntakeIdentity(data, organization))
    if not existing_client:
        return None

    if existing_client.is_commercial:
        if vin:
            has_vehicle = Vehicle.objects.filter(
                client=existing_client,
                vin__iexact=vin,
            ).exists()
            if has_vehicle:
                return (
                    "This vehicle is already on file for this business. "
                    "Please contact the office if you need help with your registration."
                )
        return (
            "A business profile matching this information is already in our system. "
            "Please contact the office instead of submitting a new application."
        )

    if vin:
        has_vehicle = Vehicle.objects.filter(
            client=existing_client,
            vin__iexact=vin,
        ).exists()
        if has_vehicle:
            return (
                "This vehicle is already on file for your profile. "
                "Please contact the office if you need help with your registration."
            )

    return (
        "A profile matching your information is already in our system. "
        "Please contact the office instead of submitting a new application."
    )


def validate_intake_submission_from_form(organization, cleaned_data) -> str | None:
    from types import SimpleNamespace

    payload = SimpleNamespace(
        organization=organization,
        is_commercial=bool(cleaned_data.get("is_commercial")),
        business_name=cleaned_data.get("business_name", ""),
        business_ein=cleaned_data.get("business_ein", ""),
        driver_license=cleaned_data.get("driver_license", ""),
        email=cleaned_data.get("email"),
        phone_number=cleaned_data.get("phone_number", ""),
        first_name=cleaned_data.get("first_name", ""),
        last_name=cleaned_data.get("last_name", ""),
        dob=cleaned_data.get("dob"),
        vin=cleaned_data.get("vin", ""),
    )
    return validate_intake_submission(organization, payload)
