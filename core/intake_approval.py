"""Client and vehicle resolution when approving intake submissions."""

from .intake_duplicates import find_existing_client_for_intake
from .models import Vehicle


def intake_vehicle_for_client(intake, client):
    """Return the client's existing vehicle for this intake VIN, if any."""
    vin = (intake.vin or "").strip()
    if not vin:
        return None
    return Vehicle.objects.filter(client=client, vin=vin).first()


def client_profile_for_intake(intake):
    """Return the client profile created from an approved intake, when resolvable."""
    from .models import ClientIntake

    if intake.status != ClientIntake.Status.APPROVED:
        return None
    vin = (intake.vin or "").strip()
    if not vin:
        return None
    vehicle = (
        Vehicle.objects.filter(
            vin__iexact=vin,
            client__organization_id=intake.organization_id,
        )
        .select_related("client")
        .first()
    )
    return vehicle.client if vehicle else None


def attach_client_profiles_to_intakes(intakes):
    """Set linked_client on each approved intake (batch lookup, no N+1)."""
    from .models import ClientIntake

    intake_list = list(intakes)
    approved = [
        intake for intake in intake_list
        if intake.status == ClientIntake.Status.APPROVED and (intake.vin or "").strip()
    ]
    for intake in intake_list:
        intake.linked_client = None

    if not approved:
        return intake_list

    org_ids = {intake.organization_id for intake in approved}
    vins = {(intake.vin or "").strip().upper() for intake in approved}
    client_map = {}
    for vehicle in Vehicle.objects.filter(
        client__organization_id__in=org_ids,
    ).select_related("client"):
        key = (vehicle.client.organization_id, (vehicle.vin or "").strip().upper())
        if key[1] in vins:
            client_map[key] = vehicle.client

    for intake in approved:
        key = (intake.organization_id, (intake.vin or "").strip().upper())
        intake.linked_client = client_map.get(key)

    return intake_list


def vehicle_defaults_from_intake(intake):
    """Field map used when creating or updating a vehicle from intake."""
    return {
        "year": intake.year,
        "make": intake.make,
        "model": intake.model,
        "vehicle_type": intake.vehicle_type,
        "body_type": intake.body_type,
        "fuel_type": intake.fuel_type,
        "color": intake.color,
        "weight": intake.weight,
        "cylinders": intake.cylinders,
        "odometer_reading": intake.odometer_reading,
        "odometer_status": intake.odometer_status,
        "max_gross_weight": intake.max_gross_weight,
        "num_axles": intake.num_axles,
        "owner_name": intake.owner_name,
        "owner_nys_id": intake.owner_nys_id,
        "owner_dob": intake.owner_dob,
        "co_registrant_name": intake.co_registrant_name,
        "co_registrant_nys_id": intake.co_registrant_nys_id,
        "co_registrant_dob": intake.co_registrant_dob,
        "has_lien": intake.has_lien,
        "lienholder_name": intake.lienholder_name,
        "lienholder_address": intake.lienholder_address,
        "lien_filing_code": intake.lien_filing_code,
        "is_leased": intake.is_leased,
        "lessor_name": intake.lessor_name,
        "lessor_address": intake.lessor_address,
        "insurance_company": intake.insurance_company,
        "insurance_policy_number": intake.insurance_policy_number,
        "insurance_effective_date": intake.insurance_effective_date,
        "insurance_expiration_date": intake.insurance_expiration_date,
    }
