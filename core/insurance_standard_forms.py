"""Agency standard forms filled from the policy: certificates, applications, and loss notices.

These are the office's own forms. They carry the same facts a holder, carrier, or
underwriter expects. They are not licensed ACORD forms and do not use the ACORD name.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

FORMS = (
    ("liability_certificate", "Certificate of Liability Insurance", "The certificate a job site or landlord asks for."),
    ("property_evidence", "Evidence of Property Insurance", "Proof of dwelling or homeowner coverage for a mortgagee."),
    ("commercial_property_evidence", "Evidence of Commercial Property", "Proof of property coverage for a commercial holder."),
    ("auto_id", "Insurance Identification Card", "Agency card for each vehicle until the carrier card is uploaded."),
    ("auto_loss", "Automobile Loss Notice", "First report of an auto claim for the carrier."),
    ("property_loss", "Property Loss Notice", "First report of a property claim for the carrier."),
    ("liability_loss", "Liability Loss Notice", "First report of a liability claim for the carrier."),
    ("cancellation", "Cancellation Request", "Insured request to cancel or rewrite the policy."),
    ("personal_auto_app", "Personal Automobile Application", "Drivers, vehicles, and limits for a personal auto quote."),
    ("commercial_app", "Commercial Insurance Application", "Named insured, operations, and limits for a commercial quote."),
    ("homeowner_app", "Homeowners Application", "Dwelling, occupancy, and limits for a home quote."),
)

FORM_KEYS = {key for key, _title, _blurb in FORMS}


def form_title(key: str) -> str:
    for item_key, title, _blurb in FORMS:
        if item_key == key:
            return title
    return "Insurance form"


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


def _draw_header(c, title, policy):
    c.setFillColorRGB(0.06, 0.16, 0.32)
    c.rect(0, 742, 612, 50, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(36, 762, title[:70])
    c.setFont("Helvetica", 9)
    c.drawString(36, 748, _agency(policy)[:80])
    c.setFillColorRGB(0.1, 0.12, 0.16)
    y = 720
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
    return y - 8


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
    title = form_title(form_key)
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    y = _draw_header(c, title, policy)
    holder = (extra.get("holder_name") or "").strip()
    holder_address = (extra.get("holder_address") or "").strip()
    description = (extra.get("description") or "").strip()
    loss_date = (extra.get("loss_date") or "").strip()

    if form_key in {"liability_certificate", "property_evidence", "commercial_property_evidence"}:
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
                "This document is evidence of the coverage listed above, issued by the agency from the policy on file.",
                "It does not amend the policy. The carrier's policy controls.",
            ],
        )
    elif form_key == "auto_id":
        y = _section(c, y, "Vehicles", _vehicles(policy))
        y = _section(c, y, "Coverages", _coverages(policy))
        y = _section(
            c,
            y,
            "Notice",
            ["Temporary identification issued by the agency. Replace it with the carrier card when that card is uploaded."],
        )
    elif form_key in {"auto_loss", "property_loss", "liability_loss"}:
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
        if form_key == "auto_loss":
            y = _section(c, y, "Vehicles", _vehicles(policy))
            y = _section(c, y, "Drivers", _drivers(policy))
    elif form_key == "cancellation":
        y = _section(
            c,
            y,
            "Request",
            [
                f"Requested by: {extra.get('requested_by') or 'Insured'}",
                f"Effective: {extra.get('effective_date') or '—'}",
                description or "Cancel the policy at the insured's request.",
            ],
        )
    else:
        y = _section(c, y, "Drivers", _drivers(policy))
        y = _section(c, y, "Vehicles", _vehicles(policy))
        y = _section(c, y, "Coverages requested or on file", _coverages(policy))
        if description:
            y = _section(c, y, "Remarks", [description])
        y = _section(
            c,
            y,
            "Applicant statement",
            ["The facts above were taken from the quote or policy in the agency file. The applicant should review them before signing."],
        )
    c.setFont("Helvetica", 8)
    c.drawString(36, 36, f"{_agency(policy)}  ·  {title}  ·  Policy {policy.policy_number}")
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
