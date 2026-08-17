"""Space-branded HTML chrome for outbound email (logo, name, phone, email, copyright)."""

from __future__ import annotations

import base64
import logging
import os
from email.mime.image import MIMEImage
from io import BytesIO

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from .insurance_ledger_pdf import agency_branding
from .models import Space

logger = logging.getLogger(__name__)

LOGO_CID = "rm-space-logo"


def outbound_from_email() -> str:
    return (
        getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or getattr(settings, "EMAIL_HOST_USER", "")
        or "noreply@regimanager.local"
    )


def mail_is_configured() -> bool:
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    if "console" in backend or "locmem" in backend:
        return True
    return bool(getattr(settings, "EMAIL_HOST_USER", "") and outbound_from_email())


def _logo_bytes(path: str) -> bytes:
    if not path or not os.path.isfile(path):
        return b""
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def _png_bytes_for_email(raw: bytes) -> bytes:
    from PIL import Image

    image = Image.open(BytesIO(raw))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")
    image.thumbnail((160, 160), Image.Resampling.LANCZOS)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _logo_data_uri(path: str, raw: bytes) -> str:
    png = b""
    try:
        png = _png_bytes_for_email(raw) if raw else b""
    except Exception:
        png = raw if raw else b""
    if not png:
        return ""
    payload = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{payload}"


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


def attach_brand_logo(message, brand: dict) -> bool:
    """Attach a PNG CID logo. Never raise — skip the image if it cannot be inlined."""
    raw = brand.get("logo_bytes") or b""
    if not raw:
        return False
    try:
        png = _png_bytes_for_email(raw)
        image = MIMEImage(png, _subtype="png")
        if "Content-ID" in image:
            del image["Content-ID"]
        image.add_header("Content-ID", f"<{LOGO_CID}>")
        image.add_header("Content-Disposition", "inline", filename="logo.png")
        message.attach(image)
        message.mixed_subtype = "related"
        return True
    except Exception:
        logger.exception("Could not attach space logo to outbound email")
        return False
