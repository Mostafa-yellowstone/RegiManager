"""nginx auth_request check for /media/: uploaded documents are only served to signed-in users."""

from urllib.parse import unquote

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache

# Images that appear in emails, public intake pages or the mobile app (no browser session there).
PUBLIC_MEDIA_PREFIXES = (
    "organization_logos/",
    "space_logos/",
    "email_marketing/",
    "marketing_campaigns/",
    "agent_profiles/",
)


def media_path_is_public(relative_path: str) -> bool:
    return relative_path.startswith(PUBLIC_MEDIA_PREFIXES)


@never_cache
def media_auth(request):
    uri = unquote((request.headers.get("X-Original-URI") or "").split("?", 1)[0])
    media_url = settings.MEDIA_URL
    if not uri.startswith(media_url):
        return HttpResponse(status=403)
    relative = uri[len(media_url):]
    if ".." in relative.split("/"):
        return HttpResponse(status=403)
    if media_path_is_public(relative):
        return HttpResponse(status=204)
    if request.user.is_authenticated:
        return HttpResponse(status=204)
    return HttpResponse(status=401)
