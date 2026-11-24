"""Quote-job behavior. No database and no portal login."""

from __future__ import annotations

import json
import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from quoting.carriers.base import CarrierAdapter
from quoting.carriers.common import PortalChallenge, PortalQuote, quoted_offer
from quoting.carriers.fixtures import fixture_offer
from quoting.carriers.registry import CarrierRegistry
from quoting.demo.scenarios import assigned, business_use, clean, lapse, mvr, out_of_state, referral
from quoting.demo.server import check_scenarios
from quoting.engine.job import run_quote_job
from quoting.engine.secrets import status_for
from quoting.engine.types import Application
from quoting.intake import parse_form
from quoting.present import render_desk
from quoting.service import run_from_form

TODAY = date(2026, 11, 24)
SECRET = "portal-password-should-not-leak"
SECRET_NAMES = (
    "PROGRESSIVE_AGENT_PORTAL_USERNAME",
    "PROGRESSIVE_AGENT_PORTAL_PASSWORD",
    "NATIONAL_GENERAL_AGENT_PORTAL_USERNAME",
    "NATIONAL_GENERAL_AGENT_PORTAL_PASSWORD",
    "NYAIP_AGENT_PORTAL_USERNAME",
    "NYAIP_AGENT_PORTAL_PASSWORD",
)


def _by_key(result):
    return {item.carrier_key: item for item in result.results}


class QuoteJobTests(unittest.TestCase):
    def test_clean_risk_quotes_voluntary_carriers_and_stops_assigned_risk(self):
        result = run_from_form(clean(TODAY), mode="demo", today=TODAY)
        self.assertEqual(result.status, "completed")
        rows = _by_key(result)
        self.assertEqual(rows["progressive"].status, "quoted")
        self.assertEqual(rows["national_general"].status, "quoted")
        self.assertTrue(rows["progressive"].offer.illustrative)
        self.assertTrue(rows["progressive"].offer.quote_number.startswith("DEMO-PGR-"))
        self.assertEqual(rows["progressive"].offer.term_premium, Decimal("1381.87"))
        self.assertEqual(rows["national_general"].offer.term_premium, Decimal("1464.39"))
        self.assertEqual(rows["nyaip"].status, "blocked")
        self.assertIsNone(rows["nyaip"].offer)
        self.assertEqual(rows["nyaip"].blocker.code, "special_case")
        self.assertIn("voluntary carrier declined", rows["nyaip"].blocker.missing[0])

    def test_mvr_stops_every_carrier_and_names_the_driver(self):
        result = run_from_form(mvr(TODAY), mode="demo", today=TODAY)
        self.assertEqual(result.status, "completed")
        for item in result.results:
            self.assertEqual(item.status, "blocked")
            self.assertIsNone(item.offer)
            self.assertEqual(item.blocker.code, "mvr_required")
            self.assertEqual(item.blocker.missing, ("motor vehicle report for Maya Hassan",))

    def test_referral_does_not_invent_a_progressive_premium(self):
        result = run_from_form(referral(TODAY), mode="demo", today=TODAY)
        rows = _by_key(result)
        self.assertEqual(rows["progressive"].blocker.code, "underwriting_referral")
        self.assertEqual(rows["progressive"].blocker.origin, "demo")
        self.assertIsNone(rows["progressive"].offer)
        self.assertIn("Maya Hassan", rows["progressive"].blocker.missing[0])
        self.assertEqual(rows["national_general"].status, "quoted")
        self.assertEqual(rows["nyaip"].blocker.code, "special_case")

    def test_assigned_risk_quotes_only_after_a_declination(self):
        result = run_from_form(assigned(TODAY), mode="demo", today=TODAY)
        rows = _by_key(result)
        self.assertEqual(rows["progressive"].blocker.code, "underwriting_referral")
        self.assertEqual(rows["national_general"].status, "quoted")
        self.assertEqual(rows["nyaip"].status, "quoted")
        self.assertIn("Progressive", rows["nyaip"].offer.note)
        self.assertTrue(rows["nyaip"].offer.quote_number.startswith("DEMO-NYAIP-"))
        self.assertGreater(rows["nyaip"].offer.term_premium, rows["national_general"].offer.term_premium)

    def test_missing_lapse_reason_is_named(self):
        result = run_from_form(lapse(TODAY), mode="demo", today=TODAY)
        for item in result.results:
            self.assertEqual(item.blocker.code, "special_case")
            self.assertEqual(item.blocker.missing, ("reason the applicant has no current policy",))
            self.assertIsNone(item.offer)

    def test_business_use_and_out_of_state_license_stop(self):
        business = run_from_form(business_use(TODAY), mode="demo", today=TODAY)
        self.assertTrue(all(item.blocker.code == "special_case" for item in business.results))
        self.assertIn("commercial auto quote", business.results[0].blocker.missing[0])
        license_stop = run_from_form(out_of_state(TODAY), mode="demo", today=TODAY)
        self.assertIn("NJ", license_stop.results[0].blocker.missing[0])

    def test_intake_rejects_another_state_and_a_half_specified_deductible(self):
        other_state = clean(TODAY)
        other_state["insured_state"] = "NJ"
        result = run_from_form(other_state, mode="demo", today=TODAY)
        self.assertEqual(result.status, "intake_incomplete")
        self.assertEqual(result.results, ())
        self.assertTrue(any(issue.field == "insured_state" for issue in result.issues))

        mismatch = clean(TODAY)
        mismatch["coverage_coll"] = "none"
        result = run_from_form(mismatch, mode="demo", today=TODAY)
        self.assertEqual(result.status, "intake_incomplete")
        self.assertTrue(any("both" in issue.message for issue in result.issues))

    def test_unknown_line_does_not_call_carriers(self):
        application, _invalid = parse_form(clean(TODAY))
        other = Application(
            line="homeowners",
            jurisdiction="NY",
            effective_date=application.effective_date,
            named_insured=application.named_insured,
            drivers=application.drivers,
            vehicles=application.vehicles,
            coverage=application.coverage,
            prior=application.prior,
            voluntary_market_declined=False,
            declination_carrier="",
            mvr_pending=False,
        )
        result = run_quote_job(other, mode="demo", today=TODAY)
        self.assertEqual(result.results, ())
        self.assertIn("New York personal auto", result.issues[0].message)

    def test_live_mode_reports_secret_names_and_not_values(self):
        planted = {name: SECRET if name.endswith("PASSWORD") else "agent-user" for name in SECRET_NAMES}
        previous = {name: os.environ.get(name) for name in SECRET_NAMES}
        try:
            for name in SECRET_NAMES:
                os.environ.pop(name, None)
            missing = run_from_form(clean(TODAY), mode="live", today=TODAY)
            blob = json.dumps(missing.to_dict())
            self.assertNotIn(SECRET, blob)
            rows = _by_key(missing)
            for key in ("progressive", "national_general"):
                self.assertEqual(rows[key].status, "needs_credentials")
                self.assertIsNone(rows[key].offer)
                self.assertTrue(all(name.isupper() for name in rows[key].blocker.missing))
            self.assertEqual(rows["nyaip"].blocker.code, "special_case")
            os.environ.update(planted)
            ready = run_from_form(clean(TODAY), mode="live", today=TODAY)
            ready_blob = json.dumps(ready.to_dict())
            self.assertNotIn(SECRET, ready_blob)
            self.assertNotIn("agent-user", ready_blob)
            ready_rows = _by_key(ready)
            for key in ("progressive", "national_general"):
                self.assertEqual(ready_rows[key].blocker.code, "interactive_login_required")
                self.assertIsNone(ready_rows[key].offer)
            self.assertEqual(ready_rows["nyaip"].blocker.code, "special_case")
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_live_mode_does_not_apply_the_demo_referral_rule(self):
        previous = os.environ.get("PROGRESSIVE_AGENT_PORTAL_PASSWORD")
        os.environ.pop("PROGRESSIVE_AGENT_PORTAL_PASSWORD", None)
        try:
            result = run_from_form(referral(TODAY), mode="live", today=TODAY)
        finally:
            if previous is None:
                os.environ.pop("PROGRESSIVE_AGENT_PORTAL_PASSWORD", None)
            else:
                os.environ["PROGRESSIVE_AGENT_PORTAL_PASSWORD"] = previous
        progressive = _by_key(result)["progressive"]
        self.assertEqual(progressive.status, "needs_credentials")
        self.assertNotEqual(progressive.blocker.code, "underwriting_referral")

    def test_mvr_still_stops_in_live_mode_when_credentials_exist(self):
        previous = {name: os.environ.get(name) for name in SECRET_NAMES}
        try:
            for name in SECRET_NAMES:
                os.environ[name] = "configured"
            result = run_from_form(mvr(TODAY), mode="live", today=TODAY)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        for item in result.results:
            self.assertEqual(item.blocker.code, "mvr_required")
            self.assertNotIn("configured", json.dumps(item.to_dict()))

    def test_bot_check_stops_without_submitting(self):
        class Session:
            def __init__(self):
                self.submitted = False

            def ensure_ready(self):
                raise PortalChallenge("bot_check", "National General showed a bot check.")

            def submit_quote(self, application):
                self.submitted = True
                raise AssertionError("submit must not run after a bot check")

        session = Session()
        previous = {name: os.environ.get(name) for name in SECRET_NAMES}
        try:
            for name in SECRET_NAMES:
                os.environ[name] = "configured"
            result = run_from_form(
                clean(TODAY),
                mode="live",
                today=TODAY,
                sessions={"national_general": session},
            )
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        national = _by_key(result)["national_general"]
        self.assertFalse(session.submitted)
        self.assertEqual(national.blocker.code, "portal_challenge")
        self.assertIn("bot check", national.blocker.missing[0])
        self.assertIsNone(national.offer)

    def test_empty_carrier_selection_does_not_quote_anyone(self):
        form = clean(TODAY)
        form["carriers"] = []
        result = run_from_form(form, mode="demo", today=TODAY)
        self.assertEqual(result.status, "intake_incomplete")
        self.assertEqual(result.results, ())
        self.assertTrue(any(issue.field == "carriers" for issue in result.issues))

    def test_declination_without_a_carrier_name_stops_assigned_risk(self):
        form = clean(TODAY)
        form["voluntary_market_declined"] = "yes"
        form["declination_carrier"] = ""
        result = run_from_form(form, mode="demo", today=TODAY)
        nyaip = _by_key(result)["nyaip"]
        self.assertEqual(nyaip.status, "blocked")
        self.assertIsNone(nyaip.offer)
        self.assertIn("name of the voluntary carrier that declined", nyaip.blocker.missing[0])

    def test_mfa_challenge_stops_that_carrier_without_submitting(self):
        class Session:
            def __init__(self):
                self.submitted = False

            def ensure_ready(self):
                raise PortalChallenge("mfa", "Progressive asked for a one-time passcode.")

            def submit_quote(self, application):
                self.submitted = True
                raise AssertionError("submit must not run after MFA")

        session = Session()
        previous = {name: os.environ.get(name) for name in SECRET_NAMES}
        try:
            for name in SECRET_NAMES:
                os.environ[name] = "configured"
            result = run_from_form(
                clean(TODAY),
                mode="live",
                today=TODAY,
                sessions={"progressive": session},
            )
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        progressive = _by_key(result)["progressive"]
        self.assertFalse(session.submitted)
        self.assertEqual(progressive.blocker.code, "portal_challenge")
        self.assertIn("MFA", progressive.blocker.missing[0])
        self.assertIsNone(progressive.offer)
        self.assertEqual(_by_key(result)["national_general"].blocker.code, "interactive_login_required")

    def test_a_portal_quote_is_used_and_an_incomplete_one_is_not_filled_in(self):
        class Session:
            def __init__(self, payload):
                self.payload = payload

            def ensure_ready(self):
                return None

            def submit_quote(self, application):
                return self.payload

        previous = {name: os.environ.get(name) for name in SECRET_NAMES}
        try:
            for name in SECRET_NAMES:
                os.environ[name] = "configured"
            quoted = run_from_form(
                clean(TODAY),
                mode="live",
                today=TODAY,
                sessions={
                    "progressive": Session(
                        PortalQuote("PGR-100", Decimal("900.00"), 6, note="Returned by the portal.")
                    )
                },
            )
            incomplete = run_from_form(
                clean(TODAY),
                mode="live",
                today=TODAY,
                sessions={"progressive": Session(PortalQuote("", Decimal("0"), 6))},
            )
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        offer = _by_key(quoted)["progressive"].offer
        self.assertEqual(offer.quote_number, "PGR-100")
        self.assertEqual(offer.term_premium, Decimal("900.00"))
        self.assertEqual(offer.source, "portal")
        self.assertFalse(offer.illustrative)
        stopped = _by_key(incomplete)["progressive"]
        self.assertEqual(stopped.blocker.code, "missing_information")
        self.assertIsNone(stopped.offer)

    def test_an_extra_carrier_registers_without_a_job_change(self):
        class Harbor(CarrierAdapter):
            key = "harbor"
            display_name = "Harbor"
            portal_url = "https://example.com/harbor"
            secret_names = ("HARBOR_AGENT_PORTAL_USERNAME",)

            def fixture(self, application):
                return quoted_offer(self, fixture_offer(application, prefix="HAR", premium=Decimal("10.00")))

        registry = CarrierRegistry()
        registry.register(Harbor())
        application, _invalid = parse_form(clean(TODAY))
        result = run_quote_job(
            application,
            mode="demo",
            carriers=("harbor",),
            registry=registry,
            today=TODAY,
        )
        self.assertEqual(result.results[0].carrier_key, "harbor")
        self.assertEqual(result.results[0].offer.term_premium, Decimal("10.00"))

    def test_desk_renders_the_stop_and_hides_secret_values(self):
        result = run_from_form(mvr(TODAY), mode="demo", today=TODAY)
        html = render_desk(
            form=mvr(TODAY),
            result=result,
            secrets=({"carrier_key": "progressive", "carrier_name": "Progressive", "name": "PROGRESSIVE_AGENT_PORTAL_PASSWORD", "present": False},),
            banner="demo",
            scenario="mvr",
        )
        self.assertIn("motor vehicle report for Maya Hassan", html)
        self.assertIn("What is missing", html)
        self.assertIn("PROGRESSIVE_AGENT_PORTAL_PASSWORD", html)
        self.assertNotIn(SECRET, html)
        self.assertNotIn("value=\"" + SECRET, html)

    def test_secret_status_is_boolean_only(self):
        from quoting.carriers.registry import REGISTRY

        previous = os.environ.get("PROGRESSIVE_AGENT_PORTAL_PASSWORD")
        os.environ["PROGRESSIVE_AGENT_PORTAL_PASSWORD"] = SECRET
        try:
            rows = status_for(REGISTRY.for_line("personal_auto", "NY"))
        finally:
            if previous is None:
                os.environ.pop("PROGRESSIVE_AGENT_PORTAL_PASSWORD", None)
            else:
                os.environ["PROGRESSIVE_AGENT_PORTAL_PASSWORD"] = previous
        self.assertTrue(any(row["name"] == "PROGRESSIVE_AGENT_PORTAL_PASSWORD" and row["present"] is True for row in rows))
        self.assertNotIn(SECRET, json.dumps(rows))

    def test_sample_paths_and_the_worksheet_link(self):
        self.assertEqual(check_scenarios(), 0)
        worksheet = Path(__file__).resolve().parents[1] / "templates/core/insurance_area/quote_worksheet.html"
        self.assertIn("ny-auto-quote", worksheet.read_text())
        readme = Path(__file__).resolve().parent / "README.md"
        text = readme.read_text()
        for name in SECRET_NAMES:
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
