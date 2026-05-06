from .models import Organization, OrganizationMembership

def automation_status(request):
    if not request.user.is_authenticated:
        return {'automation_enabled': False, 'user_nav_role': 'Agency Agent'}
    
    memberships = OrganizationMembership.objects.filter(user=request.user).select_related('organization')
    
    # Check if any organization associated with the user has automation enabled
    enabled = any(m.organization.is_automation_enabled for m in memberships)
    
    # Determine display role: Owner beats Agent
    is_owner = any(m.role == OrganizationMembership.Role.OWNER for m in memberships)
    user_nav_role = 'Agency Owner' if is_owner else 'Agency Agent'
    
    can_view_partners = is_owner or any(m.can_manage_dealers for m in memberships)
    
    return {
        'automation_enabled': enabled,
        'user_nav_role': user_nav_role,
        'can_view_partners': can_view_partners,
    }
