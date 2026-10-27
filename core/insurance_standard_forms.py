"""Agency forms filled from the policy, numbered the way the industry files them.

The number and name identify the form (125, then Commercial Insurance Application).
The page itself is the agency's layout, filled from the policy on file.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# (key, number shown first, name). Order inside a group is the order in the picker.
_CATALOG = (
    ("Loss notices", (
        ("1", "1", "Property Loss Notice"),
        ("2", "2", "Automobile Loss Notice"),
        ("3", "3", "Liability Notice of Occurrence / Claim"),
        ("4", "4", "Workers Compensation First Report of Injury or Illness"),
        ("5", "5", "Aircraft Loss Notice"),
        ("11", "11", "Auto Accident Information Form"),
        ("12", "12", "Exchange of Information Form"),
    )),
    ("Certificates", (
        ("20", "20", "Certificate of Aviation Liability Insurance"),
        ("21", "21", "Certificate of Aircraft Insurance"),
        ("22", "22", "Intermodal Interchange Certificate of Insurance"),
        ("23", "23", "Vehicle or Equipment Certificate of Insurance"),
        ("24", "24", "Certificate of Property Insurance"),
        ("25", "25", "Certificate of Liability Insurance"),
        ("30", "30", "Certificate of Garage Insurance"),
        ("31", "31", "Certificate of Marine / Energy Insurance"),
    )),
    ("Evidence", (
        ("27", "27", "Evidence of Property Insurance"),
        ("28", "28", "Evidence of Commercial Property Insurance"),
        ("29", "29", "Evidence of Flood Insurance"),
    )),
    ("Policy service", (
        ("35", "35", "Cancellation Request / Policy Release"),
        ("36", "36", "Agent/Broker of Record Change"),
        ("37", "37", "Statement of No Loss"),
        ("45", "45", "Additional Interest Schedule"),
        ("50", "50", "Automobile Insurance ID Card"),
        ("58", "58", "Notice of Cancellation or Termination of Policy"),
        ("75", "75", "Insurance Binder"),
        ("101", "101", "Additional Remarks Schedule"),
    )),
    ("Personal lines", (
        ("70", "70", "Personal Policy Change Request"),
        ("71", "71", "Personal Auto Policy Change Request"),
        ("80", "80", "Homeowner Application"),
        ("81", "81", "Personal Inland Marine Application"),
        ("82", "82", "Watercraft Application"),
        ("83", "83", "Personal Umbrella Application"),
        ("84", "84", "Dwelling Fire Application"),
        ("85", "85", "Mobile Home Application"),
        ("88", "88", "Personal Insurance Application"),
        ("89", "89", "Residential Section"),
        ("90ny", "90 NY", "New York Personal Auto Application"),
        ("99", "99", "Accidents / Convictions Schedule"),
        ("103", "103", "Personal Auto Additional Driver Information"),
        ("290ny", "290 NY", "New York Personal Auto Application Section"),
    )),
    ("Commercial lines", (
        ("125", "125", "Commercial Insurance Application"),
        ("126", "126", "Commercial General Liability Section"),
        ("127", "127", "Business Auto Section"),
        ("128", "128", "Garage and Dealers Section"),
        ("129", "129", "Vehicle Schedule"),
        ("130", "130", "Workers Compensation Application"),
        ("131", "131", "Umbrella Section"),
        ("132", "132", "Truckers / Motor Carriers Section"),
        ("133", "133", "Workers Compensation Assigned Risk Section"),
        ("137ny", "137 NY", "New York Commercial Auto"),
        ("139", "139", "Statement / Schedule of Values"),
        ("140", "140", "Property Section"),
        ("141", "141", "Crime Section"),
        ("143", "143", "Transportation Section"),
        ("144", "144", "Glass and Sign Section"),
        ("145", "145", "Accounts Receivable / Valuable Papers"),
        ("147", "147", "Installation / Builders Risk Section"),
        ("148", "148", "Electronic Data Processing Section"),
        ("152", "152", "Commercial Inland Marine Section"),
        ("155", "155", "Equipment Breakdown Section"),
        ("160", "160", "Business Owners Section"),
        ("163", "163", "Commercial Auto Driver Information"),
        ("175", "175", "Commercial Policy Change Request"),
        ("186", "186", "Contractors Supplement"),
        ("187", "187", "Professional Liability Supplement"),
    )),
)

_ALIASES = {
    "liability_certificate": "25",
    "property_evidence": "27",
    "commercial_property_evidence": "28",
    "auto_id": "50",
    "auto_loss": "2",
    "property_loss": "1",
    "liability_loss": "3",
    "cancellation": "35",
    "personal_auto_app": "90ny",
    "commercial_app": "125",
    "homeowner_app": "80",
}


def _entry(key: str):
    resolved = _ALIASES.get(key, key)
    for _group, items in _CATALOG:
        for item_key, number, name in items:
            if item_key == resolved:
                return item_key, number, name
    return None


FORM_GROUPS = [
    {
        "name": group,
        "forms": [
            {"key": key, "number": number, "name": name, "title": f"{number} {name}"}
            for key, number, name in items
        ],
    }
    for group, items in _CATALOG
]

FORMS = tuple(
    (form["key"], form["title"], "")
    for group in FORM_GROUPS
    for form in group["forms"]
)

FORM_KEYS = {key for key, _title, _blurb in FORMS} | set(_ALIASES)


def form_title(key: str) -> str:
    found = _entry(key)
    if not found:
        return "Insurance form"
    _key, number, name = found
    return f"{number} {name}"


def _agency(policy) -> str:
    org = policy.organization
    return (getattr(org, "insurance_intake_display_name", "") or org.name or "Agency").strip()


def _insured(policy) -> str:
    return policy.named_insured or (policy.client.name if policy.client_id else "")


def _carrier(policy) -> str:
    if not policy.insurance_company_id:
        return ""
    company = policy.insurance_company
    naic = f"  NAIC {company.naic}" if getattr(company, "naic", "") else ""
    return f"{company.name}{naic}"


def _coverages(policy) -> list[str]:
    lines = []
    for row in policy.coverages.all():
        extra = f" deductible ${row.deductible}" if row.deductible is not None else ""
        vehicle = f" (auto {row.vehicle.auto_number})" if row.vehicle_id else ""
        lines.append(f"{row.get_code_display()}{vehicle}: {row.limit_text or '—'}{extra}")
    return lines or ["Limits have not been entered on this policy."]


def _vehicles(policy) -> list[str]:
    rows = []
    for vehicle in policy.policy_vehicles.all():
        bits = " ".join(str(part) for part in (vehicle.year or "", vehicle.make or "") if part).strip()
        lien = f"  Lienholder {vehicle.lienholder_name}" if vehicle.lienholder_name else ""
        rows.append(f"{bits or 'Vehicle'}  VIN {vehicle.vin or '—'}  Plate {vehicle.plate_number or '—'}{lien}")
    if not rows and (policy.vin or policy.plate_number):
        rows.append(f"VIN {policy.vin or '—'}  Plate {policy.plate_number or '—'}")
    return rows or ["No vehicle on the policy."]


def _drivers(policy) -> list[str]:
    rows = []
    for driver in policy.policy_drivers.all():
        excluded = "  EXCLUDED" if driver.is_excluded else ""
        sr22 = "  SR-22" if driver.sr22_required else ""
        rows.append(
            f"{driver.name}  {driver.license_state} {driver.license_number}{excluded}{sr22}".strip()
        )
    return rows or ["No driver schedule on the policy."]


def _family(key: str) -> str:
    found = _entry(key)
    number = found[1] if found else ""
    digits = "".join(ch for ch in number if ch.isdigit())
    n = int(digits) if digits else 0
    if n in {20, 21, 22, 23, 24, 25, 30, 31}:
        return "certificate"
    if n in {27, 28, 29}:
        return "evidence"
    if n in {1, 2, 3, 4, 5, 11, 12}:
        return "loss"
    if n in {35, 36, 37, 58}:
        return "change"
    if n == 50:
        return "id"
    if n in {75, 101}:
        return "binder"
    if n in {90, 127, 129, 132, 137, 163, 290, 71, 99, 103}:
        return "auto"
    if n in {80, 84, 85, 89, 140, 139, 160, 70, 42}:
        return "property"
    if n in {4, 130, 133}:
        return "workers"
    return "application"


def _draw_header(c, number, name, policy):
    c.setFillColorRGB(0.04, 0.14, 0.28)
    c.rect(0, 736, 612, 56, fill=1, stroke=0)
    c.setFillColorRGB(0.98, 0.85, 0.35)
    c.roundRect(28, 746, 78, 32, 6, fill=1, stroke=0)
    c.setFillColorRGB(0.04, 0.14, 0.28)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(67, 757, number[:10])
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(118, 764, name[:62])
    c.setFont("Helvetica", 9)
    c.drawString(118, 750, _agency(policy)[:78])
    c.setFillColorRGB(0.1, 0.12, 0.16)
    y = 714
    period = ""
    if policy.start_date and policy.end_date:
        period = f"{policy.start_date.isoformat()} to {policy.end_date.isoformat()}"
    facts = [
        f"Named insured: {_insured(policy)}",
        f"Address: {policy.insured_address or (policy.client.full_address if policy.client_id else '')}",
        f"Carrier: {_carrier(policy) or '—'}",
        f"Policy number: {policy.policy_number}    Period: {period or '—'}",
    ]
    for line in facts:
        c.setFont("Helvetica", 10)
        c.drawString(36, y, (line or "")[:110])
        y -= 14
    c.setStrokeColorRGB(0.82, 0.86, 0.9)
    c.line(36, y + 4, 576, y + 4)
    return y - 10


def _section(c, y, heading, lines):
    if y < 90:
        c.showPage()
        y = 740
    c.setFont("Helvetica-Bold", 11)
    c.drawString(36, y, heading)
    y -= 14
    c.setFont("Helvetica", 10)
    for line in lines:
        if y < 54:
            c.showPage()
            y = 740
            c.setFont("Helvetica", 10)
        c.drawString(44, y, (line or "")[:105])
        y -= 13
    return y - 8


def standard_form_pdf(policy, form_key: str, extra: dict | None = None) -> bytes:
    extra = extra or {}
    found = _entry(form_key)
    number, name = (found[1], found[2]) if found else ("", form_title(form_key))
    title = f"{number} {name}".strip()
    family = _family(form_key)
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    y = _draw_header(c, number or "Form", name, policy)
    holder = (extra.get("holder_name") or "").strip()
    holder_address = (extra.get("holder_address") or "").strip()
    description = (extra.get("description") or "").strip()
    loss_date = (extra.get("loss_date") or "").strip()

    if family in {"certificate", "evidence"}:
        y = _section(
            c,
            y,
            "Certificate holder",
            [holder or "Holder not named", holder_address, description or "Description of operations not entered."],
        )
        flags = []
        if extra.get("additional_insured"):
            flags.append("Additional insured is requested for the holder.")
        if extra.get("waiver"):
            flags.append("Waiver of subrogation is requested for the holder.")
        if flags:
            y = _section(c, y, "Special wording", flags)
        y = _section(c, y, "Coverages and limits on file", _coverages(policy))
        y = _section(
            c,
            y,
            "Notice",
            [
                "This page is filled from the policy on file at the agency.",
                "It does not amend the policy. The carrier's policy controls.",
            ],
        )
    elif family == "id":
        y = _section(c, y, "Vehicles", _vehicles(policy))
        y = _section(c, y, "Coverages", _coverages(policy))
        y = _section(
            c,
            y,
            "Notice",
            ["Identification issued by the agency from the policy on file. Replace it with the carrier card when that card is uploaded."],
        )
    elif family == "loss":
        y = _section(
            c,
            y,
            "Loss",
            [
                f"Date of loss: {loss_date or '—'}",
                description or "Description not entered.",
                f"Other party: {extra.get('other_party') or '—'}",
                f"Police report: {extra.get('police_report') or '—'}",
            ],
        )
        if number.startswith("2") or number == "11":
            y = _section(c, y, "Vehicles", _vehicles(policy))
            y = _section(c, y, "Drivers", _drivers(policy))
    elif family == "change":
        y = _section(
            c,
            y,
            "Request",
            [
                f"Requested by: {extra.get('requested_by') or 'Insured'}",
                f"Effective: {extra.get('effective_date') or '—'}",
                description or "See the policy file for the change requested.",
            ],
        )
    elif family == "auto":
        y = _section(c, y, "Drivers", _drivers(policy))
        y = _section(c, y, "Vehicles", _vehicles(policy))
        y = _section(c, y, "Coverages on file", _coverages(policy))
    elif family == "property":
        y = _section(c, y, "Location", [policy.insured_address or "Address not on the policy."])
        y = _section(c, y, "Coverages on file", _coverages(policy))
    elif family == "workers":
        y = _section(c, y, "Named insured", [_insured(policy), policy.insured_address or ""])
        y = _section(c, y, "Coverages on file", _coverages(policy))
    else:
        y = _section(c, y, "Applicant", [_insured(policy)])
        y = _section(c, y, "Coverages on file", _coverages(policy))
        y = _section(c, y, "Vehicles", _vehicles(policy))
    if description and family not in {"certificate", "evidence", "loss", "change"}:
        y = _section(c, y, "Remarks", [description])
    y = _section(
        c,
        y,
        "Prepared from the policy file",
        ["Review the facts above before this page is sent to a holder, carrier, or underwriter."],
    )
    c.setFillColorRGB(0.35, 0.4, 0.48)
    c.setFont("Helvetica", 8)
    c.drawString(36, 36, f"{number}  {name}   ·   {_agency(policy)}   ·   Policy {policy.policy_number}"[:120])
    c.showPage()
    c.save()
    return buffer.getvalue()


def rating_packet_pdf(lead) -> bytes:
    """One page the agent keeps open while quoting on a carrier site."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    org = lead.organization
    agency = (getattr(org, "insurance_intake_display_name", "") or org.name or "Agency").strip()
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, 750, "Rating packet")
    c.setFont("Helvetica", 10)
    y = 728
    lines = [
        agency,
        f"Applicant: {lead.client_name}",
        f"Phone: {lead.phone}    Email: {lead.email or '—'}",
        f"Address: {lead.street_address} {lead.apartment} {lead.city} {lead.state} {lead.zip_code}".strip(),
        f"DOB: {lead.date_of_birth or '—'}    License: {lead.dl_number or '—'}",
        f"Line: {lead.insurance_type or '—'}    Coverage: {lead.coverage_type or '—'}",
        f"Prior insurance: {'yes' if lead.has_prior else 'no'}    Accident or violation: {'yes' if lead.has_accident else 'no'}",
        f"Vehicle: {lead.vehicle_year} {lead.vehicle_make} {lead.vehicle_model}  VIN {lead.vin or '—'}",
        f"Notes: {lead.notes or '—'}",
    ]
    for line in lines:
        c.drawString(36, y, (line or "")[:110])
        y -= 16
    y -= 6
    c.setFont("Helvetica-Bold", 11)
    c.drawString(36, y, "Other drivers")
    y -= 16
    c.setFont("Helvetica", 10)
    extras = list(lead.additional_drivers.all())
    if not extras:
        c.drawString(44, y, "None")
        y -= 14
    for driver in extras:
        c.drawString(44, y, f"{driver.full_name}  {driver.dl_number}  {driver.date_of_birth or ''}"[:110])
        y -= 14
    y -= 8
    c.setFont("Helvetica-Bold", 11)
    c.drawString(36, y, "Other vehicles")
    y -= 16
    c.setFont("Helvetica", 10)
    cars = list(lead.additional_vehicles.all())
    if not cars:
        c.drawString(44, y, "None")
        y -= 14
    for vehicle in cars:
        c.drawString(44, y, f"{vehicle.year} {vehicle.make} {vehicle.model}  {vehicle.vin}"[:110])
        y -= 14
    c.setFont("Helvetica", 8)
    c.drawString(36, 36, "Enter the carrier's premium on Compare carriers. This packet is the applicant, not a carrier rate.")
    c.showPage()
    c.save()
    return buffer.getvalue()
