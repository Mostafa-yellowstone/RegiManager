"""Shared referral linking logic for add/edit client flows."""

from .models import Referral
from .source_choices import norm_source

REFERRAL_SOURCE_KEYS = frozenset({"dealer", "referral"})


def uses_referral_partner(source):
    """True when source should open the referral-space partner picker."""
    return norm_source(source) in REFERRAL_SOURCE_KEYS


def preferred_referral_category(source):
    """Default category when creating a new partner from a source choice."""
    key = norm_source(source)
    if key == "dealer":
        return "dealer"
    if key == "referral":
        return "customer"
    return "dealer"


def build_referral_partner_choices(
    organizations,
    *,
    blank_label="--- Select partner ---",
    include_new=True,
    new_label="+ Create New Partner",
    current_referral=None,
):
    """
    All referral-space entities for partner pickers (not dealer-only).
    Option labels include category so dealers, brokers, etc. are distinguishable.
    """
    choices = [("", blank_label)]
    seen_ids = set()
    if organizations is not None and getattr(organizations, "exists", lambda: False)():
        referrals = (
            Referral.objects.filter(organization__in=organizations)
            .order_by("name", "category")
        )
        for partner in referrals:
            seen_ids.add(partner.id)
            choices.append(
                (str(partner.id), f"{partner.name} ({partner.get_category_display()})")
            )
    if current_referral and current_referral.id not in seen_ids:
        choices.insert(
            1,
            (
                str(current_referral.id),
                f"{current_referral.name} ({current_referral.get_category_display()})",
            ),
        )
    if include_new:
        choices.append(("new", new_label))
    return choices


def apply_referral_id_to_client(client, referral_id, *, organization, source):
    """Attach an existing Referral Space partner when source is dealer/referral."""
    if not uses_referral_partner(source):
        return client
    raw = (referral_id or "").strip()
    if not raw.isdigit():
        return client
    partner = Referral.objects.filter(id=int(raw), organization=organization).first()
    if partner:
        client.referral = partner
        client.save(update_fields=["referral"])
    return client


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
                category=(
                    form.cleaned_data.get("referral_category")
                    or preferred_referral_category(source)
                ),
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
