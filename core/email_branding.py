"""Space-branded HTML chrome for outbound email (logo, name, phone, email, copyright)."""

from __future__ import annotations

import base64
import os
from email.mime.image import MIMEImage

from django.template.loader import render_to_string
from django.utils import timezone

from .insurance_ledger_pdf import agency_branding
from .models import Space

LOGO_CID = "rm-space-logo"


def _logo_bytes(path: str) -> bytes:
    if not path or not os.path.isfile(path):
        return b""
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def _logo_data_uri(path: str, raw: bytes) -> str:
    if not raw:
        return ""
    ext = os.path.splitext(path or "")[1].lower()
    mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
    if ext == ".gif":
        mime = "image/gif"
    elif ext == ".webp":
        mime = "image/webp"
    payload = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{payload}"


def email_brand_for_org(org, space: Space | None = None) -> dict:
    """Letterhead for a space: logo, name, email, phone, plus org copyright next to RegiManager."""
    brand = agency_branding(org, space)
    path = brand.get("logo_path") or ""
    raw = _logo_bytes(path)
    year = timezone.now().year
    org_name = (getattr(org, "name", "") or brand.get("name") or "this agency").strip()
    return {
        **brand,
        "org_name": org_name,
        "logo_bytes": raw,
        "logo_cid": LOGO_CID if raw else "",
        "logo_data_uri": _logo_data_uri(path, raw),
        "copyright_line": f"© {year} {org_name} · RegiManager",
    }


def wrap_email_html(inner_html: str, brand: dict, *, logo_mode: str = "cid") -> str:
    logo_src = ""
    if brand.get("logo_bytes"):
        if logo_mode == "data":
            logo_src = brand.get("logo_data_uri") or ""
        else:
            logo_src = f"cid:{LOGO_CID}"
    return render_to_string(
        "core/emails/branded_frame.html",
        {
            "inner_html": inner_html,
            "brand": brand,
            "logo_src": logo_src,
        },
    )


def attach_brand_logo(message, brand: dict) -> None:
    raw = brand.get("logo_bytes") or b""
    if not raw:
        return
    image = MIMEImage(raw)
    image.add_header("Content-ID", f"<{LOGO_CID}>")
    image.add_header("Content-Disposition", "inline", filename="logo.png")
    message.attach(image)
    message.mixed_subtype = "related"
