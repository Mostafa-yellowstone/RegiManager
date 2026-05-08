from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Q

from .models import OrganizationMembership

def automation_status(request):
    if not request.user.is_authenticated:
        return {
            "automation_enabled": False,
            "user_nav_role": "Agency Agent",
            "can_view_partners": False,
            "can_view_finance_bi": False,
            "notif_unread_count": 0,
            "top_notifications": [],
        }
    
    memberships = OrganizationMembership.objects.filter(user=request.user).select_related('organization')
    
    # Check if any organization associated with the user has automation enabled
    enabled = any(m.organization.is_automation_enabled for m in memberships)
    
    # Determine display role: Owner beats Agent
    is_owner = any(m.role == OrganizationMembership.Role.OWNER for m in memberships)
    user_nav_role = 'Agency Owner' if is_owner else 'Agency Agent'
    
    can_view_partners = is_owner or any(m.can_manage_dealers for m in memberships)
    can_view_finance_bi = is_owner or any(m.can_view_reports for m in memberships)
    
    # Notifications (defensive against missing tables / unapplied migrations)
    try:
        from .models import Notification

        # Note notifications stay visible until the related note is marked done.
        notif_qs = (
            Notification.objects.filter(user=request.user)
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

    return {
        "automation_enabled": enabled,
        "user_nav_role": user_nav_role,
        "can_view_partners": can_view_partners,
        "can_view_finance_bi": can_view_finance_bi,
        "notif_unread_count": notif_unread_count,
        "top_notifications": top_notifications,
    }
