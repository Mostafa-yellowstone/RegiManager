"""In-app notifications for insurance policy pipeline assignments."""

from .models import Notification


def notify_insurance_policy_assignment(policy, *, entered_by, assign_method):
    """
    Notify the assigned agent when a policy is routed via pipeline or manual override.
    """
    if assign_method not in ("pipeline", "manual"):
        return None
    if not policy.added_by_id or not policy.client_id:
        return None

    entered_label = entered_by.get_full_name() or entered_by.username
    policy_label = policy.policy_number or f"#{policy.id}"
    client_label = policy.client.name if policy.client else "Client"

    if assign_method == "pipeline":
        title = "New policy assigned to you (pipeline)"
        message = f"{policy_label} for {client_label} — entered by {entered_label}"
    else:
        title = "New policy assigned to you"
        message = f"{policy_label} for {client_label} — assigned by {entered_label}"

    return Notification.objects.create(
        user=policy.added_by,
        client=policy.client,
        insurance_policy=policy,
        title=title,
        message=message,
        level=Notification.Level.SUCCESS,
    )
