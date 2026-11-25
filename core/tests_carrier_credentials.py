from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .carrier_credentials_models import (
    CarrierCredential, CarrierCredentialLog, CredentialKeyError, decrypt_secret, encrypt_secret, usable_carrier_keys,
)
from .models import Organization
from .quote_engine.carriers import CarrierAdapter, QuoteResult
from .quote_engine.runner import run_quotes
from .tests_quote_engine import TODAY, base_auto


import os
from cryptography.fernet import Fernet


def setUpModule():
    os.environ["CARRIER_CRED_KEY"] = Fernet.generate_key().decode()


def tearDownModule():
    os.environ.pop("CARRIER_CRED_KEY", None)


def mk(org, **kw):
    d = dict(organization=org, carrier_key="progressive", line="auto", label="main", username="u")
    d.update(kw)
    return CarrierCredential.objects.create(**d)


class CredentialTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org")

    def test_roundtrip_and_not_plaintext(self):
        c = mk(self.org)
        c.set_password("S3cret!")
        c.save()
        c.refresh_from_db()
        self.assertNotIn("S3cret", c.password_enc)
        self.assertEqual(c.get_password(actor="t", purpose="test"), "S3cret!")
        self.assertEqual(c.logs.filter(action="used").count(), 1)
        self.assertNotIn("S3cret", " ".join(c.logs.values_list("detail", flat=True)))

    def test_tampered_token_fails(self):
        with self.assertRaises(CredentialKeyError):
            decrypt_secret("not-a-token")
        self.assertNotEqual(encrypt_secret("a"), encrypt_secret("a"))  # random IV

    def test_disabled_by_default_and_usable_keys(self):
        c = mk(self.org)
        self.assertFalse(c.enabled)
        c.set_password("x"); c.enabled = True; c.save()
        mk(self.org, carrier_key="travelers", label="x").save()  # enabled False, no password
        self.assertEqual(usable_carrier_keys(self.org, "auto"), {"progressive"})
        self.assertEqual(usable_carrier_keys(self.org, "commercial_auto"), set())

    def test_auto_disable_after_failures_and_lock(self):
        c = mk(self.org); c.set_password("x"); c.enabled = True; c.save()
        c.record_result(False, error="bad pw"); c.record_result(False, error="bad pw")
        c.refresh_from_db(); self.assertTrue(c.enabled)
        c.record_result(False, error="bad pw"); c.refresh_from_db()
        self.assertFalse(c.enabled)
        c.enabled = True; c.save(); c.record_result(True); c.refresh_from_db()
        self.assertEqual((c.status, c.consecutive_failures), ("ok", 0))
        c.record_result(False, status="locked", error="locked"); c.refresh_from_db()
        self.assertFalse(c.enabled)

    def test_runner_skips_carriers_without_enabled_login(self):
        ok = lambda req: QuoteResult("A", "quoted", premium_term=500)
        cs = [CarrierAdapter("a", "A", ("auto",), quote_fn=ok), CarrierAdapter("b", "B", ("auto",), quote_fn=ok)]
        r = run_quotes(base_auto(), carriers=cs, today=TODAY, allowed_keys={"a"})
        st = {x.carrier: x.status for x in r.results}
        self.assertEqual(st, {"A": "quoted", "B": "skipped"})


class AdminTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org")
        self.su = get_user_model().objects.create_superuser("root", "r@x.com", "pw")
        self.client.force_login(self.su)

    def test_form_is_write_only_and_encrypts(self):
        r = self.client.post(reverse("admin:core_carriercredential_add"), {
            "organization": self.org.pk, "carrier_key": "progressive", "line": "auto", "label": "main",
            "portal_url": "", "username": "agent1", "new_password": "Hunter2!x", "status": "untested", "enabled": "on",
            "logs-TOTAL_FORMS": 0, "logs-INITIAL_FORMS": 0,
        })
        self.assertEqual(r.status_code, 302)
        c = CarrierCredential.objects.get()
        self.assertTrue(c.enabled)
        self.assertEqual(c.get_password(), "Hunter2!x")
        page = self.client.get(reverse("admin:core_carriercredential_change", args=[c.pk])).content.decode()
        self.assertNotIn("Hunter2", page)
        self.assertNotIn(c.password_enc, page)
        self.assertTrue(CarrierCredentialLog.objects.filter(credential=c, action="created").exists())

    def test_cannot_enable_without_password(self):
        r = self.client.post(reverse("admin:core_carriercredential_add"), {
            "organization": self.org.pk, "carrier_key": "progressive", "line": "auto", "label": "m",
            "username": "u", "status": "untested", "enabled": "on", "logs-TOTAL_FORMS": 0, "logs-INITIAL_FORMS": 0,
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(CarrierCredential.objects.count(), 0)
