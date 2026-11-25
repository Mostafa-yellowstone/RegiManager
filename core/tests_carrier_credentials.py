from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .carrier_credentials_models import (
    CarrierCredential, CarrierCredentialLog, CredentialKeyError, decrypt_secret, encrypt_secret, usable_carrier_keys,
)
from .models import Organization
from .quote_engine.carriers import CarrierAdapter, QuoteResult
from .quote_engine.runner import run_quotes
from .tests_quote_engine import TODAY, base_auto, base_commercial


import copy
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
        from .quote_followup_models import mark_step
        r = run_for_lead(self.lead, extra)
        st = {x.carrier: x.status for x in r.results}
        self.assertEqual(st["Progressive"], "needs_input")  # driver is wired; no code entry channel in this call


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

    def _inline_jobs(self):
        from unittest import mock
        from .quote_engine.lead_bridge import run_job
        return mock.patch("core.quote_engine_views.start_job", lambda job_id, extra: run_job(job_id, extra, poll=0, wait_s=1))

    def test_save_then_run_with_login(self):
        from .quote_engine_models import QuoteEngineJob
        c = mk(self.org, otp_email="otp@agency.com"); c.set_password("x"); c.enabled = True; c.save()
        self.client.post(self.url, {"action": "save", "effective_date": "2099-01-01", "bodily_injury_limit": "25/50"})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.quote_details["bodily_injury_limit"], "25/50")
        with self._inline_jobs():
            r = self.client.post(self.url, {"action": "run", "effective_date": "2099-01-01", "bodily_injury_limit": "25/50"})
        self.assertEqual(r.status_code, 302)
        job = QuoteEngineJob.objects.get()
        self.assertEqual(job.status, "done")
        run = self.lead.engine_runs.get()
        self.assertFalse(run.blocked)
        st = self.client.get(reverse("quote-engine-job-status", args=[self.lead.id, job.id])).json()
        self.assertEqual(st["status"], "done")
        self.assertTrue(all(x["status"] != "quoted" for x in st["results"]))  # nothing fake without a real portal run
        self.assertNotIn("123456789", str(run.issues) + str(run.results))  # no license number stored

    def test_otp_endpoint_only_when_waiting_and_code_is_encrypted(self):
        from .quote_engine_models import QuoteEngineJob
        job = QuoteEngineJob.objects.create(lead=self.lead, created_by=self.su)
        url = reverse("quote-engine-job-otp", args=[self.lead.id, job.id])
        self.assertEqual(self.client.post(url, {"code": "123456"}).status_code, 409)
        job.status = "waiting_otp"; job.save()
        self.assertEqual(self.client.post(url, {"code": "12"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"code": "123 456"}).status_code, 200)
        job.refresh_from_db()
        self.assertNotIn("123456", job.otp_code_enc)
        self.assertEqual(decrypt_secret(job.otp_code_enc), "123456")

    def test_run_job_waits_for_modal_code_then_clears_it(self):
        from .quote_engine_models import QuoteEngineJob
        from .quote_engine.lead_bridge import run_job
        from .quote_engine import carriers as cmod
        c = mk(self.org); c.set_password("x"); c.enabled = True; c.save()
        got = {}
        def fn(req):
            got["code"] = req["otp_provider"](); got["user"] = req["_credential"].username
            return QuoteResult("Progressive", "quoted", premium_term=1234.5, term_months=6)
        adapter = [a for a in cmod.get_carriers() if a.key == "progressive"][0]
        old, adapter.quote_fn = adapter.quote_fn, fn
        self.addCleanup(setattr, adapter, "quote_fn", old)
        job = QuoteEngineJob.objects.create(lead=self.lead, created_by=self.su, spend_approved=True)
        def answer():
            if QuoteEngineJob.objects.get(id=job.id).status == "waiting_otp":
                QuoteEngineJob.objects.filter(id=job.id).update(otp_code_enc=encrypt_secret("654321"))
        run_job(job.id, {"effective_date": "2099-01-01", "bodily_injury_limit": "25/50"}, poll=0, wait_s=5, _tick=answer)
        job.refresh_from_db()
        self.assertEqual(got["code"], "654321")
        self.assertEqual(job.otp_code_enc, "")
        self.assertEqual(job.status, "done")

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


class FollowUpAndProgressiveTests(TestCase):
    def setUp(self):
        EnginePageTests.setUp(self)

    def test_steps_order_enforced_and_bind_human_only(self):
        from .quote_followup_models import ensure_steps, mark_step
        self.assertEqual(len(ensure_steps(self.lead)), 8)
        with self.assertRaises(ValueError):
            mark_step(self.lead, "mvr", "done")
        mark_step(self.lead, "data_entry", "done"); mark_step(self.lead, "consent", "done", user=self.su)
        mark_step(self.lead, "run_quote", "done", system=True)
        with self.assertRaises(ValueError):
            mark_step(self.lead, "bind", "done", system=True)

    def test_step_endpoint(self):
        r = self.client.post(self.url, {"action": "step", "key": "data_entry", "status": "done", "note": "ok"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.lead.followup_steps.get(key="data_entry").status, "done")
        self.client.post(self.url, {"action": "step", "key": "mvr", "status": "done"})
        self.assertEqual(self.lead.followup_steps.get(key="mvr").status, "pending")
        self.assertContains(self.client.get(self.url), "Follow-up")

    def test_runner_passes_spend_approval_flag(self):
        seen = []
        c = CarrierAdapter("progressive", "Progressive", ("auto",), spend_gate=True, quote_fn=lambda q: (seen.append(q["spend_approved"]), QuoteResult("P", "quoted", premium_term=1))[1])
        run_quotes(base_auto(), today=TODAY, carriers=[c])
        run_quotes(base_auto(), today=TODAY, carriers=[c], spend_approved=True)
        self.assertEqual(seen, [False, True])

    def test_run_button_approval_records_consent_step(self):
        from unittest import mock
        from .quote_engine.lead_bridge import run_job
        with mock.patch("core.quote_engine_views.start_job", lambda job_id, extra: run_job(job_id, extra, poll=0, wait_s=1)):
            self.client.post(self.url, {"action": "run", "effective_date": "2099-01-01", "bodily_injury_limit": "25/50", "spend_approved": "1"})
        s = self.lead.followup_steps.get(key="consent")
        self.assertEqual(s.status, "done"); self.assertEqual(s.done_by, self.su)
        self.assertContains(self.client.get(self.url), "Approve and run")

    def test_progressive_flow_with_fake_driver(self):
        from .quote_engine.adapters.progressive import PortalQuestion, run_progressive

        class Fake:
            def __init__(self, rate=None, ask=None):
                self.calls, self.rate, self.ask = [], rate, ask
            def login(self, otp): self.calls.append("login"); self.otp = otp()
            def new_auto_quote(self, state): self.calls.append(("new", state))
            def enter_drivers(self, d, a): self.calls.append("drivers"); self.answers = a
            def enter_vehicles(self, v, a):
                if self.ask: raise PortalQuestion(self.ask)
                self.calls.append("vehicles")
            def set_coverage(self, c): self.calls.append("cov"); self.cov = c
            def go_to_point_of_sale(self): self.calls.append("pos")
            def read_rate(self): return self.rate
            def screenshot(self): return ""
            def close(self): self.calls.append("close")
        req = base_auto()
        # no consent: nothing touches the portal
        d = Fake(); r = run_progressive(req, d, lambda: "123456", spend_approved=False)
        self.assertEqual(r.status, "needs_approval")
        self.assertNotIn("pos", d.calls)  # stopped right before the money step
        self.assertIn("login", d.calls)   # but everything before ran automatically, OTP included
        self.assertEqual(d.otp, "123456")
        d = Fake(rate={"premium_term": 900.0, "premium_monthly": 150.0, "term_months": 6, "ref": "Q9", "alerts": ["PBV required"]})
        r = run_progressive(req, d, lambda: "123456", spend_approved=True)
        self.assertEqual((r.status, r.premium_term, r.quote_ref), ("quoted", 900.0, "Q9"))
        self.assertEqual(d.cov["bi_pd"], "25/50/25"); self.assertEqual(d.answers["annual_miles"], 10000)
        self.assertEqual(d.calls[:2], ["login", ("new", "NY")]); self.assertEqual(d.calls[-1], "close")
        d = Fake(ask="Prior carrier?")
        r = run_progressive(req, d, lambda: "1", spend_approved=True)
        self.assertEqual(r.status, "needs_input"); self.assertIn("Prior carrier?", r.detail)
        self.assertEqual(r.extra["steps_done"], ["login", "new_quote", "drivers"])
        d = Fake(rate={"premium_term": 0, "alerts": ["Not eligible"]})
        self.assertEqual(run_progressive(req, d, lambda: "1", spend_approved=True).status, "declined")
        # liability vs full, owned vs financed
        d = Fake(rate={"premium_term": 500.0})
        run_progressive(req, d, lambda: "1", spend_approved=True)
        self.assertFalse(d.cov["vehicles"][0]["comp_collision"])
        r2 = copy.deepcopy(req); r2["vehicles"][0].update(coverage="full", ownership="financed", lienholder="Chase")
        d = Fake(rate={"premium_term": 700.0}); run_progressive(r2, d, lambda: "1", spend_approved=True)
        self.assertEqual((d.cov["vehicles"][0]["comp_collision"], d.cov["vehicles"][0]["lienholder"]), (True, "Chase"))
        r3 = copy.deepcopy(req); r3["vehicles"][0].update(coverage="liability", ownership="financed", lienholder="Chase")
        self.assertIn("lender requires full", run_progressive(r3, Fake(), lambda: "1", spend_approved=True).detail)
        r4 = copy.deepcopy(req); r4["vehicles"][0].update(coverage="full", ownership="financed")
        self.assertIn("lienholder", run_progressive(r4, Fake(), lambda: "1", spend_approved=True).detail)
        c = base_commercial()
        self.assertEqual(run_progressive(c, Fake(), lambda: "1", spend_approved=True).status, "skipped")


class KeyFallbackTests(TestCase):
    def test_works_without_env_key_and_survives_adding_it_later(self):
        os.environ.pop("CARRIER_CRED_KEY", None)
        token = encrypt_secret("pw1")  # saved with the derived key
        self.assertEqual(decrypt_secret(token), "pw1")
        os.environ["CARRIER_CRED_KEY"] = Fernet.generate_key().decode()
        try:
            self.assertEqual(decrypt_secret(token), "pw1")       # old data still readable
            new = encrypt_secret("pw2")                          # new data uses the env key
            self.assertEqual(decrypt_secret(new), "pw2")
            os.environ.pop("CARRIER_CRED_KEY")
            with self.assertRaises(CredentialKeyError):
                decrypt_secret(new)                              # env key lost: new data unreadable
        finally:
            os.environ["CARRIER_CRED_KEY"] = Fernet.generate_key().decode()
