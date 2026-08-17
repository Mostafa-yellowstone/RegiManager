"""Personalize email campaign HTML for each CRM contact."""

from __future__ import annotations

import html
import re

from .models import EmailMarketingContact

TOKEN_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def contact_token_map(contact: EmailMarketingContact | None) -> dict[str, str]:
    if not contact:
        return {}
    return {
        "name": contact.name or "",
        "address_line1": contact.address_line1 or "",
        "address_line2": contact.address_line2 or "",
        "address_line3": contact.address_line3 or "",
        "city": contact.city or "",
        "state": contact.state or "",
        "zip_code": contact.zip_code or "",
        "phone": contact.phone or "",
        "email": contact.email or "",
        "website": contact.website or "",
        "full_address": contact.full_address,
    }


def personalize_text(text: str, contact: EmailMarketingContact | None) -> str:
    tokens = contact_token_map(contact)

    def replace_token(match):
        key = match.group(1).lower()
        return tokens.get(key, "")

    return TOKEN_PATTERN.sub(replace_token, text or "")


def render_campaign_html(
    html_content: str,
    css_content: str,
    contact: EmailMarketingContact | None,
    brand: dict | None = None,
    *,
    logo_mode: str = "cid",
) -> str:
    tokens = contact_token_map(contact)

    def replace_token(match):
        key = match.group(1).lower()
        return html.escape(tokens.get(key, ""))

    body = TOKEN_PATTERN.sub(replace_token, html_content or "")
    style_block = f"<style>{css_content or ''}</style>" if (css_content or "").strip() else ""
    inner = f"{style_block}{body}"
    if brand:
        from .email_branding import wrap_email_html

        return wrap_email_html(inner, brand, logo_mode=logo_mode)
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{inner}</body></html>"
