from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.core.cache import cache
from django.conf import settings

@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """
    When a user logs in, update the cache with their new session key.
    This will invalidate any other active sessions for this user.
    """
    cache_key = f"user_active_session_{user.id}"
    session_key = request.session.session_key
    # Overwrite any existing session key in the cache
    cache.set(cache_key, session_key, settings.SESSION_COOKIE_AGE)
