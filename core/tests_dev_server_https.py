import json
import shutil
import ssl
import tempfile
import threading
import urllib.request
from pathlib import Path

from django.core.management import get_commands
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from RegiManager.settings import running_dev_server
from core.dev_preview import DevServerPreviewMiddleware
from core.dev_server_https import DevHTTPSWSGIServer, ensure_dev_certificate


class DevServerHTTPSTests(SimpleTestCase):
    def test_runserver_command_comes_from_the_https_dev_server(self):
        self.assertEqual(get_commands()["runserver"], "core.https_devserver")

    @patch("core.dev_preview.running_dev_server", return_value=True)
    def test_development_server_can_be_opened_in_a_preview_frame(self, _running):
        def get_response(request):
            response = HttpResponse("ok")
            response["X-Frame-Options"] = "DENY"
            response["Cross-Origin-Opener-Policy"] = "same-origin"
            return response

        middleware = DevServerPreviewMiddleware(get_response)
        request = RequestFactory().get(
            "/",
            HTTP_ORIGIN="https://tweakcn.com",
            HTTP_ACCESS_CONTROL_REQUEST_PRIVATE_NETWORK="true",
        )
        response = middleware(request)
        self.assertNotIn("X-Frame-Options", response)
        self.assertNotIn("Cross-Origin-Opener-Policy", response)
        self.assertIn("https://tweakcn.com", response["Content-Security-Policy"])
        self.assertEqual(response["Access-Control-Allow-Private-Network"], "true")
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://tweakcn.com")

    @patch("core.dev_preview.running_dev_server", return_value=False)
    def test_production_server_stays_locked_in_a_frame(self, _running):
        def get_response(request):
            response = HttpResponse("ok")
            response["X-Frame-Options"] = "DENY"
            return response

        response = DevServerPreviewMiddleware(get_response)(RequestFactory().get("/"))
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertNotIn("Content-Security-Policy", response)

    def test_https_switch_is_only_for_runserver(self):
        self.assertTrue(running_dev_server(["manage.py", "runserver", "8000"]))
        self.assertFalse(running_dev_server(["gunicorn", "-c", "gunicorn.conf.py", "RegiManager.wsgi:application"]))
        self.assertFalse(running_dev_server(["manage.py", "test"]))

    def test_development_server_accepts_https_and_marks_the_request_secure(self):
        cert_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, cert_dir, True)
        cert_file, key_file = ensure_dev_certificate(cert_dir / "localhost.crt", cert_dir / "localhost.key")
        self.assertTrue((cert_dir / "dev-ca.crt").is_file())
        seen = {}

        def app(environ, start_response):
            seen["scheme"] = environ.get("wsgi.url_scheme")
            body = json.dumps({"scheme": seen["scheme"]}).encode()
            start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
            return [body]

        DevHTTPSWSGIServer.certfile = str(cert_file)
        DevHTTPSWSGIServer.keyfile = str(key_file)
        server = DevHTTPSWSGIServer(("127.0.0.1", 0), None)
        server.set_app(app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(
                f"https://127.0.0.1:{server.server_port}/health",
                context=context,
                timeout=5,
            ) as response:
                payload = json.loads(response.read().decode())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["scheme"], "https")
            self.assertEqual(seen["scheme"], "https")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
