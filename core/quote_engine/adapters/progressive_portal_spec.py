"""What the Progressive agent portal (foragentsonly.com) looks like, recorded live on Nov 25 2026 (NY, auto).

Verified live from login through the Coverages screen. Portfolio, Point of Sale and the rate page have NOT
been recorded yet, so the driver stops at Coverages until they are.
"""
STEPS = ["Named Insured", "Products", "Household Members", "Additional Details", "Coverages/Bill Plans",
         "Portfolio", "Point of Sale", "Final Sale"]

# Messages the portal shows. Used to turn a portal error into a clear message on the right lead field.
MESSAGES = {
    "required": "Required to continue",
    "date": "is not a valid date",
    "email": "not formatted correctly",
    "email2": "Not a valid email address",
    "phone": "Phone number must be 10 digits in length",
    "zip": "ZIP code must be 5 digits in length",
    "prior_term": "Prior policy term question must be answered",
    "no_additional": "Select 'No additional risks apply'",
}

# Words on a page that mean a human must step in. The driver stops and never retries these.
CHALLENGE_MARKERS = ("verify you are human", "unusual activity", "access denied", "account has been locked",
                     "temporarily locked", "too many attempts", "captcha")
OTP_MARKERS = ("one-time passcode",)

# Labels as the portal prints them (prefix match). Dependent dropdowns reset the fields after them.
NAMED_INSURED = {"first_name": "First Name:", "last_name": "Last Name:", "dob": "Date of Birth:", "gender": "Gender:",
                 "email": "Customer Email:", "phone": "Phone Type/Number: Cell or Home phone required Cell",
                 "address1": "Mailing Address Line 1:", "city": "City:", "zip": "ZIP Code:",
                 "moved": "Has the insured moved", "disclosure": "Was the above disclosure"}
VEHICLE = {"effective": "Policy Effective Date:", "vin": "VIN:", "owned_for": "How long has the customer had this vehicle",
           "use": "Primary Vehicle Use", "for_hire": "Used for Delivery", "miles": "Annual Miles"}
HOUSEHOLD = {"marital": "Marital Status", "license_type": "Driver License Type", "license_status": "Driver License Status",
             "years_licensed": "Years Licensed"}
ADDITIONAL = {"prior": "Insured/Spouse has vehicle", "term12": "Is your current policy a 12", "prior_pgr": "Is Progressive the prior",
              "prior_bi": "What were the Bodily", "prior_years": "Number of years with your most",
              "titled": "Have you included the titled", "everyone": "Have you included everyone",
              "pip_claims": "How many injury claims", "residents": "Total number of residents", "residence": "Primary Residence"}
NEXT_BUTTON = {"Named Insured": "PRODUCTS (SUBMIT", "Products": "HOUSEHOLD MEMBERS (SUBMIT",
               "Household Members": "ADDITIONAL DETAILS (SUBMIT", "Additional Details": "COVERAGES/BILL PLANS (SUBMIT"}

MILES_BANDS = [(0, "0 - 3,999"), (4000, "4,000 - 5,999"), (6000, "6,000 - 7,999"), (8000, "8,000 - 9,999"),
               (10000, "10,000 - 11,999"), (12000, "12,000 - 13,999"), (14000, "14,000 - 15,999"), (16000, "16,000 - 17,999"),
               (18000, "18,000 - 19,999"), (20000, "20,000 - 21,999"), (22000, "22,000 - 23,999"), (24000, "24,000 - 26,999"),
               (27000, "27,000 - 29,999"), (30000, "30,000 - 99,999")]


def miles_band(miles: int) -> str:
    out = MILES_BANDS[0][1]
    for lo, label in MILES_BANDS:
        if miles >= lo:
            out = label
    return out


# Coverages screen, recorded live Nov 25 2026 (existing test quote reopened; no new quote was created).
COVERAGE = {"bi_pd": "Bodily Injury & Property", "um_uim": "Uninsured & Supplementary", "pip": "Personal Injury Protection",
            "add_pip": "Additional Personal Injury", "obel": "Optional Basic Economic", "med_pay": "Medical Payment",
            "comp": "Comprehensive Deductible", "collision": "Collision Deductible", "rental": "Rental", "roadside": "Roadside",
            "snapshot": "Snapshot Enrollment"}
COVERAGE_OPTIONS = {"bi_pd": ["25/50/25"], "um_uim": {"25/50/25": "25/50 Excluding Supplementary"},
                    "med_pay": {5000: "$5,000 Per Person", 10000: "$10,000 Per Person"}, "obel": {25000: "$25,000"}}
# Rules learned: changing BI/PD clears UM/UIM (set it again after). After changes the premium shows "$ --" until
# RECALCULATE is clicked. Snapshot Enrollment is required (blank by default). A PBV modal appears on entry (close X).
COVERAGE_RULES = ["set bi_pd first, then um_uim", "click RECALCULATE after the last change", "snapshot must be chosen",
                  "close the PBV modal", "if another browser session holds the quote click RECOVER QUOTE"]


# Recovered from the Nov 24 2026 session transcripts (two real quotes). Not re-verified live.
# After Coverages: "PORTFOLIO (SUBMIT AND MOVE TO NEXT STEP)" at bottom right, then POINT OF SALE.
# Click RECALCULATE first; premium then reads "Total Auto Premium:$X".
UM_UIM_25_50_OPTIONS = ["25/50 Including Supplementary", "25/50 Excluding Supplementary"]  # both seen; pick by rule, do not assume
SNAPSHOT_DEFAULT = "Do Not Participate"
PORTFOLIO = {
    "title_pattern": "<Insured>'s Portfolio",
    "summary_columns": ["TOTAL PREMIUM", "INITIAL PAYMENT", "BILL PLAN", "POLICY TERM", "PACKAGE SAVINGS"],
    "default_bill_plan": "PAY IN FULL",  # radio id P0100Y_input; other plans list down payment + installments
    "term": "6 months",
    "premium_text": "Total Premium:",
}
POINT_OF_SALE = {
    "order_button": "ORDER POINT OF SALE",  # orders CLUE + MVR (consumer reports): MONEY/RECORD-PULL GATE, needs modal approval
    "status_labels": {"clue": "CLUE for Auto", "mvr": "MVR for Auto and/or Toys"},
    "states": ["Not Ordered", "Ordered"],
    "alerts_heading": "Point of Sale Alerts",
    "alert_examples": ["Required: Pre-binding verification may be required",
                       "Prior Damage, Theft or Title issue may impact rate for vehicle 1",
                       "Risk has no lapse in coverage."],
    "verification_table": ["VIN VERIFICATION", "VEHICLE HISTORY STATUS", "Financial Responsibility", "Proof of Residency", "Multi-Policy Verification"],
    "report_validity": "CLUE/MVR status shows 30-day window",
    "ssn_optional": True,
    "rate_after_pos": "re-read from Portfolio page ($ amounts) after ordering; Coverages page may show a different number later",
}
# Evidence that the POS rate can move a lot: quote A 6,408 -> 6,408 (unchanged); quote B 6,332 -> alert 12,022, later 10,299.
# So the engine must report the post-POS rate separately and flag any jump. Bind/Final Sale are never clicked.


UM_UIM_OPTIONS = {"25/50/25": "25/50 Excluding Supplementary", "100/300/100": "100/300"}  # 25/50 also offers "Including Supplementary"
COVERAGE_OPTIONS["obel"] = {25000: "$25,000"}
COVERAGE_OPTIONS["med_pay"] = {5000: "$5,000 Per Person", 10000: "$10,000 Per Person"}
