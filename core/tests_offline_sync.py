import uuid

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.signals import got_request_exception
from django.db.utils import InterfaceError, OperationalError
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt

from core.offline_sync import DatabaseOutageMarkerMiddleware, OfflineSyncMiddleware

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "offline-sync-tests"}}
CALLS = {"write": 0}


@csrf_exempt
def _write_view(request):
    CALLS["write"] += 1
    if request.POST.get("fail") == "validation":
        return JsonResponse({"ok": False}, status=400)
    return HttpResponseRedirect("/t/done/")


@csrf_exempt
def _db_down_view(request):
    raise OperationalError("could not connect to server")


@csrf_exempt
def _bug_view(request):
    raise ValueError("ordinary bug")


urlpatterns = [
    path("t/write/", _write_view),
    path("t/db-down/", _db_down_view),
    path("t/bug/", _bug_view),
    path("", include("RegiManager.urls")),
]

STACK_SETTINGS = dict(
    ROOT_URLCONF="core.tests_offline_sync",
    CACHES=LOCMEM,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    RATE_LIMIT_ENABLED=False,
)


def _key():
    return str(uuid.uuid4())


@override_settings(CACHES=LOCMEM)
class IdempotencyMiddlewareUnitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.calls = 0
        self.status = 302

    def tearDown(self):
        cache.clear()

    def _view(self, request):
        self.calls += 1
        return HttpResponse(status=self.status)

    def _post(self, key=None, method="post"):
        headers = {"HTTP_X_IDEMPOTENCY_KEY": key} if key else {}
        request = getattr(self.factory, method)("/x/", **headers)
        return OfflineSyncMiddleware(self._view)(request)

    def test_same_key_runs_the_view_once(self):
        key = _key()
        first = self._post(key)
        second = self._post(key)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second["X-Idempotent-Replay"], "1")
        self.assertEqual(self.calls, 1)

    def test_different_keys_both_run(self):
        self._post(_key())
        self._post(_key())
        self.assertEqual(self.calls, 2)

    def test_requests_without_key_are_untouched(self):
        self._post()
        self._post()
        self.assertEqual(self.calls, 2)

    def test_malformed_key_is_ignored(self):
        self._post("short")
        self._post("short")
        self.assertEqual(self.calls, 2)

    def test_get_requests_are_not_deduplicated(self):
        key = _key()
        self._post(key, method="get")
        self._post(key, method="get")
        self.assertEqual(self.calls, 2)

    def test_server_error_releases_key_so_replay_runs_again(self):
        key = _key()
        self.status = 500
        self._post(key)
        self.status = 302
        self._post(key)
        self.assertEqual(self.calls, 2)

    def test_rate_limited_or_rejected_request_releases_key(self):
        key = _key()
        for status in (429, 403, 400):
            self.status = status
            self._post(key)
        self.status = 302
        self._post(key)
        self.assertEqual(self.calls, 4)
        self._post(key)
        self.assertEqual(self.calls, 4)

    def test_in_flight_duplicate_gets_retryable_conflict(self):
        key = _key()
        middleware = OfflineSyncMiddleware(self._view)

        def nested(request):
            inner = self.factory.post("/x/", HTTP_X_IDEMPOTENCY_KEY=key)
            duplicate = middleware(inner)
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(duplicate["X-Regi-Retryable"], "1")
            return HttpResponse(status=302)

        OfflineSyncMiddleware(nested)(self.factory.post("/x/", HTTP_X_IDEMPOTENCY_KEY=key))
        self.assertEqual(self.calls, 0)

    def test_cache_outage_still_processes_request(self):
        from unittest import mock

        with mock.patch("core.offline_sync.cache.add", side_effect=ConnectionError("redis down")):
            response = self._post(_key())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.calls, 1)


@override_settings(CACHES=LOCMEM)
class DatabaseOutageUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_db_error_signalled_during_request_becomes_retryable_503(self):
        def get_response(request):
            try:
                raise OperationalError("connection refused")
            except OperationalError:
                got_request_exception.send(sender=None, request=request)
            return HttpResponse(status=500)

        response = OfflineSyncMiddleware(get_response)(self.factory.post("/x/"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["X-Regi-Retryable"], "1")
        self.assertEqual(response["Retry-After"], "30")

    def test_ordinary_500_is_left_alone(self):
        def get_response(request):
            try:
                raise ValueError("bug")
            except ValueError:
                got_request_exception.send(sender=None, request=request)
            return HttpResponse(status=500)

        response = OfflineSyncMiddleware(get_response)(self.factory.post("/x/"))
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.has_header("X-Regi-Retryable"))

    def test_marker_handles_interface_error_as_outage(self):
        marker = DatabaseOutageMarkerMiddleware(lambda r: HttpResponse())
        request = self.factory.post("/x/", HTTP_ACCEPT="application/json")
        response = marker.process_exception(request, InterfaceError("connection already closed"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_marker_ignores_other_exceptions(self):
        marker = DatabaseOutageMarkerMiddleware(lambda r: HttpResponse())
        self.assertIsNone(marker.process_exception(self.factory.post("/x/"), ValueError("bug")))


@override_settings(**STACK_SETTINGS, DEBUG=False)
class OfflineSyncStackTests(TestCase):
    def setUp(self):
        cache.clear()
        CALLS["write"] = 0

    def tearDown(self):
        cache.clear()

    def test_replayed_write_through_full_stack_is_applied_once(self):
        key = _key()
        first = self.client.post("/t/write/", {"a": "1"}, HTTP_X_IDEMPOTENCY_KEY=key)
        replay = self.client.post(
            "/t/write/", {"a": "1"}, HTTP_X_IDEMPOTENCY_KEY=key, HTTP_X_OFFLINE_REPLAY="1"
        )
        self.assertEqual(first.status_code, 302)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["duplicate"], True)
        self.assertEqual(CALLS["write"], 1)

    def test_validation_failure_can_be_retried_with_same_key(self):
        key = _key()
        self.client.post("/t/write/", {"fail": "validation"}, HTTP_X_IDEMPOTENCY_KEY=key)
        self.client.post("/t/write/", {"a": "1"}, HTTP_X_IDEMPOTENCY_KEY=key)
        self.assertEqual(CALLS["write"], 2)

    def test_database_outage_in_view_returns_retryable_503_page(self):
        response = self.client.post("/t/db-down/", {"a": "1"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["X-Regi-Retryable"], "1")
        self.assertContains(response, "Temporarily unavailable", status_code=503)

    def test_database_outage_for_json_clients(self):
        response = self.client.post("/t/db-down/", {"a": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()["retryable"])

    def test_ordinary_bug_is_not_marked_retryable(self):
        response = self.client.post("/t/bug/", {"a": "1"})
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.has_header("X-Regi-Retryable"))


@override_settings(CACHES=LOCMEM, SECURE_SSL_REDIRECT=False, RATE_LIMIT_ENABLED=False)
class ServiceWorkerEndpointTests(TestCase):
    def test_service_worker_is_served_from_site_root(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/javascript"))
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn("no-cache", response["Cache-Control"])
        body = response.content.decode()
        self.assertIn("importScripts(", body)
        self.assertIn("core/js/offline-queue-db.js", body)
        self.assertIn("X-Idempotency-Key", body)

    @override_settings(OFFLINE_QUEUE_ENABLED=False)
    def test_disabled_queue_serves_self_unregistering_worker(self):
        body = self.client.get("/sw.js").content.decode()
        self.assertIn("unregister", body)
        self.assertNotIn("importScripts(", body)

    def test_service_worker_rejects_post(self):
        self.assertEqual(self.client.post("/sw.js").status_code, 405)

    def test_pages_load_queue_script_with_signed_in_user(self):
        user = User.objects.create_user(username="offline-user", password="Offline-Pass-123")
        self.client.force_login(user)
        response = self.client.get("/privacy/")
        anonymous = self.client_class().get("/privacy/")
        self.assertContains(anonymous, "core/js/offline-queue.js")
        self.assertContains(anonymous, 'data-user-id=""')
        self.assertContains(anonymous, 'data-enabled="True"')
        self.assertContains(anonymous, 'data-sw-url="/sw.js"')
        self.assertContains(response, f'data-user-id="{user.pk}"')

    @override_settings(OFFLINE_QUEUE_ENABLED=False)
    def test_pages_flag_disabled_queue(self):
        self.assertContains(self.client.get("/auth/login/"), 'data-enabled="False"')

    def test_queue_script_excludes_credentials_and_live_lookups(self):
        from django.contrib.staticfiles import finders

        with open(finders.find("core/js/offline-queue-db.js"), encoding="utf-8") as handle:
            source = handle.read()
        for word in ("auth", "admin", "api", "password", "login", "logout", "ocr", "search", "esign", "pdf"):
            self.assertIn(word, source)
