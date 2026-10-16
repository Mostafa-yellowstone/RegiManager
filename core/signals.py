from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import InsurancePolicy, OrganizationMembership, UserSession
from .owner_notifications import notify_owners_policy_bound


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """
    When a user logs in, store their new session key in the database
    and delete the old session (if any) to force-logout the other device.
    """
    # Ensure the session has a key generated
    if not request.session.session_key:
        try:
            request.session.save()
        except Exception:
            pass

    new_session_key = request.session.session_key

    # Attendance for every active PSB agent (DMV + insurance), NY clock.
    # Runs even when there is no Django session key (API / token logins).
    try:
        from .agent_portal_services import start_attendance_on_login

        start_attendance_on_login(user)
    except Exception:
        pass

    if not new_session_key:
        # If there's still no session key (e.g. in tests or custom API logins),
        # do not save/create UserSession as session_key cannot be NULL.
        return

    try:
        active = UserSession.objects.get(user=user)
        old_key = active.session_key
        # Delete the old session from Django's Session table so the
        # other device/browser is instantly kicked out.
        if old_key and old_key != new_session_key:
            Session.objects.filter(session_key=old_key).delete()
        # Update to the new session key
        active.session_key = new_session_key
        active.save(update_fields=["session_key", "created_at"])
    except UserSession.DoesNotExist:
        UserSession.objects.create(user=user, session_key=new_session_key)


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    """
    When a user logs out, remove their active session record
    so the next login starts fresh with no stale state.
    """
    if user and hasattr(user, "pk") and user.pk:
        UserSession.objects.filter(user=user).delete()


@receiver(post_save, sender=OrganizationMembership)
@receiver(post_delete, sender=OrganizationMembership)
def refresh_nav_after_membership_change(sender, instance, **kwargs):
    from .context_processors import invalidate_nav_cache

    invalidate_nav_cache(instance.user_id, [instance.organization_id])


@receiver(pre_save, sender=get_user_model())
def remember_credential_state(sender, instance, **kwargs):
    instance._credentials_changed = False
    if not instance.pk:
        return
    # set_password() leaves the raw value in _password until save; hash upgrades at login clear it first.
    password_changed = getattr(instance, "_password", None) is not None
    previous = sender.objects.filter(pk=instance.pk).values("password", "is_active").first()
    if previous and (
        (password_changed and previous["password"] != instance.password)
        or (previous["is_active"] and not instance.is_active)
    ):
        instance._credentials_changed = True


@receiver(post_save, sender=get_user_model())
def revoke_access_after_credential_change(sender, instance, created, **kwargs):
    """A new password or a deactivated account must sign out every device, including mobile API tokens."""
    if created or not getattr(instance, "_credentials_changed", False):
        return
    from rest_framework.authtoken.models import Token

    Token.objects.filter(user=instance).delete()
    session_keys = list(UserSession.objects.filter(user=instance).values_list("session_key", flat=True))
    if session_keys:
        Session.objects.filter(session_key__in=session_keys).delete()
    UserSession.objects.filter(user=instance).delete()


@receiver(pre_save, sender=InsurancePolicy)
def cache_policy_stage(sender, instance, **kwargs):
    if instance.pk:
        try:
            previous = InsurancePolicy.objects.only("stage").get(pk=instance.pk)
            instance._previous_stage = previous.stage
        except InsurancePolicy.DoesNotExist:
            instance._previous_stage = None
    else:
        instance._previous_stage = None


@receiver(post_save, sender=InsurancePolicy)
def notify_on_policy_bound(sender, instance, created, **kwargs):
    previous_stage = getattr(instance, "_previous_stage", None)
    if instance.stage not in InsurancePolicy.BOUND_STAGES:
        return
    if created or previous_stage not in InsurancePolicy.BOUND_STAGES:
        notify_owners_policy_bound(instance)
