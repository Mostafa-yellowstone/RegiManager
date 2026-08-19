"""Versioned ACORD mapping stub — never invent a form a carrier did not document."""

from .exceptions import MissingCarrierSpec
from .models import AcordMapping, Connector


def map_canonical_to_acord(connector: Connector, transaction_type: str, canonical: dict) -> dict:
    mapping = AcordMapping.objects.filter(
        connector=connector, transaction_type=transaction_type
    ).first()
    if mapping is None:
        raise MissingCarrierSpec(
            f"No ACORD mapping for {connector.slug} / {transaction_type}. "
            "Do not invent an ACORD transaction without official documentation."
        )
    return {
        "acord_version": mapping.acord_version,
        "transaction_type": transaction_type,
        "canonical": canonical,
        "mapping": mapping.mapping,
    }
