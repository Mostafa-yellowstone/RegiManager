"""Temporary ID card, compensation disclosure, and certificate PDFs."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .models import InsurancePolicy


def _line(c, text, y, *, size=11, font="Helvetica"):
    c.setFont(font, size)
    c.drawString(54, y, (text or "")[:110])
    return y - (size + 8)


def temporary_id_card_pdf(policy: InsurancePolicy) -> bytes:
    """Two agency identification cards on a letter page, one per vehicle."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    org = policy.organization
    agency = (getattr(org, "insurance_intake_display_name", "") or org.name or "Insurance agency").strip()
    phone = (getattr(org, "phone_number", "") or "").strip()
    carrier = policy.insurance_company
    carrier_name = carrier.name if carrier else "Carrier"
    naic = getattr(carrier, "naic", "") if carrier else ""
    insured = policy.named_insured or (policy.client.name if policy.client_id else "")
    start = policy.start_date.strftime("%m/%d/%Y") if policy.start_date else ""
    end = policy.end_date.strftime("%m/%d/%Y") if policy.end_date else ""
    vehicles = list(policy.policy_vehicles.all())
    if not vehicles:
        vehicles = [None]
    width, height = 324, 198
    for index, vehicle in enumerate(vehicles):
        if index and index % 2 == 0:
            c.showPage()
        left = 54
        bottom = 520 if index % 2 == 0 else 280
        c.setStrokeColorRGB(0.06, 0.16, 0.32)
        c.setLineWidth(1.5)
        c.roundRect(left, bottom, width, height, 8, fill=0, stroke=1)
        c.setFillColorRGB(0.06, 0.16, 0.32)
        c.rect(left, bottom + height - 28, width, 28, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(left + 10, bottom + height - 18, "INSURANCE IDENTIFICATION CARD")
        c.setFillColorRGB(0.1, 0.12, 0.16)
        y = bottom + height - 44
        c.setFont("Helvetica", 8)
        rows = [
            f"Insurer: {carrier_name}" + (f"   NAIC {naic}" if naic else ""),
            f"Policy: {policy.policy_number}",
            f"Effective: {start}    Expiration: {end}",
            f"Named insured: {insured}",
        ]
        if vehicle is None:
            rows.append(f"VIN {policy.vin or '—'}    Plate {policy.plate_number or '—'}")
        else:
            car = " ".join(str(part) for part in (vehicle.year or "", vehicle.make or "") if part).strip()
            rows.append(f"{car or 'Vehicle'}    VIN {vehicle.vin or '—'}")
            rows.append(f"Plate {vehicle.plate_number or '—'}")
        rows.append(f"Agency: {agency}")
        if phone:
            rows.append(f"Phone: {phone}")
        for row in rows:
            c.drawString(left + 10, y, row[:58])
            y -= 12
        c.setFont("Helvetica", 7)
        c.drawString(left + 10, bottom + 10, "Temporary card issued by the agency. Carrier card replaces it.")
    c.save()
    return buffer.getvalue()


def compensation_disclosure_pdf(policy: InsurancePolicy) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    org = policy.organization
    agency = (getattr(org, "insurance_intake_display_name", "") or org.name or "This agency").strip()
    insured = policy.named_insured or (policy.client.name if policy.client_id else "the insured")
    fee = policy.broker_fee if policy.broker_fee is not None else "not entered"
    rate = policy.commission_rate if policy.commission_rate is not None else "not entered"
    y = 740
    c.setFont("Helvetica-Bold", 16)
    c.drawString(54, y, "Producer compensation disclosure")
    y -= 28
    y = _line(c, f"{agency} is a licensed insurance producer.", y)
    y = _line(c, f"Named insured: {insured}", y)
    y = _line(c, f"Policy: {policy.policy_number}", y)
    y = _line(c, f"Broker fee charged by the agency: {fee}", y)
    y = _line(c, f"Commission rate from the carrier, if known: {rate}%", y)
    y -= 6
    y = _line(
        c,
        "New York Insurance Regulation 194 requires this agency to tell you, when you ask,",
        y,
    )
    y = _line(c, "how it is compensated for placing this policy. The figures above are what we have on file.", y)
    y = _line(c, "Ask us if you want the compensation for a specific quote in more detail.", y)
    c.showPage()
    c.save()
    return buffer.getvalue()


def certificate_pdf(certificate) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    policy = certificate.policy
    org = policy.organization
    agency = (getattr(org, "insurance_intake_display_name", "") or org.name or "Agency").strip()
    carrier = policy.insurance_company.name if policy.insurance_company_id else "Carrier"
    insured = policy.named_insured or (policy.client.name if policy.client_id else "")
    y = 740
    c.setFont("Helvetica-Bold", 16)
    c.drawString(54, y, "Certificate of insurance")
    y -= 16
    c.setFont("Helvetica", 9)
    c.drawString(54, y, "Evidence of coverage for the holder named below. This is not an insurance policy.")
    y -= 28
    y = _line(c, f"Agency: {agency}", y, font="Helvetica-Bold")
    y = _line(c, f"Holder: {certificate.holder.name}", y)
    if certificate.holder.address:
        y = _line(c, certificate.holder.address, y)
    y = _line(c, f"Insured: {insured}", y)
    y = _line(c, f"Carrier: {carrier}", y)
    y = _line(c, f"Policy number: {policy.policy_number}", y)
    start = policy.start_date.isoformat() if policy.start_date else "—"
    end = policy.end_date.isoformat() if policy.end_date else "—"
    y = _line(c, f"Policy period: {start} to {end}", y)
    y = _line(c, f"Line: {policy.get_insurance_type_display() if policy.insurance_type else '—'}", y)
    y -= 6
    c.setFont("Helvetica-Bold", 12)
    c.drawString(54, y, "Limits on file")
    y -= 18
    for row in policy.coverages.filter(vehicle__isnull=True):
        extra = f"   Deductible ${row.deductible}" if row.deductible is not None else ""
        y = _line(c, f"{row.get_code_display()}: {row.limit_text or '—'}{extra}", y)
    y -= 6
    y = _line(c, f"Additional insured: {'Yes' if certificate.additional_insured else 'No'}", y)
    y = _line(c, f"Waiver of subrogation: {'Yes' if certificate.waiver_of_subrogation else 'No'}", y)
    if certificate.description:
        y = _line(c, f"Description: {certificate.description}", y)
    c.showPage()
    c.save()
    return buffer.getvalue()
