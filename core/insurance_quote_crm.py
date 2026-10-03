"""Open a CRM policy when a quote lead is added, and keep its agent in sync."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .client_matching import DuplicateClientError, resolve_client_for_display_name
from .models import InsurancePolicy


def sync_quote_lead_to_crm(lead):
    """Create or update the CRM policy for this quote without copying the profile."""
    if lead is None or not lead.client_name or not lead.organization_id:
        return None
    try:
        client = resolve_client_for_display_name(
            lead.organization,
            lead.client_name,
            source="walk_in",
        )
    except DuplicateClientError:
        return None

    _fill_blank_client_fields(client, lead)
    agent_user = lead.assigned_to.user if lead.assigned_to_id else None
    policy = lead.crm_policy
    if policy is None:
        today = timezone.localdate()
        policy = InsurancePolicy(
            organization=lead.organization,
            client=client,
            policy_number=f"Q-{lead.id}",
            insurance_company=None,
            premium=Decimal("0.00"),
            broker_fee=None,
            commission_rate=None,
            commission_amount=None,
            stage=InsurancePolicy.StageChoices.QUOTE,
            status=InsurancePolicy.StatusChoices.PENDING,
            insurance_type=(lead.insurance_type or "")[:30],
            source=_policy_source(lead),
            business_type=InsurancePolicy.BusinessTypeChoices.NEW_BUSINESS,
            bound_date=today,
            start_date=today,
            end_date=today + timedelta(days=183),
            added_by=agent_user,
            named_insured=(lead.client_name or "")[:255],
            insured_address=_lead_address(lead)[:500],
            vin=(lead.vin or "")[:17],
            driver_name=(lead.client_name or "")[:200],
        )
        policy.save()
        lead.crm_policy = policy
        lead.save(update_fields=["crm_policy", "updated_at"])
        return policy

    policy.client = client
    policy.added_by = agent_user
    policy.named_insured = (lead.client_name or "")[:255]
    if lead.vin:
        policy.vin = lead.vin[:17]
    if lead.insurance_type:
        policy.insurance_type = lead.insurance_type[:30]
    policy.save()
    return policy


def _policy_source(lead) -> str:
    heard = (lead.heard_about or "").strip()
    allowed = {key for key, _label in InsurancePolicy.SourceChoices.choices}
    if heard in allowed:
        return heard
    return InsurancePolicy.SourceChoices.WALK_IN


def _lead_address(lead) -> str:
    parts = [
        lead.street_address,
        lead.apartment,
        lead.city,
        lead.state,
        lead.zip_code,
    ]
    return ", ".join(part for part in parts if part)


def _fill_blank_client_fields(client, lead):
    updates = []
    if lead.phone and not client.phone_number:
        client.phone_number = lead.phone[:20]
        updates.append("phone_number")
    if lead.email and not client.email:
        client.email = lead.email
        updates.append("email")
    if lead.street_address and not client.street_address:
        client.street_address = lead.street_address[:200]
        updates.append("street_address")
    if lead.apartment and not client.apartment:
        client.apartment = lead.apartment[:50]
        updates.append("apartment")
    if lead.city and not client.city:
        client.city = lead.city[:100]
        updates.append("city")
    if lead.state and not client.state:
        client.state = lead.state[:2]
        updates.append("state")
    if lead.zip_code and not client.zip_code:
        client.zip_code = lead.zip_code[:10]
        updates.append("zip_code")
    if lead.dl_number and not client.driver_license:
        client.driver_license = lead.dl_number[:50]
        updates.append("driver_license")
    if lead.date_of_birth and not client.dob:
        client.dob = lead.date_of_birth
        updates.append("dob")
    if updates:
        client.save(update_fields=updates)
