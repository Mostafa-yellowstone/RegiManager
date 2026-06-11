"""Shared referral linking logic for add/edit client flows."""

from .models import Referral
from .source_choices import norm_source

REFERRAL_SOURCE_KEYS = frozenset({"referral", "dealer"})


def uses_referral_partner(source):
    return norm_source(source) in REFERRAL_SOURCE_KEYS


def apply_client_referral_from_form(client, form, *, is_edit=False):
    """
    Link or create a Referral partner from ClientForm cleaned data.
    On edit, preserve an existing referral unless the user picks a new one.
    """
    source = form.cleaned_data.get("source")
    if not uses_referral_partner(source):
        if not is_edit:
            client.referral = None
        return

    referral_select = (form.cleaned_data.get("referral_select") or "").strip()
    if referral_select and referral_select != "new":
        try:
            client.referral = Referral.objects.get(
                id=int(referral_select),
                organization=client.organization,
            )
        except (Referral.DoesNotExist, ValueError, TypeError):
            if not is_edit:
                client.referral = None
        return

    referral_name = (form.cleaned_data.get("referral_name") or "").strip()
    if referral_name:
        referral = Referral.objects.filter(
            organization=client.organization,
            name__iexact=referral_name,
        ).first()
        if not referral:
            referral = Referral.objects.create(
                organization=client.organization,
                name=referral_name,
                category=form.cleaned_data.get("referral_category") or "dealer",
                address=form.cleaned_data.get("referral_address") or "",
                phone_no=form.cleaned_data.get("referral_phone_no") or "",
                email=form.cleaned_data.get("referral_email") or "",
                website=form.cleaned_data.get("referral_website") or "",
                initial_balance=form.cleaned_data.get("referral_balance") or 0,
            )
        client.referral = referral
        return

    if not is_edit:
        client.referral = None
