import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.assistant import MAX_MESSAGE_CHARS, SYSTEM_PROMPT

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "assistant-tests"}}
PUBLIC_IP = "93.184.216.34"
BASE = dict(
    CACHES=LOCMEM,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    RATE_LIMIT_ENABLED=False,
    GEMINI_API_KEY="test-key",
    GEMINI_MODELS="primary-model,backup-model",
    ASSISTANT_DAILY_LIMIT=1000,
    ASSISTANT_PER_VISITOR_DAILY_LIMIT=80,
)


def _gemini_ok(text="Use form MV-82 and confirm on dmv.ny.gov."):
    response = mock.Mock(status_code=200)
    response.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return response


def _gemini_status(code):
    return mock.Mock(status_code=code, json=mock.Mock(return_value={}))


@override_settings(**BASE)
class AssistantChatTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _ask(self, messages=None, language="en", **extra):
        body = {"language": language, "messages": messages or [{"role": "user", "content": "How do I renew?"}]}
        extra.setdefault("REMOTE_ADDR", PUBLIC_IP)
        return self.client.post(
            reverse("assistant-chat"), data=json.dumps(body), content_type="application/json", **extra
        )

    @mock.patch("core.assistant.requests.post")
    def test_answers_question_with_gemini_reply(self, post):
        post.return_value = _gemini_ok()
        response = self._ask()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "reply": "Use form MV-82 and confirm on dmv.ny.gov.", "language": "en"})
        url = post.call_args.args[0]
        self.assertIn("primary-model:generateContent", url)
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")

    @mock.patch("core.assistant.requests.post")
    def test_chosen_language_is_enforced_in_system_prompt(self, post):
        post.return_value = _gemini_ok("Utilice el formulario MV-82.")
        self._ask(language="es")
        sent = json.loads(post.call_args.kwargs["data"])
        system = sent["system_instruction"]["parts"][0]["text"]
        self.assertIn("Always reply in Spanish", system)

    @mock.patch("core.assistant.requests.post")
    def test_unknown_language_falls_back_to_english(self, post):
        post.return_value = _gemini_ok()
        self._ask(language="xx")
        system = json.loads(post.call_args.kwargs["data"])["system_instruction"]["parts"][0]["text"]
        self.assertIn("Always reply in English", system)

    @mock.patch("core.assistant.requests.post")
    def test_history_is_mapped_trimmed_and_starts_with_user(self, post):
        post.return_value = _gemini_ok()
        messages = [{"role": "assistant", "content": "Hi! What would you like to know?"}]
        for i in range(10):
            messages.append({"role": "user", "content": f"question {i}"})
            messages.append({"role": "assistant", "content": f"answer {i}"})
        messages.append({"role": "user", "content": "final question"})
        self._ask(messages=messages)
        contents = json.loads(post.call_args.kwargs["data"])["contents"]
        self.assertLessEqual(len(contents), 12)
        self.assertEqual(contents[0]["role"], "user")
        self.assertEqual(contents[-1], {"role": "user", "parts": [{"text": "final question"}]})
        self.assertTrue(all(c["role"] in {"user", "model"} for c in contents))

    @mock.patch("core.assistant.requests.post")
    def test_busy_primary_model_falls_back_to_backup(self, post):
        post.side_effect = [_gemini_status(429), _gemini_ok("Backup answer")]
        response = self._ask()
        self.assertEqual(response.json()["reply"], "Backup answer")
        self.assertIn("backup-model", post.call_args.args[0])

    @mock.patch("core.assistant.requests.post")
    def test_all_models_busy_returns_friendly_message(self, post):
        post.return_value = _gemini_status(429)
        response = self._ask()
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json()["ok"])
        self.assertIn("(914) 292-9743", response.json()["reply"])

    @mock.patch("core.assistant.requests.post")
    def test_network_failure_returns_friendly_message(self, post):
        import requests

        post.side_effect = requests.ConnectionError("down")
        response = self._ask()
        self.assertEqual(response.status_code, 502)
        self.assertIn("try again", response.json()["reply"])

    @mock.patch("core.assistant.requests.post")
    def test_thought_parts_are_not_shown(self, post):
        reply = mock.Mock(status_code=200)
        reply.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "internal", "thought": True}, {"text": "Visible answer"}]}}]
        }
        post.return_value = reply
        self.assertEqual(self._ask().json()["reply"], "Visible answer")

    def test_rejects_bad_payloads(self):
        bad = self.client.post(reverse("assistant-chat"), data="not json", content_type="application/json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self._ask(messages=[{"role": "assistant", "content": "hi"}]).status_code, 400)
        self.assertEqual(self._ask(messages=[{"role": "user", "content": "   "}]).status_code, 400)
        too_long = self._ask(messages=[{"role": "user", "content": "x" * (MAX_MESSAGE_CHARS + 1)}])
        self.assertEqual(too_long.status_code, 400)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("assistant-chat")).status_code, 405)

    @override_settings(GEMINI_API_KEY="")
    def test_unconfigured_assistant_is_reported_politely(self):
        response = self._ask()
        self.assertEqual(response.status_code, 503)
        self.assertIn("isn't available", response.json()["reply"])

    @mock.patch("core.assistant.requests.post")
    def test_per_visitor_burst_limit(self, post):
        post.return_value = _gemini_ok()
        statuses = [self._ask().status_code for _ in range(10)]
        self.assertEqual(statuses.count(200), 8)
        self.assertEqual(statuses[-1], 429)
        self.assertEqual(post.call_count, 8)

    @override_settings(ASSISTANT_DAILY_LIMIT=3)
    @mock.patch("core.assistant.requests.post")
    def test_global_daily_cap_keeps_usage_in_free_tier(self, post):
        post.return_value = _gemini_ok()
        statuses = []
        for i in range(5):
            statuses.append(self._ask(REMOTE_ADDR=f"93.184.216.{10 + i}").status_code)
        self.assertEqual(statuses[:3], [200, 200, 200])
        self.assertEqual(statuses[3:], [429, 429])
        self.assertEqual(post.call_count, 3)

    def test_csrf_is_required(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        response = strict.post(
            reverse("assistant-chat"),
            data=json.dumps({"messages": [{"role": "user", "content": "hi"}]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


@override_settings(**BASE)
class AssistantWidgetTests(TestCase):
    def test_widget_is_on_public_pages_when_configured(self):
        response = self.client.get("/privacy/")
        self.assertContains(response, 'id="rm-assistant"')
        self.assertContains(response, reverse("assistant-chat"))
        self.assertContains(response, "core/js/assistant.js")
        self.assertContains(response, 'data-lang="ar"')
        self.assertContains(response, 'data-lang="es"')
        self.assertContains(response, "csrfmiddlewaretoken")

    @override_settings(GEMINI_API_KEY="")
    def test_widget_hidden_without_api_key(self):
        self.assertNotContains(self.client.get("/privacy/"), 'id="rm-assistant"')

    def test_prompt_covers_requested_services_and_safety(self):
        for topic in ("registration", "renewal", "plate transfer", "title", "TLC", "insurance", "MV-82", "dmv.ny.gov"):
            self.assertIn(topic.lower(), SYSTEM_PROMPT.lower())
        self.assertIn("Never invent exact amounts", SYSTEM_PROMPT)
        self.assertIn("personal data", SYSTEM_PROMPT)

    def test_offline_queue_never_queues_assistant_requests(self):
        from django.contrib.staticfiles import finders

        with open(finders.find("core/js/offline-queue-db.js"), encoding="utf-8") as handle:
            self.assertIn("assistant", handle.read())
