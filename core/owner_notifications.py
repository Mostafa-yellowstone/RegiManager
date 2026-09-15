"""Leadership notifications for the companion app and portal."""

from __future__ import annotations

from decimal import Decimal

from .models import Notification, OrganizationMembership
from .role_permissions import Role, normalize_role


def _owner_manager_memberships(organization):
    memberships = OrganizationMembership.objects.filter(
        organization=organization,
        is_active=True,
        organization__is_active=True,
    ).select_related("user")
    return [
        membership
        for membership in memberships
        if normalize_role(membership.role) in {Role.OWNER, Role.MANAGER}
    ]


def notify_owners_policy_bound(policy) -> int:
    """Notify active PSB owners and managers when a policy is bound. Returns count sent."""
    recipients = _owner_manager_memberships(policy.organization)
    client = policy.client
    agent_name = (
        policy.added_by.get_full_name() or policy.added_by.username
        if policy.added_by
        else "An agent"
    )
    company_name = policy.insurance_company.name if policy.insurance_company_id else "Unknown"
    message = (
        f"{client.name}: policy {policy.policy_number} bound with {company_name} "
        f"by {agent_name}. Premium ${policy.premium}, commission ${policy.commission_amount or 0}."
    )
    created = 0
    for membership in recipients:
        Notification.objects.create(
            user=membership.user,
            client=client,
            organization=policy.organization,
            policy=policy,
            event_type="policy_bound",
            level=Notification.Level.INFO,
            title="Policy bound",
            message=message,
        )
        created += 1
    return created


def notify_pulse_daily_snapshot(
    *,
    organization,
    work_date,
    records: int,
    processing_fee: Decimal,
) -> int:
    """In-app Pulse digest for owners/managers (pair with cron + optional push)."""
    recipients = _owner_manager_memberships(organization)
    fee = Decimal(processing_fee or 0).quantize(Decimal("0.01"))
    title = "Pulse daily snapshot"
    message = (
        f"{organization.name} · {work_date.isoformat()}: "
        f"{records} DMV records, processing fee ${fee}."
    )
    created = 0
    for membership in recipients:
        Notification.objects.create(
            user=membership.user,
            organization=organization,
            event_type="pulse_daily_snapshot",
            level=Notification.Level.INFO,
            title=title,
            message=message,
        )
        created += 1
    return created
