"""RegiManager Core admin registrations, grouped for clarity in the admin UI."""

from . import (
    carrier_credentials,
    clients,
    defense_driving,
    expenses,
    insurance,
    inventory,
    motorclub,
    organization,
    referrals,
    services,
    spaces,
    staff,
    tlc,
    licenses,
)
from .site import patch_admin_site

patch_admin_site()

__all__ = [
    "carrier_credentials",
    "clients",
    "defense_driving",
    "expenses",
    "insurance",
    "inventory",
    "motorclub",
    "organization",
    "referrals",
    "services",
    "spaces",
    "staff",
    "tlc",
    "licenses",
    "patch_admin_site",
]
