from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Q

from .models import OrganizationMembership, SiteNews

def automation_status(request):
    if not request.user.is_authenticated:
        return {
            "automation_enabled": False,
            "user_nav_role": "PSB Agent",
            "can_view_partners": False,
            "can_view_finance_bi": False,
            "notif_unread_count": 0,
            "top_notifications": [],
            "user_organizations": [],
            "active_organization": None,
        }
    
    memberships = OrganizationMembership.objects.filter(
        user=request.user, 
        is_active=True,
        organization__is_active=True
    ).select_related('organization')
    
    # Location Switcher context
    user_organizations = [m.organization for m in memberships]
    active_org_id = request.session.get('active_org_id')
    
    # If active_org_id is set, filter the scopes used for permission checking
    if active_org_id:
        active_memberships = memberships.filter(organization_id=active_org_id)
        active_organization = next((o for o in user_organizations if o.id == active_org_id), None)
    else:
        active_memberships = memberships
        active_organization = None

    # Check if any (active) organization associated with the user has automation enabled
    enabled = any(m.organization.is_automation_enabled for m in active_memberships)
    
    # Determine display role: Owner beats Agent
    is_owner = any(m.role == OrganizationMembership.Role.OWNER for m in active_memberships)
    user_nav_role = 'PSB Owner' if is_owner else 'PSB Agent'
    
    can_view_partners = is_owner or any(m.can_manage_referrals for m in active_memberships)
    can_view_finance_bi = is_owner or any(m.can_view_reports for m in active_memberships)
    can_view_spaces = request.user.is_superuser or is_owner or any(m.can_view_spaces for m in active_memberships)
    
    # Notifications (defensive against missing tables / unapplied migrations)
    try:
        from .models import Notification

        # Note notifications stay visible until the related note is marked done.
        notif_qs = (
            Notification.objects.filter(user=request.user)
            .filter(client__deleted_at__isnull=True)
            .filter(
                Q(note__isnull=False, note__is_done=False)
                | Q(note__isnull=True, is_read=False)
            )
            .select_related("client", "note")
        )
        
        # If active_organization is set, we might want to filter notifications too?
        # For now, let's keep notifications global so owners don't miss alerts.
        
        notif_unread_count = notif_qs.count()
        top_notifications = list(notif_qs.order_by("-created_at")[:6])
    except (OperationalError, ProgrammingError):
        notif_unread_count = 0
        top_notifications = []

    # Site News
    try:
        site_news = SiteNews.objects.filter(is_active=True).first()
    except (OperationalError, ProgrammingError):
        site_news = None

    return {
        "automation_enabled": enabled,
        "user_nav_role": user_nav_role,
        "can_view_partners": can_view_partners,
        "can_view_finance_bi": can_view_finance_bi,
        "can_view_spaces": can_view_spaces,
        "notif_unread_count": notif_unread_count,
        "top_notifications": top_notifications,
        "user_organizations": user_organizations,
        "active_organization": active_organization,
        "site_news": site_news,
    }
