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
