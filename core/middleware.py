from django.contrib.auth import logout
from django.contrib import messages

from .models import UserSession


class SingleSessionMiddleware:
    """
    Enterprise Security Middleware:
    Ensures only one device/session can be active per user at a time.

    Uses the database-backed UserSession model (not LocMemCache) so it
    works correctly on multi-worker production servers (gunicorn).

    Flow:
      1. User logs in → user_logged_in signal stores session key in
         UserSession AND deletes the old session from the Session table.
      2. On every request, this middleware checks whether the current
         session key matches the one stored in UserSession.
      3. If it doesn't match, the user was displaced by a login on
         another device → log them out with a clear message.
      4. If no UserSession record exists (first request after a cold
         start, or a race condition), we simply skip the check — the
         login signal will create the record on next login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            session_key = request.session.session_key
            if session_key:
                try:
                    active = UserSession.objects.get(user=request.user)
                    if active.session_key != session_key:
                        # Another device logged in — this session is stale.
                        logout(request)
                        messages.warning(
                            request,
                            "You were signed out because your account was accessed "
                            "from another device or browser. Please sign in again."
                        )
                except UserSession.DoesNotExist:
                    # No record yet (edge case) — don't block the user.
                    pass

        response = self.get_response(request)
        return response
