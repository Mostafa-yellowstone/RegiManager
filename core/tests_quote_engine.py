import copy
import time
from datetime import date

from django.test import SimpleTestCase

from .quote_engine.carriers import CarrierAdapter, QuoteResult, get_carriers
from .quote_engine.runner import run_quotes
from .quote_engine.validators import (
    has_errors, parse_date, validate_quote_request, validate_vin, vin_check_digit,
)

TODAY = date(2026, 11, 25)
GOOD_VIN = "1HGCM82633A004352"  # standard published sample VIN, valid check digit


def base_auto():
    return {
        "line_of_business": "auto",
        "effective_date": "2026-12-01",
        "contact": {"email": "a@b.com", "phone": "(718) 623-0134"},
        "garaging_address": {"street": "12 Main St", "city": "Brooklyn", "state": "NY", "zip": "11201"},
        "drivers": [{"first_name": "Ann", "last_name": "Lee", "date_of_birth": "1985-04-02",
                     "license_number": "123456789", "license_state": "NY", "relationship": "self"}],
        "vehicles": [{"vin": GOOD_VIN, "year": 2003, "make": "Honda", "model": "Accord", "ownership": "owned"}],
        "prior_insurance": {"has_prior": True, "carrier": "GEICO", "expiration_date": "2026-12-01", "months_with_carrier": 24},
        "bodily_injury_limit": "25/50",
    }


def base_commercial():
    d = base_auto()
    d.update({
        "line_of_business": "commercial_auto",
        "business": {"legal_name": "Lee Hauling LLC", "entity_type": "llc", "fein": "12-3456789",
                     "usdot": "1234567", "years_in_business": 3, "operation_type": "local delivery"},
        "csl_limit": 1000000,
    })
    d.pop("bodily_injury_limit")
    d["vehicles"] = [{"vin": GOOD_VIN, "year": 2003, "make": "Ford", "model": "E350", "ownership": "owned",
                      "vehicle_class": "van", "gvw": 9500, "radius_miles": 50}]
    return d


def codes(issues, sev=None):
    return {i.code for i in issues if sev is None or i.severity == sev}


class VinTests(SimpleTestCase):
    def test_good_vin(self):
        self.assertEqual(vin_check_digit(GOOD_VIN), GOOD_VIN[8])
        self.assertEqual(validate_vin(GOOD_VIN, 2003), [])

    def test_bad_vins(self):
        self.assertIn("vin_length", codes(validate_vin("123")))
        self.assertIn("vin_chars", codes(validate_vin("1HGCM82633A00435O")))
        self.assertIn("vin_check_digit", codes(validate_vin("1HGCM82643A004352")))
        self.assertIn("vin_missing", codes(validate_vin("")))
        self.assertIn("vin_repeated", codes(validate_vin("11111111111111111")))

    def test_year_mismatch_is_warning(self):
        i = validate_vin(GOOD_VIN, 2015)
        self.assertEqual(codes(i, "warning"), {"vin_year_mismatch"})

    def test_spaces_and_lowercase(self):
        self.assertEqual(validate_vin(" 1hgcm82633a004352 ", 2003), [])


class RequestTests(SimpleTestCase):
    def v(self, d):
        return validate_quote_request(d, TODAY)

    def test_valid_auto_has_no_errors(self):
        self.assertFalse(has_errors(self.v(base_auto())), self.v(base_auto()))

    def test_valid_commercial_has_no_errors(self):
        self.assertFalse(has_errors(self.v(base_commercial())), self.v(base_commercial()))

    def test_unknown_line_rejected(self):
        d = base_auto(); d["line_of_business"] = "homeowners"
        self.assertEqual(codes(self.v(d)), {"lob_invalid"})

    def test_driver_rules(self):
        d = base_auto()
        d["drivers"][0]["date_of_birth"] = "2030-01-01"
        self.assertIn("dob_future", codes(self.v(d)))
        d["drivers"][0]["date_of_birth"] = "2015-01-01"
        self.assertIn("age_too_young", codes(self.v(d)))
        d["drivers"][0]["date_of_birth"] = "2009-01-01"
        self.assertIn("age_permit", codes(self.v(d), "warning"))
        d["drivers"][0]["date_of_birth"] = "13/45/1990"
        self.assertIn("dob_invalid", codes(self.v(d)))

    def test_license_format_and_expiry(self):
        d = base_auto()
        d["drivers"][0]["license_number"] = "12"
        self.assertIn("dl_format", codes(self.v(d)))
        d = base_auto(); d["drivers"][0]["license_expiration"] = "2026-01-01"
        self.assertIn("dl_expired", codes(self.v(d), "warning"))
        d["drivers"][0]["license_expiration"] = "2020-01-01"
        self.assertIn("dl_expired", codes(self.v(d), "error"))

    def test_excluded_driver_skips_license(self):
        d = base_auto(); d["drivers"][0]["license_number"] = ""; d["drivers"][0]["excluded"] = True
        self.assertNotIn("required", {i.code for i in self.v(d) if i.field.endswith("license_number")})

    def test_duplicates(self):
        d = base_auto(); d["drivers"].append(copy.deepcopy(d["drivers"][0]))
        c = codes(self.v(d))
        self.assertTrue({"duplicate_driver", "duplicate_license"} <= c)
        d = base_auto(); d["vehicles"].append(copy.deepcopy(d["vehicles"][0]))
        self.assertIn("duplicate_vin", codes(self.v(d)))

    def test_incident_dates(self):
        d = base_auto(); d["drivers"][0]["accidents"] = [{"date": "2027-01-01"}, {"date": "1980-01-01"}, {}]
        c = codes(self.v(d))
        self.assertTrue({"date_future", "date_before_birth", "date_invalid"} <= c)

    def test_address_and_contact(self):
        d = base_auto()
        d["garaging_address"].update(zip="1120", state="ZZ")
        d["contact"] = {"email": "bad", "phone": "123"}
        c = codes(self.v(d))
        self.assertTrue({"zip_invalid", "state_invalid", "email_invalid", "phone_invalid"} <= c)
        d = base_auto(); d["garaging_address"]["street"] = "PO Box 12"
        self.assertIn("po_box", codes(self.v(d), "error"))

    def test_vehicle_rules(self):
        d = base_auto(); v = d["vehicles"][0]
        v.update(year=2040, ownership="financed")
        c = codes(self.v(d))
        self.assertTrue({"year_range", "lienholder_required"} <= c)
        v.update(year="x"); self.assertIn("year_invalid", codes(self.v(d)))
        d = base_auto(); d["vehicles"][0]["deductible_collision"] = 123
        self.assertIn("deductible_invalid", codes(self.v(d)))

    def test_policy_rules(self):
        d = base_auto(); d["effective_date"] = "2026-01-01"
        self.assertIn("date_past", codes(self.v(d)))
        d = base_auto(); d["effective_date"] = "2027-06-01"
        self.assertIn("date_far", codes(self.v(d), "warning"))
        d = base_auto(); d["prior_insurance"] = {"has_prior": False}
        self.assertIn("no_prior", codes(self.v(d), "warning"))
        d = base_auto(); d["prior_insurance"]["expiration_date"] = "2026-06-01"
        self.assertIn("lapse", codes(self.v(d), "warning"))
        d = base_auto(); d["bodily_injury_limit"] = "1/2"
        self.assertIn("limit_invalid", codes(self.v(d)))

    def test_commercial_rules(self):
        d = base_commercial()
        d["business"].update(fein="00-1234567", usdot="12", entity_type="club", years_in_business=0)
        d["vehicles"][0].update(gvw=999999, radius_miles=500, vehicle_class="rocket")
        d["csl_limit"] = 42
        c = codes(self.v(d))
        self.assertTrue({"fein_invalid", "usdot_invalid", "entity_invalid", "gvw_range", "class_invalid", "csl_invalid"} <= c)
        self.assertIn("long_haul", codes(self.v(d), "warning"))
        d = base_commercial(); del d["vehicles"][0]["gvw"]
        self.assertIn("gvw_required", codes(self.v(d)))
        d = base_commercial(); d["business"] = {}
        self.assertIn("required", codes(self.v(d)))

    def test_personal_with_business_use_warns(self):
        d = base_auto(); d["vehicles"][0]["use"] = "delivery"
        self.assertIn("use_mismatch", codes(self.v(d), "warning"))

    def test_empty_request(self):
        d = {"line_of_business": "auto"}
        c = codes(self.v(d))
        self.assertTrue({"required"} <= c)

    def test_parse_date_formats(self):
        for s in ("2026-01-05", "01/05/2026", "01-05-2026"):
            self.assertEqual(parse_date(s), date(2026, 1, 5))
        self.assertIsNone(parse_date("nope"))


class RunnerTests(SimpleTestCase):
    def test_blocked_on_errors(self):
        d = base_auto(); d["vehicles"][0]["vin"] = "BAD"
        r = run_quotes(d, today=TODAY)
        self.assertTrue(r.blocked)
        self.assertEqual(r.results, [])

    def test_parallel_failure_isolation_and_ranking(self):
        def slow(price):
            def f(req):
                time.sleep(0.3)
                return QuoteResult("x", "quoted", premium_term=price)
            return f

        def boom(req):
            raise RuntimeError("portal down")

        cs = [CarrierAdapter("a", "A", ("auto",), quote_fn=slow(900)),
              CarrierAdapter("b", "B", ("auto",), quote_fn=slow(700)),
              CarrierAdapter("c", "C", ("auto",), quote_fn=boom),
              CarrierAdapter("d", "D", ("commercial_auto",), quote_fn=slow(1)),
              CarrierAdapter("e", "E", ("auto",), states=frozenset({"FL"}), quote_fn=slow(1))]
        t = time.monotonic()
        r = run_quotes(base_auto(), carriers=cs, today=TODAY)
        elapsed = time.monotonic() - t
        self.assertLess(elapsed, 0.8)  # ran in parallel
        st = {x.carrier: x.status for x in r.results}
        self.assertEqual(st["C"], "error")
        self.assertEqual(st["D"], "skipped")
        self.assertEqual(st["E"], "skipped")
        self.assertEqual(r.results[0].premium_term, 700)
        self.assertEqual(r.best().premium_term, 700)

    def test_unbuilt_carrier_never_fakes_a_price(self):
        r = run_quotes(base_auto(), today=TODAY)
        self.assertFalse(r.blocked)
        self.assertTrue(all(x.status in ("not_implemented", "skipped") for x in r.results))
        self.assertIsNone(r.best())

    def test_registry_lines(self):
        auto = get_carriers("auto")
        commercial = get_carriers("commercial_auto")
        self.assertEqual([c.key for c in auto], ["progressive"])
        self.assertEqual([c.key for c in commercial], ["progressive"])
