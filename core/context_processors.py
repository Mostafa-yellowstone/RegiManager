from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Q

from .models import OrganizationMembership


def _membership_context(request):
    cache_key = f"nav_ctx:{request.user.pk}:{request.session.get('active_org_id')}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    ).select_related("organization")

    user_organizations = [m.organization for m in memberships]
    active_org_id = request.session.get("active_org_id")
    if active_org_id:
        active_memberships = memberships.filter(organization_id=active_org_id)
        active_organization = next((o for o in user_organizations if o.id == active_org_id), None)
    else:
        active_memberships = memberships
        active_organization = None

    enabled = any(m.organization.is_automation_enabled for m in active_memberships)
    is_owner = any(m.role == OrganizationMembership.Role.OWNER for m in active_memberships)
    user_nav_role = "PSB Owner" if is_owner else "PSB Agent"
    can_view_partners = is_owner or any(m.can_manage_referrals for m in active_memberships)
    can_view_finance_bi = is_owner or any(m.can_view_reports for m in active_memberships)
    can_view_spaces = request.user.is_superuser or any(
        m.can_view_spaces for m in active_memberships
    )
    can_manage_email_marketing = is_owner or any(
        m.can_manage_email_marketing for m in active_memberships
    )

    result = {
        "automation_enabled": enabled,
        "user_nav_role": user_nav_role,
        "can_view_partners": can_view_partners,
        "can_view_finance_bi": can_view_finance_bi,
        "can_view_spaces": can_view_spaces,
        "can_manage_email_marketing": can_manage_email_marketing,
        "user_organizations": user_organizations,
        "active_organization": active_organization,
    }
    cache.set(cache_key, result, timeout=60)
    return result


def automation_status(request):
    if not request.user.is_authenticated:
        return {
            "automation_enabled": False,
            "user_nav_role": "PSB Agent",
            "can_view_partners": False,
            "can_view_finance_bi": False,
            "can_manage_email_marketing": False,
            "notif_unread_count": 0,
            "top_notifications": [],
            "user_organizations": [],
            "active_organization": None,
            "site_news_unread_count": 0,
            "site_news_latest_unread": None,
        }

    membership_ctx = _membership_context(request)

    try:
        from .models import Notification

        notif_qs = (
            Notification.objects.filter(user=request.user)
            .filter(client__deleted_at__isnull=True)
            .filter(
                Q(note__isnull=False, note__is_done=False)
                | Q(note__isnull=True, is_read=False)
            )
            .select_related("client", "note")
        )
        notif_unread_count = notif_qs.count()
        top_notifications = list(notif_qs.order_by("-created_at")[:6])
    except (OperationalError, ProgrammingError):
        notif_unread_count = 0
        top_notifications = []

    try:
        from .site_news import (
            news_scope_for_organizations,
            organizations_for_request,
            unread_news_count,
            unread_news_for_user,
        )

        news_orgs = organizations_for_request(request)
        site_news_unread_count = unread_news_count(request.user, news_orgs)
        site_news_latest_unread = unread_news_for_user(request.user, news_orgs).first()
        site_news = site_news_latest_unread or news_scope_for_organizations(news_orgs).filter(
            is_active=True
        ).first()
    except (OperationalError, ProgrammingError):
        site_news_unread_count = 0
        site_news_latest_unread = None
        site_news = None

    return {
        **membership_ctx,
        "notif_unread_count": notif_unread_count,
        "top_notifications": top_notifications,
        "site_news": site_news,
        "site_news_unread_count": site_news_unread_count,
        "site_news_latest_unread": site_news_latest_unread,
    }


def portal_timezone(request):
    if not request.user.is_authenticated:
        return {}

    from django.utils import timezone as dj_timezone

    from .timezone_utils import timezone_label

    tzinfo = dj_timezone.get_current_timezone()
    tz_name = str(tzinfo) if tzinfo else dj_timezone.get_default_timezone_name()
    return {
        "portal_timezone_name": tz_name,
        "portal_timezone_label": timezone_label(tz_name),
    }
