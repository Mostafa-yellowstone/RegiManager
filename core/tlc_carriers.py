"""TLC carrier name lists and registry helpers."""

from __future__ import annotations

from .tlc_models import (
    TLCCarrier,
    TLCCarrierCommissionRule,
    TLCCarrierStatement,
    TLCPolicy,
)


def get_tlc_carrier_names(organization_id: int) -> list[str]:
    """Return sorted unique carrier names for an organization."""
    names: set[str] = set()
    names.update(
        TLCCarrier.objects.filter(organization_id=organization_id, is_active=True).values_list(
            "name", flat=True
        )
    )
    names.update(
        TLCPolicy.objects.filter(organization_id=organization_id)
        .exclude(carrier="")
        .values_list("carrier", flat=True)
    )
    names.update(
        TLCCarrierCommissionRule.objects.filter(organization_id=organization_id)
        .exclude(carrier="")
        .values_list("carrier", flat=True)
    )
    names.update(
        TLCCarrierStatement.objects.filter(organization_id=organization_id)
        .exclude(carrier="")
        .values_list("carrier", flat=True)
    )
    return sorted((name.strip() for name in names if name and name.strip()), key=str.casefold)


def ensure_tlc_carrier(organization, name: str) -> TLCCarrier | None:
    """Persist a carrier name on the organization's registry."""
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    carrier, _created = TLCCarrier.objects.get_or_create(
        organization=organization,
        name=cleaned,
        defaults={"is_active": True},
    )
    if not carrier.is_active:
        carrier.is_active = True
        carrier.save(update_fields=["is_active"])
    return carrier
