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


def _signed_money(value: Decimal) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}${abs(value):,.2f}"


def notify_policy_endorsed(policy, transaction, *, old_commission=None, actor=None) -> int:
    """Notify owners, managers and the policy's agent about an endorsement. Returns count sent."""
    from django.urls import reverse

    users = {membership.user_id: membership.user for membership in _owner_manager_memberships(policy.organization)}
    if policy.added_by_id:
        users.setdefault(policy.added_by_id, policy.added_by)

    old_premium = Decimal(transaction.old_premium or 0)
    new_premium = Decimal(transaction.new_premium or 0)
    new_commission = Decimal(policy.commission_amount or 0)
    old_commission = Decimal(old_commission or 0)
    company_name = policy.insurance_company.name if policy.insurance_company_id else "no carrier"
    by = ""
    if actor is not None and getattr(actor, "is_authenticated", False):
        by = f" by {actor.get_full_name() or actor.username}"
    message = (
        f"{policy.client.name}: policy {policy.policy_number} ({company_name}) endorsed{by}, "
        f"effective {transaction.effective_date:%b %d, %Y}. "
        f"Premium ${old_premium:,.2f} → ${new_premium:,.2f} ({_signed_money(new_premium - old_premium)}). "
        f"Commission ${old_commission:,.2f} → ${new_commission:,.2f}."
    )
    if transaction.note:
        message += f" {transaction.note}"
    action_url = reverse("insurance-policy-detail", args=[policy.id])
    Notification.objects.bulk_create(
        [
            Notification(
                user=user,
                client=policy.client,
                organization=policy.organization,
                policy=policy,
                event_type="policy_endorsed",
                level=Notification.Level.INFO,
                title="Policy endorsed",
                message=message,
                action_url=action_url,
            )
            for user in users.values()
        ]
    )
    return len(users)


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
