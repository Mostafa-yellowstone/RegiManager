"""Sync TLC policy fields from CRM client/vehicle records."""

from __future__ import annotations

from .models import Client, Vehicle
from .tlc_models import TLCPolicy


def personal_name(client: Client) -> str:
    parts = [client.first_name, client.middle_name, client.last_name]
    return " ".join(part for part in parts if part).strip()


def apply_client_to_policy(policy: TLCPolicy, client: Client | None, vehicle: Vehicle | None = None) -> None:
    """Fill policy insured fields from CRM. CRM link is optional; policy legal names may differ."""
    if not client:
        return
    policy.client = client
    if client.is_commercial and client.business_name:
        policy.business_name = client.business_name
        policy.named_insured = personal_name(client) or client.business_name
    else:
        policy.named_insured = personal_name(client) or client.name
        if not policy.business_name:
            policy.business_name = client.business_name or ""
    if not policy.driver_name:
        policy.driver_name = policy.named_insured
    if vehicle:
        policy.vehicle = vehicle
        policy.vin = vehicle.vin or policy.vin
        policy.plate_number = vehicle.plate_number or policy.plate_number
