from django import template

register = template.Library()


@register.filter
def short_receipt(value):
    """Compact RCPT-YYYYMMDDHHMMSS-ORG numbers for CRM tables."""
    if not value:
        return ""
    text = str(value)
    if text.startswith("RCPT-") and text.count("-") >= 2:
        prefix, timestamp, suffix = text.split("-", 2)
        short_ts = timestamp[-6:] if len(timestamp) >= 6 else timestamp
        return f"{prefix}-{short_ts}-{suffix}"
    if len(text) > 18:
        return f"{text[:15]}…"
    return text
