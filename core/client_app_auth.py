"""Authentication helpers for the client mobile wallet app."""

from __future__ import annotations

import re
import secrets

from django.db.models import Q
from django.utils import timezone
from rest_framework import authentication, exceptions, permissions
from rest_framework.throttling import AnonRateThrottle

from .models import Client, ClientAppSession, Organization


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D+", "", (raw or "").strip())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


def resolve_organization(*, portal_token: str = "", organization_id=None) -> Organization | None:
    token = (portal_token or "").strip()
    if token:
        return Organization.objects.filter(portal_token=token, is_active=True).first()
    if organization_id is not None and str(organization_id).isdigit():
        return Organization.objects.filter(id=int(organization_id), is_active=True).first()
    return None


def find_client_for_login(
    org: Organization,
    *,
    phone: str = "",
    email: str = "",
    require_enabled: bool = True,
) -> Client | None:
    qs = Client.objects.filter(organization=org)
    if require_enabled:
        qs = qs.filter(app_access_enabled=True)
    phone_norm = normalize_phone(phone)
    email_norm = normalize_email(email)
    if phone_norm:
        # Stored phones may include punctuation; match by last digits then normalize.
        tail = phone_norm[-4:] if len(phone_norm) >= 4 else phone_norm
        candidates = list(
            qs.filter(
                Q(phone_number__icontains=tail)
                | Q(phone_number=phone)
                | Q(phone_number=phone_norm)
            )[:50]
        )
        for client in candidates:
            if normalize_phone(client.phone_number) == phone_norm:
                return client
        return None
    if email_norm:
        return qs.filter(email__iexact=email_norm).first()
    return None


def issue_session(client: Client, *, device_label: str = "") -> ClientAppSession:
    token = secrets.token_hex(32)
    return ClientAppSession.objects.create(
        client=client,
        token=token,
        device_label=(device_label or "")[:120],
    )


def revoke_session(session: ClientAppSession | None) -> None:
    if not session or session.revoked_at:
        return
    session.revoked_at = timezone.now()
    session.save(update_fields=["revoked_at"])


class ClientAppAuthentication(authentication.BaseAuthentication):
    """
    Authenticate client wallet requests.

    Header: Authorization: Token <client_session_token>
    Sets request.user to AnonymousUser and request.client / request.client_session.
    """

    keyword = "Token"

    def authenticate(self, request):
        auth = authentication.get_authorization_header(request).decode("utf-8")
        if not auth:
            return None
        parts = auth.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None
        token = parts[1].strip()
        if not token:
            return None
        session = (
            ClientAppSession.objects.select_related("client", "client__organization")
            .filter(token=token, revoked_at__isnull=True)
            .first()
        )
        if not session:
            raise exceptions.AuthenticationFailed("Invalid or expired client session.")
        if not session.client.app_access_enabled:
            raise exceptions.AuthenticationFailed("Client app access is disabled.")
        # Touch last_seen
        ClientAppSession.objects.filter(pk=session.pk).update(last_seen_at=timezone.now())
        request.client = session.client
        request.client_session = session
        # DRF expects (user, auth); keep user anonymous — client is on request.client
        from django.contrib.auth.models import AnonymousUser

        return (AnonymousUser(), session)

    def authenticate_header(self, request):
        return self.keyword


class IsClientAppAuthenticated(permissions.BasePermission):
    def has_permission(self, request, view):
        client = getattr(request, "client", None)
        session = getattr(request, "client_session", None)
        return bool(client and session and session.revoked_at is None and client.app_access_enabled)


class ClientAppLoginThrottle(AnonRateThrottle):
    scope = "anon"
