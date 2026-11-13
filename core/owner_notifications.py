"""Leadership notifications for the companion app and portal."""

from __future__ import annotations

from decimal import Decimal

from .models import Notification, OrganizationMembership
from .push_notifications import send_push
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


def _amount(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _usd(value) -> str:
    return f"${_amount(value):,.2f}"


def _person(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.username


def notify_owners_policy_bound(policy) -> int:
    """Notify active PSB owners and managers when a policy is bound. Returns count sent."""
    recipients = _owner_manager_memberships(policy.organization)
    client_name = policy.client.name if policy.client_id else (policy.named_insured or "A client")
    agent_name = _person(policy.added_by) or "An agent"
    company_name = policy.insurance_company.name if policy.insurance_company_id else "Unknown carrier"
    premium = _amount(policy.premium)
    commission = _amount(policy.commission_amount)
    broker_fee = _amount(getattr(policy, "broker_fee", 0))
    agency_take = commission + broker_fee
    message = (
        f"{client_name}: policy {policy.policy_number} bound with {company_name} by {agent_name}. "
        f"Premium {_usd(premium)}, commission {_usd(commission)}, broker fee {_usd(broker_fee)}."
    )
    data = {
        "kind": "insurance",
        "client": client_name,
        "subtitle": f"{company_name} · #{policy.policy_number}",
        "by": agent_name,
        "headline": {"label": "Agency earns", "amount": str(agency_take)},
        "lines": [
            {"label": "Premium", "amount": str(premium)},
            {"label": "Commission", "amount": str(commission)},
            {"label": "Broker fee", "amount": str(broker_fee)},
        ],
    }
    for membership in recipients:
        Notification.objects.create(
            user=membership.user,
            client=policy.client if policy.client_id else None,
            organization=policy.organization,
            policy=policy,
            event_type="policy_bound",
            level=Notification.Level.INFO,
            title="Policy bound",
            message=message,
            data=data,
        )
    send_push(
        [m.user_id for m in recipients],
        organization_id=policy.organization_id,
        title=f"Policy bound · {client_name}",
        body=(
            f"{company_name} · by {agent_name}\n"
            f"Agency earns {_usd(agency_take)}: commission {_usd(commission)} + broker fee {_usd(broker_fee)}\n"
            f"Premium {_usd(premium)}"
        ),
        data={"type": "policy_bound", "policy_id": policy.id},
    )
    return len(recipients)


def dmv_fee_breakdown(record) -> dict:
    """Split a DMV receipt into what goes to the DMV and what the office keeps."""
    dmv_lines = [
        ("DMV fee", _amount(record.dmv_fee)),
        ("DMV sales tax", _amount(record.dmv_sales_tax)),
        ("Other DMV fees", _amount(record.other_dmv_fee)),
    ]
    dmv_total = sum((amount for _label, amount in dmv_lines), Decimal("0.00"))
    processing_fee = _amount(record.processing_fee)
    referral_share = _amount(record.referral_commission)
    office_keeps = max(processing_fee - referral_share, Decimal("0.00"))
    return {
        "dmv_lines": [(label, amount) for label, amount in dmv_lines if amount],
        "dmv_total": dmv_total,
        "processing_fee": processing_fee,
        "referral_share": referral_share,
        "office_keeps": office_keeps,
    }


def notify_owners_dmv_transaction(record) -> int:
    """Notify owners and managers when a DMV transaction is recorded. Returns count sent."""
    recipients = _owner_manager_memberships(record.organization)
    if not recipients:
        return 0
    split = dmv_fee_breakdown(record)
    client_name = record.client_name or "Walk-in client"
    service = record.service_type_label
    agent_name = _person(record.handled_by) or "An agent"
    lines = [{"label": label, "amount": str(amount), "group": "dmv"} for label, amount in split["dmv_lines"]]
    lines.append({"label": "DMV total", "amount": str(split["dmv_total"]), "group": "dmv", "total": True})
    lines.append({"label": "Office processing fee", "amount": str(split["processing_fee"]), "group": "office"})
    if split["referral_share"]:
        lines.append({"label": "Referral share", "amount": str(-split["referral_share"]), "group": "office"})
    data = {
        "kind": "dmv",
        "client": client_name,
        "subtitle": f"{service} · {record.receipt_number}",
        "by": agent_name,
        "headline": {"label": "Office keeps", "amount": str(split["office_keeps"])},
        "lines": lines,
    }
    message = (
        f"{client_name}: {service} by {agent_name}. "
        f"Office processing fee {_usd(split['processing_fee'])}"
        + (f" (referral share {_usd(split['referral_share'])})" if split["referral_share"] else "")
        + f". DMV fees {_usd(split['dmv_total'])}."
    )
    Notification.objects.bulk_create(
        [
            Notification(
                user=membership.user,
                organization=record.organization,
                event_type="dmv_transaction",
                level=Notification.Level.INFO,
                title="DMV transaction",
                message=message,
                data=data,
            )
            for membership in recipients
        ]
    )
    send_push(
        [m.user_id for m in recipients],
        organization_id=record.organization_id,
        title=f"DMV · {service} · {client_name}",
        body=(
            f"Office keeps {_usd(split['office_keeps'])} (processing fee {_usd(split['processing_fee'])})\n"
            f"DMV fees {_usd(split['dmv_total'])} · by {agent_name}"
        ),
        data={"type": "dmv_transaction", "record_id": record.id},
    )
    return len(recipients)


def notify_owners_expense_alert(organization, *, title, message, push_title, push_body, data) -> int:
    """Expense watch alert for owners and managers. Returns count sent."""
    recipients = _owner_manager_memberships(organization)
    if not recipients:
        return 0
    Notification.objects.bulk_create(
        [
            Notification(
                user=membership.user,
                organization=organization,
                event_type="expense_alert",
                level=Notification.Level.WARNING,
                title=title,
                message=message,
                data=data,
            )
            for membership in recipients
        ]
    )
    send_push(
        [m.user_id for m in recipients],
        organization_id=organization.id,
        title=push_title,
        body=push_body,
        data={"type": "expense_alert"},
    )
    return len(recipients)


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
