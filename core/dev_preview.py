"""Let the development server be opened from a local browser preview.

Production (gunicorn) never takes this path. Framing and private-network
headers stay off there.
"""

from django.http import HttpResponse

from RegiManager.settings import running_dev_server

PREVIEW_ORIGINS = ("https://tweakcn.com", "https://www.tweakcn.com")


class DevServerPreviewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not running_dev_server():
            return self.get_response(request)

        origin = request.META.get("HTTP_ORIGIN", "")
        private_network = request.META.get("HTTP_ACCESS_CONTROL_REQUEST_PRIVATE_NETWORK") == "true"
        if request.method == "OPTIONS" and (private_network or origin in PREVIEW_ORIGINS):
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        if origin in PREVIEW_ORIGINS or private_network:
            if origin:
                response["Access-Control-Allow-Origin"] = origin
                response["Vary"] = "Origin"
            response["Access-Control-Allow-Private-Network"] = "true"
            response["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
            requested_headers = request.META.get("HTTP_ACCESS_CONTROL_REQUEST_HEADERS")
            if requested_headers:
                response["Access-Control-Allow-Headers"] = requested_headers

        # The development server is opened inside the preview frame. Production keeps DENY.
        if "X-Frame-Options" in response:
            del response["X-Frame-Options"]
        if "Cross-Origin-Opener-Policy" in response:
            del response["Cross-Origin-Opener-Policy"]
        response["Content-Security-Policy"] = (
            "frame-ancestors 'self' https://tweakcn.com https://www.tweakcn.com"
        )
        return response
