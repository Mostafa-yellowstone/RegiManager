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


class WiringTests(SimpleTestCase):
    def test_not_enabled_without_env(self):
        import os
        from core.quote_engine.adapters import progressive_wiring as w
        for k in ("PROGRESSIVE_AUTOMATION", "PROGRESSIVE_USER", "PROGRESSIVE_PASSWORD"):
            os.environ.pop(k, None)
        self.assertFalse(w.enabled())
        self.assertFalse(w.install())

    def test_needs_otp_provider(self):
        from core.quote_engine.adapters import progressive_wiring as w
        r = w.make_quote_fn(page_factory=lambda: FakePage(), env={"PROGRESSIVE_USER": "u", "PROGRESSIVE_PASSWORD": "p"})({})
        self.assertEqual(r.status, "needs_input")

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
