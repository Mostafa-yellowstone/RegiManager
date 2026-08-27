"""RegiManager Core admin registrations, grouped for clarity in the admin UI."""

from . import clients, insurance, inventory, motorclub, organization, referrals, services, spaces, tlc
from .site import patch_admin_site

patch_admin_site()

__all__ = [
    "clients",
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
