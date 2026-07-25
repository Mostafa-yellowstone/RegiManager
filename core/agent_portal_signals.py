"""Activity timeline hooks for insurance, motorclub, and TLC."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .agent_portal_models import AgentActivityEvent
from .agent_portal_services import log_agent_activity
from .models import InsurancePolicy, MotorclubMembership
from .tlc_models import TLCEndorsement, TLCPolicy


@receiver(pre_save, sender=InsurancePolicy)
def _cache_insurance_stage_for_activity(sender, instance, **kwargs):
    if instance.pk:
        try:
            previous = InsurancePolicy.objects.only("stage").get(pk=instance.pk)
            instance._activity_previous_stage = previous.stage
        except InsurancePolicy.DoesNotExist:
            instance._activity_previous_stage = None
    else:
        instance._activity_previous_stage = None


@receiver(post_save, sender=InsurancePolicy)
def log_insurance_policy_activity(sender, instance, created, **kwargs):
    actor = instance.added_by
    if actor is None:
        return
    client_name = ""
    if instance.client_id:
        client_name = instance.client.get_full_name() if hasattr(instance.client, "get_full_name") else str(instance.client)
    policy_label = instance.policy_number or f"Policy #{instance.pk}"
    previous = getattr(instance, "_activity_previous_stage", None)

    if created:
        if instance.stage in InsurancePolicy.QUOTE_STAGES:
            event_type = AgentActivityEvent.EventType.QUOTE_CREATED
            title = f"Quote created — {policy_label}"
        elif instance.stage in InsurancePolicy.BOUND_STAGES:
            event_type = AgentActivityEvent.EventType.POLICY_BOUND
            title = f"Policy bound — {policy_label}"
        elif instance.stage == InsurancePolicy.StageChoices.ENDORSEMENT:
            event_type = AgentActivityEvent.EventType.ENDORSEMENT
            title = f"Endorsement — {policy_label}"
        else:
            event_type = AgentActivityEvent.EventType.OTHER
            title = f"Insurance policy saved — {policy_label}"
        log_agent_activity(
            organization=instance.organization,
            actor=actor,
            domain=AgentActivityEvent.Domain.INSURANCE,
            event_type=event_type,
            title=title,
            detail=client_name,
            object_id=instance.pk,
        )
        return

    if (
        previous not in InsurancePolicy.BOUND_STAGES
        and instance.stage in InsurancePolicy.BOUND_STAGES
    ):
        log_agent_activity(
            organization=instance.organization,
            actor=actor,
            domain=AgentActivityEvent.Domain.INSURANCE,
            event_type=AgentActivityEvent.EventType.POLICY_BOUND,
            title=f"Policy bound — {policy_label}",
            detail=client_name,
            object_id=instance.pk,
        )
    elif (
        not created
        and instance.stage == InsurancePolicy.StageChoices.ENDORSEMENT
        and previous != InsurancePolicy.StageChoices.ENDORSEMENT
    ):
        log_agent_activity(
            organization=instance.organization,
            actor=actor,
            domain=AgentActivityEvent.Domain.INSURANCE,
            event_type=AgentActivityEvent.EventType.ENDORSEMENT,
            title=f"Endorsement — {policy_label}",
            detail=client_name,
            object_id=instance.pk,
        )


@receiver(post_save, sender=MotorclubMembership)
def log_motorclub_activity(sender, instance, created, **kwargs):
    if not created:
        return
    actor = instance.added_by
    if actor is None:
        return
    client_name = ""
    if instance.client_id:
        client_name = (
            instance.client.get_full_name()
            if hasattr(instance.client, "get_full_name")
            else str(instance.client)
        )
    label = instance.membership_number or f"MC #{instance.pk}"
    log_agent_activity(
        organization=instance.organization,
        actor=actor,
        domain=AgentActivityEvent.Domain.MOTORCLUB,
        event_type=AgentActivityEvent.EventType.MEMBERSHIP_CREATED,
        title=f"Motor Club membership created — {label}",
        detail=client_name or instance.get_status_display(),
        object_id=instance.pk,
    )


@receiver(post_save, sender=TLCPolicy)
def log_tlc_policy_activity(sender, instance, created, **kwargs):
    if not created:
        return
    actor = instance.added_by or instance.producer
    if actor is None:
        return
    label = instance.policy_number or f"TLC #{instance.pk}"
    insured = instance.named_insured or instance.business_name or ""
    log_agent_activity(
        organization=instance.organization,
        actor=actor,
        domain=AgentActivityEvent.Domain.TLC,
        event_type=AgentActivityEvent.EventType.TLC_POLICY_CREATED,
        title=f"TLC policy created — {label}",
        detail=insured,
        object_id=instance.pk,
    )


@receiver(post_save, sender=TLCEndorsement)
def log_tlc_endorsement_activity(sender, instance, created, **kwargs):
    if not created:
        return
    policy = instance.policy
    actor = instance.processed_by or policy.added_by or policy.producer
    if actor is None:
        return
    log_agent_activity(
        organization=policy.organization,
        actor=actor,
        domain=AgentActivityEvent.Domain.TLC,
        event_type=AgentActivityEvent.EventType.TLC_ENDORSEMENT,
        title=f"TLC endorsement — {policy.policy_number or policy.pk}",
        detail=instance.get_endorsement_type_display(),
        object_id=instance.pk,
    )
