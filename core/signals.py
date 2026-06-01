from django.contrib.auth.signals import user_logged_in, user_logged_out
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


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    """
    When a user logs out, delete their active session key from the cache.
    Without this, the stale cache entry would cause a silent logout the
    next time the same user tries to log back in (especially on
    multi-worker production servers using LocMemCache).
    """
    if user and user.id:
        cache_key = f"user_active_session_{user.id}"
        cache.delete(cache_key)
