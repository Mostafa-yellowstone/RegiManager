"""RegiManager Core admin registrations, grouped for clarity in the admin UI."""

from . import clients, inventory, motorclub, organization, referrals, services, spaces
from .site import patch_admin_site

patch_admin_site()

__all__ = [
    "clients",
    "inventory",
    "motorclub",
    "organization",
    "referrals",
    "services",
    "spaces",
    "patch_admin_site",
]
