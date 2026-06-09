"""HTTP helpers for consistent portal responses."""

from django.core.exceptions import PermissionDenied


def deny_access(message="Access denied."):
    """Raise permission denied so handler403 / middleware render the branded page."""
    raise PermissionDenied(message)
