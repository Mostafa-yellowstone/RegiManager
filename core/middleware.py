from django.conf import settings
from django.contrib.auth import logout
from django.contrib import messages
from django.core.cache import cache

class SingleSessionMiddleware:
    """
    Enterprise Security Middleware:
    Ensures that only one device/session can be active for a user at a time.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            session_key = request.session.session_key
            # Create a unique cache key for the user
            cache_key = f"user_active_session_{request.user.id}"
            active_session_key = cache.get(cache_key)

            # If no active session is stored (e.g., first request after login), store it
            if not active_session_key:
                cache.set(cache_key, session_key, settings.SESSION_COOKIE_AGE)
            # If the session key doesn't match the one in cache, someone else logged in
            elif active_session_key != session_key:
                # Log out the stale/displaced session
                logout(request)
                messages.warning(
                    request,
                    "You were signed out because your account was accessed from another device or browser. "
                    "Please sign in again."
                )

        response = self.get_response(request)
        return response
