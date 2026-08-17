"""Stamp signature fields onto an uploaded PDF and append a completion certificate."""

from __future__ import annotations

import base64
import re
from datetime import datetime
from io import BytesIO

from django.core.files.base import ContentFile
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from PIL import Image

NAVY = colors.HexColor("#0B3A6E")
TEAL = colors.HexColor("#0F766E")
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")

_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|gif);base64,(.+)$", re.I)


def decode_data_url(raw: str) -> bytes | None:
    text = (raw or "").strip()
    match = _DATA_URL_RE.match(text)
    if not match:
        return None
    try:
        return base64.b64decode(match.group(2), validate=False)
    except Exception:
        return None


def _image_reader(raw_bytes: bytes) -> ImageReader | None:
    try:
        image = Image.open(BytesIO(raw_bytes))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        image.thumbnail((900, 360), Image.Resampling.LANCZOS)
        buf = BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


def _page_size(page) -> tuple[float, float]:
    box = page.mediabox
    return float(box.width), float(box.height)


def _draw_fields(c, page_w, page_h, fields):
    for field in fields:
        try:
            x_frac = float(field.get("x", 0))
            y_frac = float(field.get("y", 0))
            w_frac = float(field.get("w", 0.2))
            h_frac = float(field.get("h", 0.06))
        except (TypeError, ValueError):
            continue
        width = max(18, w_frac * page_w)
        height = max(12, h_frac * page_h)
        x = x_frac * page_w
        y = page_h - (y_frac * page_h) - height
        kind = (field.get("type") or "signature").lower()
        image_bytes = decode_data_url(field.get("image") or "")
        if image_bytes and kind in {"signature", "initials"}:
            reader = _image_reader(image_bytes)
            if reader:
                c.drawImage(
                    reader,
                    x,
                    y,
                    width=width,
                    height=height,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                continue
        text = str(field.get("text") or "").strip()
        if not text:
            continue
        font = "Times-Italic" if kind in {"signature", "initials"} else "Helvetica"
        size = max(8, min(height * 0.72, 16 if kind == "date" else 22))
        c.setFillColor(INK)
        c.setFont(font, size)
        c.drawString(x + 2, y + (height - size) / 2, text[:80])


def _certificate_page(envelope, prepared_at: datetime) -> bytes:
    buf = BytesIO()
    page_w, page_h = letter
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFillColor(NAVY)
    c.rect(0, page_h - 72, page_w, 72, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.rect(0, page_h - 76, page_w, 4, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, page_h - 38, "Certificate of completion")
    c.setFont("Helvetica", 9)
    c.drawString(36, page_h - 54, "Insurance Space e-signature  ·  Official signing record")

    y = page_h - 120
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, y, envelope.title[:90])
    y -= 28
    rows = [
        ("Status", "Completed / digitally applied"),
        ("Signed by", envelope.signer_name or "—"),
        ("Signer email", envelope.signer_email or "—"),
        ("Completed", prepared_at.strftime("%b %d, %Y  %I:%M %p")),
        ("IP address", envelope.signed_ip or "—"),
        ("Envelope ID", str(envelope.id)),
    ]
    c.setFont("Helvetica", 10)
    for label, value in rows:
        c.setFillColor(MUTED)
        c.drawString(36, y, label)
        c.setFillColor(INK)
        c.drawString(180, y, str(value)[:90])
        y -= 18

    y -= 12
    c.setStrokeColor(TEAL)
    c.setLineWidth(1)
    c.line(36, y, page_w - 36, y)
    y -= 28
    c.setFont("Helvetica", 8.5)
    c.setFillColor(MUTED)
    text = (
        "This page records that the signature, initials, date, and typed fields were applied "
        "to the attached document in Insurance Space. The signed file is a flattened copy of "
        "the original PDF. It is an agency signing record, not a third-party notary seal."
    )
    for line in _wrap(text, 98):
        c.drawString(36, y, line)
        y -= 12
    c.save()
    return buf.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def stamp_envelope_pdf(envelope, fields: list[dict]) -> ContentFile:
    source = envelope.original_file
    with source.open("rb") as handle:
        original_bytes = handle.read()
    reader = PdfReader(BytesIO(original_bytes))

    by_page: dict[int, list[dict]] = {}
    for field in fields or []:
        try:
            page_no = int(field.get("page") or 1)
        except (TypeError, ValueError):
            page_no = 1
        by_page.setdefault(max(1, page_no), []).append(field)

    writer = PdfWriter()
    for index, page in enumerate(reader.pages, start=1):
        if getattr(page, "rotation", 0):
            try:
                page.transfer_rotation_to_content()
            except Exception:
                pass
        page_w, page_h = _page_size(page)
        overlay = BytesIO()
        c = canvas.Canvas(overlay, pagesize=(page_w, page_h))
        _draw_fields(c, page_w, page_h, by_page.get(index, []))
        c.save()
        overlay.seek(0)
        overlay_page = PdfReader(overlay).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    cert = PdfReader(BytesIO(_certificate_page(envelope, timezone.localtime())))
    writer.add_page(cert.pages[0])
    writer.add_metadata({
        "/Title": f"Signed — {envelope.title}"[:180],
        "/Author": envelope.organization.name,
        "/Subject": "Insurance Space e-signature",
    })
    out = BytesIO()
    writer.write(out)
    filename = f"signed-{envelope.id}.pdf"
    return ContentFile(out.getvalue(), name=filename)
