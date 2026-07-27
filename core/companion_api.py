"""Companion mobile app API — authentication and session metadata."""

from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import OrganizationMembership
from .policies import active_memberships_qs


def _membership_payload(membership: OrganizationMembership, request=None) -> dict:
    org = membership.organization
    photo_url = None
    if request and membership.profile_photo:
        try:
            photo_url = request.build_absolute_uri(membership.profile_photo.url)
        except Exception:
            photo_url = None
    return {
        "id": org.id,
        "membership_id": membership.id,
        "name": org.name,
        "city": org.city,
        "state": org.state,
        "role": membership.role,
        "profile_photo_url": photo_url,
        "permissions": {
            "can_view_reports": membership.can_view_reports,
            "can_view_net_profit": membership.can_view_net_profit,
            "can_manage_referrals": membership.can_manage_referrals,
            "can_trigger_automation": membership.can_trigger_automation,
            "can_view_banking": membership.can_view_banking,
            "can_manage_news": membership.can_manage_news,
            "can_manage_knowledge_hub": membership.can_manage_knowledge_hub,
            "can_manage_documents": membership.can_manage_documents,
            "can_manage_email_marketing": membership.can_manage_email_marketing,
            "can_view_spaces": membership.can_view_spaces,
            "can_issue_refund": membership.can_issue_refund,
            "can_deal_with_insurance": membership.can_deal_with_insurance,
            "can_assign_agent_tasks": membership.can_assign_agent_tasks,
            "uses_agent_portal": (
                membership.is_active
                and membership.role != OrganizationMembership.Role.OWNER
                and membership.can_deal_with_insurance
            ),
        },
    }


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.get_full_name() or user.username,
    }


class CompanionLoginThrottle(AnonRateThrottle):
    scope = "anon"


class CompanionLoginView(APIView):
    """
    Obtain an API token for the companion app.

    Use header on all requests: Authorization: Token <token>
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [CompanionLoginThrottle]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        if not username or not password:
            return Response(
                {"detail": "username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if not user or not user.is_active:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        memberships = list(
            active_memberships_qs(user).select_related("organization").order_by("organization__name")
        )
        if not memberships:
            return Response(
                {"detail": "No active PSB membership for this account."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)
        from .agent_portal_services import start_attendance_on_login

        start_attendance_on_login(user)
        organizations = [_membership_payload(m, request) for m in memberships]
        return Response(
            {
                "token": token.key,
                "token_type": "Token",
                "user": _user_payload(user),
                "organizations": organizations,
                "default_organization_id": organizations[0]["id"],
            }
        )


class CompanionMeView(APIView):
    """Current user profile and organization memberships."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        memberships = list(
            active_memberships_qs(request.user).select_related("organization").order_by("organization__name")
        )
        organizations = [_membership_payload(m, request) for m in memberships]
        return Response(
            {
                "user": _user_payload(request.user),
                "organizations": organizations,
                "server_time": timezone.now().isoformat(),
            }
        )


class CompanionLogoutView(APIView):
    """Revoke the current API token (mobile sign-out)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"detail": "Signed out."})
