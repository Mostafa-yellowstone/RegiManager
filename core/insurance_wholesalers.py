"""Wholesalers: carriers can be written direct or through one or more wholesalers."""

from __future__ import annotations

from .models import InsuranceCompany, InsuranceWholesaler


class WholesalerInputError(ValueError):
    pass


def wholesaler_for_policy(organization, company: InsuranceCompany | None, raw) -> InsuranceWholesaler | None:
    """The wholesaler picked for a policy, or None for a direct policy."""
    value = str(raw or "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise WholesalerInputError("Choose a valid wholesaler.")
    wholesaler = InsuranceWholesaler.objects.filter(organization=organization, id=int(value)).first()
    if wholesaler is None:
        raise WholesalerInputError("Choose a valid wholesaler.")
    if company is None or not company.wholesalers.filter(id=wholesaler.id).exists():
        raise WholesalerInputError(
            f"{company.name if company else 'This company'} is not listed under {wholesaler.name}."
        )
    return wholesaler


def save_wholesaler(organization, post, wholesaler: InsuranceWholesaler | None = None) -> InsuranceWholesaler:
    name = " ".join((post.get("name") or "").split())[:120]
    if not name:
        raise WholesalerInputError("Wholesaler name is required.")
    duplicate = InsuranceWholesaler.objects.filter(organization=organization, name__iexact=name)
    if wholesaler is not None:
        duplicate = duplicate.exclude(id=wholesaler.id)
    if duplicate.exists():
        raise WholesalerInputError(f"A wholesaler named {name} already exists.")
    wholesaler = wholesaler or InsuranceWholesaler(organization=organization)
    wholesaler.name = name
    wholesaler.contact_name = (post.get("contact_name") or "").strip()[:120]
    wholesaler.phone = (post.get("phone") or "").strip()[:40]
    wholesaler.email = (post.get("email") or "").strip()[:254]
    wholesaler.notes = (post.get("notes") or "").strip()[:500]
    wholesaler.save()
    company_ids = [value for value in post.getlist("companies") if str(value).isdigit()]
    wholesaler.companies.set(InsuranceCompany.objects.filter(organization=organization, id__in=company_ids))
    return wholesaler


def set_company_wholesalers(company: InsuranceCompany, post) -> None:
    ids = [value for value in post.getlist("wholesalers") if str(value).isdigit()]
    company.wholesalers.set(InsuranceWholesaler.objects.filter(organization=company.organization_id, id__in=ids))
