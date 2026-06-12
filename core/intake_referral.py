"""Link intake dealer/referral partner selections to client profiles on approval."""

from .client_referral import uses_referral_partner
from .models import Referral


def resolve_intake_referral(intake):
    """
    Return the Referral partner for this intake, creating one when the client
    submitted new dealer details. Returns None when not applicable.
    """
    if not uses_referral_partner(intake.source):
        return None

    if intake.selected_referral_id:
        return intake.selected_referral

    name = (intake.partner_name or "").strip()
    if not name:
        return None

    referral = Referral.objects.filter(
        organization_id=intake.organization_id,
        name__iexact=name,
    ).first()
    if referral:
        return referral

    return Referral.objects.create(
        organization_id=intake.organization_id,
        name=name,
        category="dealer",
        address=(intake.partner_address or "").strip(),
        phone_no=(intake.partner_phone or "").strip(),
        email=(intake.partner_email or "").strip() or None,
    )


def apply_intake_referral_to_client(intake, client):
    """Attach resolved dealer/referral partner to the client profile."""
    referral = resolve_intake_referral(intake)
    if referral:
        client.referral = referral
        client.save(update_fields=["referral"])
    return referral
