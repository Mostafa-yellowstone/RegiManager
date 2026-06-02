from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.dispatch import receiver
from .models import UserSession


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
