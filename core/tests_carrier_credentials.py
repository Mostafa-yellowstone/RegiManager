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


class LeadBridgeTests(TestCase):
    def setUp(self):
        from datetime import date
        from .models import InsuranceQuoteLead
        self.org = Organization.objects.create(name="Org")
        self.lead = InsuranceQuoteLead.objects.create(
            organization=self.org, client_name="Ann Lee", phone="(718) 623-0134", email="a@b.com",
            street_address="12 Main St", city="Brooklyn", state="NY", zip_code="11201",
            insurance_type="auto_personal", vin="1HGCM82633A004352", vehicle_year="2003",
            vehicle_make="Honda", vehicle_model="Accord", dl_number="123456789",
            date_of_birth=date(1985, 4, 2), vehicle_ownership="owned", has_prior=False,
        )

    def test_maps_lead_data_without_inventing(self):
        from .quote_engine.lead_bridge import lead_to_request
        r = lead_to_request(self.lead)
        self.assertEqual(r["line_of_business"], "auto")
        self.assertEqual(r["drivers"][0]["first_name"], "Ann")
        self.assertEqual(r["drivers"][0]["last_name"], "Lee")
        self.assertEqual(r["vehicles"][0]["vin"], "1HGCM82633A004352")
        self.assertNotIn("effective_date", r)
        self.assertNotIn("bodily_injury_limit", r)

    def test_missing_fields_reported_then_extra_fills_them(self):
        from .quote_engine.lead_bridge import missing_fields
        codes_ = {m["code"] for m in missing_fields(self.lead)}
        self.assertTrue({"date_invalid", "limit_invalid"} <= codes_)
        extra = {"effective_date": "2099-01-01", "bodily_injury_limit": "25/50"}
        self.assertEqual(missing_fields(self.lead, extra), [])

    def test_commercial_lead_needs_business_data(self):
        from .quote_engine.lead_bridge import missing_fields
        self.lead.insurance_type = "trucking"
        c = {m["field"] for m in missing_fields(self.lead)}
        self.assertIn("business.legal_name", c)

    def test_unsupported_line_blocked(self):
        from .quote_engine.lead_bridge import run_for_lead
        self.lead.insurance_type = "home_owners"
        r = run_for_lead(self.lead)
        self.assertTrue(r.blocked)
        self.assertEqual(r.issues[0].code, "lob_invalid")

    def test_run_uses_only_enabled_logins(self):
        from .quote_engine.lead_bridge import run_for_lead
        extra = {"effective_date": "2099-01-01", "bodily_injury_limit": "25/50"}
        r = run_for_lead(self.lead, extra)
        self.assertFalse(r.blocked)
        self.assertTrue(all(x.status == "skipped" for x in r.results))
        c = mk(self.org); c.set_password("x"); c.enabled = True; c.save()
        r = run_for_lead(self.lead, extra)
        st = {x.carrier: x.status for x in r.results}
        self.assertEqual(st["Progressive"], "not_implemented")


class EnginePageTests(TestCase):
    def setUp(self):
        from datetime import date
        from .models import InsuranceQuoteLead
        self.org = Organization.objects.create(name="Org")
        self.su = get_user_model().objects.create_superuser("root2", "r2@x.com", "pw")
        self.client.force_login(self.su)
        s = self.client.session; s["active_org_id"] = self.org.id; s.save()
        self.lead = InsuranceQuoteLead.objects.create(
            organization=self.org, client_name="Ann Lee", phone="(718) 623-0134", email="a@b.com",
            street_address="12 Main St", city="Brooklyn", state="NY", zip_code="11201",
            insurance_type="auto_personal", vin="1HGCM82633A004352", vehicle_year="2003",
            vehicle_make="Honda", vehicle_model="Accord", dl_number="123456789",
            date_of_birth=date(1985, 4, 2), vehicle_ownership="owned")
        self.url = reverse("quote-engine-lead", args=[self.lead.id])

    def test_page_lists_missing_fields(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Needs fixing")
        self.assertContains(r, "Run quotes")

    def test_blocked_run_saves_history_and_sends_nothing(self):
        r = self.client.post(self.url, {"action": "run"})
        self.assertEqual(r.status_code, 200)
        run = self.lead.engine_runs.get()
        self.assertTrue(run.blocked)
        self.assertEqual(run.results, [])

    def test_save_then_run_with_login(self):
        c = mk(self.org, otp_email="otp@agency.com"); c.set_password("x"); c.enabled = True; c.save()
        self.client.post(self.url, {"action": "save", "effective_date": "2099-01-01", "bodily_injury_limit": "25/50"})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.quote_details["bodily_injury_limit"], "25/50")
        r = self.client.post(self.url, {"action": "run", "effective_date": "2099-01-01", "bodily_injury_limit": "25/50"})
        self.assertContains(r, "Progressive")
        self.assertContains(r, "Not")  # not implemented, no fake price
        run = self.lead.engine_runs.get()
        self.assertFalse(run.blocked)
        self.assertNotIn("123456789", str(run.issues) + str(run.results))  # no license number stored

    def test_otp_email_reaches_adapter_only_for_that_carrier(self):
        from .carrier_credentials_models import carrier_otp_emails
        c = mk(self.org, otp_email="otp@agency.com"); c.set_password("x"); c.enabled = True; c.save()
        seen = {}
        def fn(req):
            seen.update(req); return QuoteResult("P", "quoted", premium_term=1)
        cs = [CarrierAdapter("progressive", "P", ("auto",), quote_fn=fn), CarrierAdapter("other", "O", ("auto",), quote_fn=lambda r: (seen.update(o=r.get("otp_email")), QuoteResult("O", "quoted", premium_term=2))[1])]
        run_quotes(base_auto(), carriers=cs, today=TODAY, carrier_emails=carrier_otp_emails(self.org, "auto"))
        self.assertEqual(seen["otp_email"], "otp@agency.com")
        self.assertIsNone(seen["o"])

    def test_additional_driver_and_vehicle_included(self):
        from .insurance_quote_pipeline_models import InsuranceQuoteLeadDriver, InsuranceQuoteLeadVehicle
        from .quote_engine.lead_bridge import lead_to_request
        InsuranceQuoteLeadDriver.objects.create(lead=self.lead, full_name="Bob Lee", dl_number="987654321")
        InsuranceQuoteLeadVehicle.objects.create(lead=self.lead, make="Toyota", model="Camry", year="2010", vin="")
        r = lead_to_request(self.lead)
        self.assertEqual(len(r["drivers"]), 2)
        self.assertEqual(len(r["vehicles"]), 2)

    def test_quoted_results_go_to_pipeline_once(self):
        from .insurance_desk_models import InsuranceQuoteOption
        from .quote_engine.lead_bridge import file_results_to_pipeline
        from .quote_engine.runner import RunReport
        rep = RunReport(issues=[], results=[QuoteResult("Progressive", "quoted", premium_term=812.5, term_months=6, quote_ref="Q1"),
                                            QuoteResult("Travelers", "declined"), QuoteResult("Safeco", "not_implemented")])
        self.assertEqual(file_results_to_pipeline(self.lead, rep), 1)
        self.assertEqual(file_results_to_pipeline(self.lead, rep), 0)
        o = InsuranceQuoteOption.objects.get(lead=self.lead)
        self.assertEqual((o.carrier_name, str(o.term_premium)), ("Progressive", "812.50"))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.stage, "quoted")


class OtpTests(TestCase):
    def test_extract_code_variants(self):
        from .quote_engine.otp import extract_code
        cases = {
            "Your Progressive verification code is 482913. It expires in 10 minutes.": "482913",
            "482913 is your security code": "482913",
            "<p>Use passcode: <b>73 1 ...</b> 905511 to sign in</p>": "905511",
            "Your OTP: 1234": "1234",
            "Total due $123456 on invoice": None,
            "Hello, nothing here": None,
        }
        for text, want in cases.items():
            self.assertEqual(extract_code(text), want, text)

    def _mb(self, items):
        class MB:
            def recent(self, since):
                return items
        return MB()

    def test_picks_newest_fresh_trusted_code(self):
        from datetime import datetime, timedelta, timezone
        from .quote_engine.otp import MailItem, fetch_otp
        t0 = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
        items = [
            MailItem("no-reply@progressive.com", "Code", "Your code is 111111", t0 - timedelta(minutes=5)),  # stale
            MailItem("phisher@evil.com", "Code", "Your code is 222222", t0 + timedelta(seconds=5)),  # wrong sender
            MailItem("no-reply@progressive.com", "Code", "Your code is 333333", t0 + timedelta(seconds=10)),
            MailItem("no-reply@progressive.com", "Code", "Your code is 444444", t0 + timedelta(seconds=20)),
        ]
        self.assertEqual(fetch_otp(self._mb(items), ["progressive.com"], t0, sleep=lambda s: None), "444444")

    def test_timeout_raises(self):
        from datetime import datetime, timezone
        from .quote_engine.otp import OtpNotFound, fetch_otp
        clock = iter(range(0, 1000, 30))
        with self.assertRaises(OtpNotFound):
            fetch_otp(self._mb([]), ["x.com"], datetime(2026, 1, 1, tzinfo=timezone.utc), timeout_s=60,
                      sleep=lambda s: None, now=lambda: next(clock))

    def test_naive_time_rejected(self):
        from datetime import datetime
        from .quote_engine.otp import fetch_otp
        with self.assertRaises(ValueError):
            fetch_otp(self._mb([]), [], datetime(2026, 1, 1))

    def test_mailbox_password_encrypted_and_logged(self):
        org = Organization.objects.create(name="O")
        c = mk(org, otp_email="otp@a.com", otp_imap_host="imap.example.com")
        self.assertIsNone(c.otp_mailbox())
        c.set_otp_mailbox_password("mailpw-XYZ"); c.save()
        self.assertNotIn("mailpw-XYZ", c.otp_imap_password_enc)
        mb = c.otp_mailbox(actor="t")
        self.assertEqual((mb.host, mb.user, mb.password), ("imap.example.com", "otp@a.com", "mailpw-XYZ"))
        self.assertTrue(c.logs.filter(action="otp_mailbox_used").exists())
