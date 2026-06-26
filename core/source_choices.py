"""Shared helpers for building de-duplicated client/source dropdown choices."""

from django.db.models import Q

SOURCE_LABELS = {
    "google_search": "🔍 Google Search",
    "walk_in": "🚶 Walk-In",
    "website": "🌐 Website",
    "meta_platform": "📘 Meta Platform",
    "google_campaigns": "📢 Google Campaigns",
    "existing_client": "🤝 Existing Client",
    "dealer": "🏪 Dealer",
    "referral": "💬 Referral",
    "cold_calling": "📞 Cold Calling",
    "insurance": "🛡️ Insurance",
    "other": "📦 Other",
}

STANDARD_SOURCE_KEYS = [
    "google_search", "walk_in", "website", "meta_platform",
    "google_campaigns", "existing_client", "dealer", "referral",
    "cold_calling", "insurance", "other",
]

INSURANCE_SOURCE_CHOICES = [
    {"key": key, "label": SOURCE_LABELS[key]}
    for key in [
        "walk_in", "google_search", "meta_platform", "google_campaigns",
        "existing_client", "dealer", "referral", "cold_calling",
    ]
]


def norm_source(value):
    """Normalize a source value: lowercase, strip, replace dashes with underscores."""
    if not value:
        return ""
    return str(value).lower().strip().replace("-", "_")


_GENERIC_RECEIPT_SOURCES = frozenset({"", "walk_in", "walkin", "other"})


def resolve_acquisition_source_for_record(record) -> str:
    """
    Canonical acquisition source for analytics on a service transaction.

    Vehicle service receipts usually keep the model default (walk-in) because the
    start-process form does not expose source. The client profile stores the real
    acquisition channel (google_search, meta_platform, website, etc.).
    """
    record_source = (getattr(record, "source", None) or "").strip()
    vehicle = getattr(record, "vehicle", None)
    client = getattr(vehicle, "client", None) if vehicle else None
    client_source = (getattr(client, "source", None) or "").strip() if client else ""

    if client_source:
        client_key = norm_source(client_source)
        record_key = norm_source(record_source)
        if client_key not in _GENERIC_RECEIPT_SOURCES:
            return client_source
        if record_key not in _GENERIC_RECEIPT_SOURCES:
            return record_source
        return client_source

    return record_source


def referral_name_keys(organizations):
    """Normalized referral entity names — excluded from source dropdowns."""
    from .models import Referral

    return {
        norm_source(name)
        for name in Referral.objects.filter(organization__in=organizations).values_list("name", flat=True)
        if name
    }


def _label_for_key(key, raw_value=None):
    if key in SOURCE_LABELS:
        return SOURCE_LABELS[key]
    display = raw_value or key
    return str(display).replace("_", " ").replace("-", " ").title()


def build_source_choices(db_values, organizations=None, exclude_referral_names=True):
    """
    Build de-duplicated source choices for filter dropdowns.
    Returns list of {'key': str, 'label': str}.
    """
    exclude = set()
    if exclude_referral_names and organizations is not None:
        exclude = referral_name_keys(organizations)

    choices = []
    seen = set()

    for sk in STANDARD_SOURCE_KEYS:
        choices.append({"key": sk, "label": _label_for_key(sk)})
        seen.add(sk)

    for raw in sorted({v for v in db_values if v}, key=str.lower):
        key = norm_source(raw)
        if not key or key in seen or key in exclude:
            continue
        choices.append({"key": key, "label": _label_for_key(key, raw)})
        seen.add(key)

    return choices


def build_form_source_choices(organizations, base_choices, include_custom_sources=True):
    """
    Build (value, label) tuples for ModelForm source fields.
    Excludes custom sources whose labels match referral entity names.
    """
    exclude = referral_name_keys(organizations)
    choices = list(base_choices)
    seen = {norm_source(value) for value, _ in choices}

    if include_custom_sources and organizations.exists():
        from .models import CustomSourceType

        for cs in CustomSourceType.objects.filter(organization__in=organizations):
            key = norm_source(cs.label)
            if key in seen or key in exclude:
                continue
            choices.append((cs.label.lower(), cs.label))
            seen.add(key)

    return choices


def source_filter_q(source_filter, field_name="source"):
    """Q object matching a normalized source filter against legacy stored variants."""
    if not source_filter:
        return Q()

    norm = norm_source(source_filter)
    variants = {
        source_filter,
        norm,
        norm.replace("_", "-"),
        norm.replace("-", "_"),
    }
    q = Q()
    for variant in variants:
        if variant:
            q |= Q(**{f"{field_name}__iexact": variant})
    return q
