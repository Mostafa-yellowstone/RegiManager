"""Site news visibility and read-state helpers."""

from django.db.models import Q

from .models import Organization, SiteNews, SiteNewsRead


def organizations_for_request(request):
    """Organizations in scope for news visibility (matches dashboard location filter)."""
    from .models import Organization, OrganizationMembership

    if request.user.is_superuser:
        all_orgs = Organization.objects.filter(is_active=True)
        active_org_id = request.session.get("active_org_id")
        if active_org_id:
            return all_orgs.filter(id=active_org_id)
        return all_orgs

    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    )
    all_orgs = Organization.objects.filter(
        id__in=memberships.values("organization_id")
    ).distinct()
    active_org_id = request.session.get("active_org_id")
    if active_org_id and memberships.filter(organization_id=active_org_id).exists():
        return all_orgs.filter(id=active_org_id)
    return all_orgs


def news_organization_for_post(request, organizations):
    """Pick the PSB a new announcement belongs to."""
    active_org_id = request.session.get("active_org_id")
    if active_org_id:
        org = organizations.filter(id=active_org_id).first()
        if org:
            return org
    return organizations.first()


def news_scope_for_organizations(organizations):
    """News visible to members of the given PSB scope."""
    org_ids = list(organizations.values_list("id", flat=True))
    if not org_ids:
        return SiteNews.objects.none()
    return SiteNews.objects.filter(
        Q(organization_id__in=org_ids) | Q(organization__isnull=True)
    )


def unread_news_for_user(user, organizations):
    """Active news in scope that the user has not opened yet."""
    if not getattr(user, "is_authenticated", False):
        return SiteNews.objects.none()
    scoped = news_scope_for_organizations(organizations).filter(is_active=True)
    read_ids = SiteNewsRead.objects.filter(user=user).values_list("news_id", flat=True)
    return scoped.exclude(id__in=read_ids).order_by("-created_at")


def unread_news_count(user, organizations) -> int:
    return unread_news_for_user(user, organizations).count()


def user_can_access_news(user, news, organizations) -> bool:
    if news.organization_id is None:
        return news_scope_for_organizations(organizations).filter(pk=news.pk).exists()
    return organizations.filter(id=news.organization_id).exists()


def mark_news_read(user, news):
    """Mark a single announcement as read (idempotent)."""
    if not news or not getattr(user, "is_authenticated", False):
        return
    SiteNewsRead.objects.get_or_create(user=user, news=news)


def mark_all_news_read(user, organizations):
    """Mark every unread announcement in scope as read."""
    unread = list(unread_news_for_user(user, organizations))
    if not unread:
        return 0
    existing = set(
        SiteNewsRead.objects.filter(
            user=user,
            news__in=unread,
        ).values_list("news_id", flat=True)
    )
    to_create = [
        SiteNewsRead(user=user, news=item)
        for item in unread
        if item.id not in existing
    ]
    if to_create:
        SiteNewsRead.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create)


def clear_reads_for_news(news):
    """Reset read receipts when an announcement is materially changed."""
    SiteNewsRead.objects.filter(news=news).delete()
