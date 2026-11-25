from django.test import SimpleTestCase

from core.quote_engine.adapters import progressive_portal_spec as spec
from core.quote_engine.adapters.progressive import PortalQuestion
from core.quote_engine.adapters.progressive_driver import PortalBlocked, PortalValidation, ProgressiveBrowserDriver


class FakePage:
    def __init__(self, text="", reset_once=None, errors_on=None, vin_verified=True):
        self.vals, self.clicks, self._text = {}, [], text
        self.reset_once, self.errors_on, self.vin_verified = set(reset_once or []), errors_on, vin_verified
        self.suggestions = []

    def text(self):
        t = self._text
        if self.vin_verified and "VIN:" in self.vals:
            t += "\nVERIFIED"
        if self.errors_on and self.clicks and self.clicks[-1].startswith(self.errors_on):
            t += "\nError: \nFirst Name: Required to continue"
        return t

    def fill(self, label, value): self.vals[label] = value
    def read(self, label): return self.vals.get(label, "")

    def select(self, label, option):
        if label in self.reset_once:  # portal reset the field after a dependent change: first try is lost
            self.reset_once.discard(label)
            self.vals[label] = ""
        else:
            self.vals[label] = option

    def click(self, label): self.clicks.append(label)
    def pick_suggestion(self, text): self.suggestions.append(text)
    def screenshot(self): return "/tmp/x.png"
    def close(self): self.closed = True


def drv(page):
    return ProgressiveBrowserDriver(page, "u", "p", sleep=lambda s: None)


DRIVER = {"first_name": "Test", "last_name": "Quoteqa", "dob": "01/15/1985", "gender": "M", "phone": "(718) 555-0142",
          "address": {"line1": "1 Centre Street", "city": "New York", "zip": "10007"}}
VEH = {"vin": "1HGCM82633A004352", "effective_date": "11/26/2026"}


class DriverTests(SimpleTestCase):
    def test_miles_band(self):
        self.assertEqual(spec.miles_band(10000), "10,000 - 11,999")
        self.assertEqual(spec.miles_band(500), "0 - 3,999")
        self.assertEqual(spec.miles_band(99999), "30,000 - 99,999")

    def test_named_insured_and_vehicle_flow(self):
        p = FakePage()
        d = drv(p)
        d.enter_drivers([DRIVER], {})
        self.assertEqual(p.vals[spec.NAMED_INSURED["phone"]], "7185550142")
        self.assertEqual(p.vals[spec.NAMED_INSURED["dob"]], "01151985")
        self.assertEqual(p.suggestions, ["1 Centre Street"])
        d.enter_vehicles([VEH], {"vehicle_use": "personal", "annual_miles": 10000, "marital_status": "single", "residence": "other"})
        self.assertIn("No additional risks apply", p.clicks)
        self.assertEqual(p.vals[spec.VEHICLE["miles"]], "10,000 - 11,999")

    def test_dependent_reset_is_retried_once(self):
        p = FakePage(reset_once=[spec.ADDITIONAL["prior_pgr"]])
        drv(p).enter_drivers([DRIVER], {})
        drv(p).enter_vehicles([VEH], {})
        self.assertEqual(p.vals[spec.ADDITIONAL["prior_pgr"]], "No")

    def test_portal_errors_are_raised(self):
        p = FakePage(errors_on="PRODUCTS")
        with self.assertRaises(PortalValidation) as cm:
            drv(p).enter_drivers([DRIVER], {})
        self.assertIn("Required to continue", cm.exception.errors[0])

    def test_challenge_stops_run(self):
        with self.assertRaises(PortalBlocked):
            drv(FakePage(text="Please verify you are human")).new_auto_quote("New York")

    def test_unverified_vin_asks(self):
        p = FakePage(vin_verified=False)
        with self.assertRaises(PortalQuestion):
            drv(p).enter_vehicles([VEH], {})

    def test_rejected_otp_stops(self):
        p = FakePage(text="Your login needs to be reauthenticated. One-time passcode")
        with self.assertRaises(PortalQuestion):
            drv(p).login(lambda: "000000")

    def test_stops_at_coverages(self):
        with self.assertRaises(PortalQuestion):
            drv(FakePage()).go_to_point_of_sale()


class FakeCred:
    class Status:
        LOCKED = "locked"
    enabled = True
    username = "u"
    portal_url = ""
    def __init__(self): self.results = []
    def has_password(self): return True
    def get_password(self, actor="", purpose=""): return "p"
    def record_result(self, ok, status=None, error=""): self.results.append((ok, status))


REQ = {"line_of_business": "auto", "contact": {"phone": "7185550142"}, "effective_date": "2099-01-01",
       "garaging_address": {"street": "1 Centre Street", "city": "New York", "state": "NY", "zip": "10007"},
       "drivers": [{"first_name": "A", "last_name": "B", "date_of_birth": "1985-01-15", "gender": "male"}],
       "vehicles": [{"vin": "1HGCM82633A004352"}]}


class WiringTests(SimpleTestCase):
    def test_converts_request_for_driver(self):
        from core.quote_engine.adapters import progressive_wiring as w
        d, v, why = w.to_driver_input(REQ)
        self.assertIsNone(why)
        self.assertEqual(d[0]["dob"], "01/15/1985")
        self.assertEqual(d[0]["address"]["line1"], "1 Centre Street")
        self.assertEqual(v[0]["effective_date"], "01/01/2099")

    def test_missing_gender_is_asked_not_guessed(self):
        from core.quote_engine.adapters import progressive_wiring as w
        req = {**REQ, "drivers": [{**REQ["drivers"][0], "gender": ""}]}
        r = w.make_quote_fn(page_factory=lambda: FakePage())({**req, "_credential": FakeCred(), "otp_provider": lambda: "1"})
        self.assertEqual(r.status, "needs_input")
        self.assertIn("gender", r.detail)

    def test_needs_credential_and_otp_provider(self):
        from core.quote_engine.adapters import progressive_wiring as w
        fn = w.make_quote_fn(page_factory=lambda: FakePage())
        self.assertEqual(fn(dict(REQ)).status, "needs_input")
        self.assertEqual(fn({**REQ, "_credential": FakeCred()}).status, "needs_input")

    def test_challenge_locks_the_login(self):
        from core.quote_engine.adapters import progressive_wiring as w
        cred = FakeCred()
        r = w.make_quote_fn(page_factory=lambda: FakePage(text="Access Denied unusual activity"))({**REQ, "_credential": cred, "otp_provider": lambda: "1"})
        self.assertEqual(r.status, "error")
        self.assertEqual(cred.results[-1], (False, "locked"))

    def test_set_coverage_order_and_values(self):
        p = FakePage(text="Total Auto Premium: $6,332.00")
        d = drv(p)
        d.set_coverage({"bi_pd": "25/50/25", "med_pay": 5000, "obel": 25000})
        self.assertEqual(p.vals[spec.COVERAGE["um_uim"]], "25/50 Excluding Supplementary")
        self.assertEqual(p.vals[spec.COVERAGE["med_pay"]], "$5,000 Per Person")
        self.assertEqual(p.clicks[-1], "RECALCULATE")

    def test_set_coverage_stops_when_no_premium(self):
        with self.assertRaises(PortalQuestion):
            drv(FakePage(text="$ --.--")).set_coverage({})

    def test_pos_requires_ordered_state(self):
        p = FakePage(text="TOTAL PREMIUM $6,408.00 ORDER POINT OF SALE Not Ordered Not Ordered")
        with self.assertRaises(PortalQuestion):
            drv(p).go_to_point_of_sale()
        self.assertNotIn("BIND", " ".join(p.clicks).upper())


class GenderTests(SimpleTestCase):
    def test_gender_from_details_form_reaches_driver_input(self):
        from core.quote_engine.lead_bridge import flat_to_extra, FLAT_FIELDS
        from core.quote_engine.adapters import progressive_wiring as w
        self.assertIn("gender", FLAT_FIELDS)
        self.assertEqual(flat_to_extra({"gender": "female"})["_gender"], "F")
        self.assertNotIn("_gender", flat_to_extra({"gender": "other"}))
        req = {**REQ, "drivers": [{**REQ["drivers"][0], "gender": flat_to_extra({"gender": "female"})["_gender"]}]}
        self.assertEqual(w.to_driver_input(req)[0][0]["gender"], "F")
