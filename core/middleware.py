from django.contrib.sessions.models import Session
from django.conf import settings
from django.contrib.auth import logout
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
                # Log out the old session
                logout(request)
                # You could also add a message here: 
                # messages.warning(request, "You have been logged out because someone else logged in from another device.")
        
        response = self.get_response(request)
        return response
