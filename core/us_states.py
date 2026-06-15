"""US state codes shared across models and DMV catalogs."""

US_STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"), ("CA", "California"),
    ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"), ("FL", "Florida"), ("GA", "Georgia"),
    ("HI", "Hawaii"), ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
    ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"), ("MO", "Missouri"),
    ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"),
    ("NM", "New Mexico"), ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
    ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"),
    ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
]

US_STATE_CODES = frozenset(code for code, _ in US_STATES)
STATE_LABEL_BY_CODE = dict(US_STATES)


def normalize_state_code(value: str) -> str:
    """Return a 2-letter state code; defaults to NY when unknown."""
    raw = (value or "").strip()
    if not raw:
        return "NY"

    upper = raw.upper()
    if upper in US_STATE_CODES:
        return upper

    for code, name in US_STATES:
        if name.upper() == upper:
            return code

    # Typed partial names (e.g. "Penn" -> PA) when unambiguous.
    if len(upper) >= 3:
        matches = [code for code, name in US_STATES if name.upper().startswith(upper)]
        if len(matches) == 1:
            return matches[0]

    alpha = "".join(ch for ch in upper if ch.isalpha())
    if len(alpha) == 2 and alpha in US_STATE_CODES:
        return alpha

    return "NY"


def get_state_label(state_code: str) -> str:
    code = normalize_state_code(state_code)
    return STATE_LABEL_BY_CODE.get(code, code)
