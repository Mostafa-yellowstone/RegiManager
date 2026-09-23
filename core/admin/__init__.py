"""RegiManager Core admin registrations, grouped for clarity in the admin UI."""

from . import (
    clients,
    defense_driving,
    insurance,
    inventory,
    motorclub,
    organization,
    referrals,
    services,
    spaces,
    tlc,
)
from .site import patch_admin_site

patch_admin_site()

__all__ = [
    "clients",
    "defense_driving",
    "insurance",
    "inventory",
    "motorclub",
    "organization",
    "referrals",
    "services",
    "spaces",
    "tlc",
    "patch_admin_site",
]
