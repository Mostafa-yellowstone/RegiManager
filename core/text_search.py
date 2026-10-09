"""Space-insensitive search, with a nearest-name fallback when nothing matches."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from django.db.models import Q

_WS_RE = re.compile(r"\s+")
_COMPACT_RE = re.compile(r"[\s\-]+")
_LETTER_RE = re.compile(r"[A-Za-z]")
_DIGIT_RE = re.compile(r"\D")

_NEAR_RATIO = 0.84
_SCAN_LIMIT = 2000


def collapse_text(value: str) -> str:
    return _WS_RE.sub(" ", (value or "").strip())


def compact_text(value: str) -> str:
    """Lowercase text with spaces and hyphens removed."""
    return _COMPACT_RE.sub("", collapse_text(value)).lower()


def _has_name_letters(value: str, min_len: int = 3) -> bool:
    return len(re.sub(r"[^A-Za-z]", "", value or "")) >= min_len


def flexible_pattern(value: str) -> str:
    """Case-insensitive pattern that ignores extra spaces and hyphens between characters."""
    compact = re.sub(r"[^A-Za-z0-9]", "", collapse_text(value))
    if not compact:
        return r"(?!)"
    return r"[\s\-]*".join(re.escape(char) for char in compact)


def field_contains_q(field: str, query: str) -> Q:
    collapsed = collapse_text(query)
    if not collapsed:
        return Q(pk__in=[])
    if _has_name_letters(collapsed):
        return Q(**{f"{field}__iregex": flexible_pattern(collapsed)})
    combined = Q(**{f"{field}__icontains": collapsed})
    digits = _DIGIT_RE.sub("", collapsed)
    spaceless = _WS_RE.sub("", collapsed)
    if digits and len(digits) >= 9 and digits != spaceless:
        combined |= Q(**{f"{field}__icontains": digits})
    return combined


def text_search_q(query: str, fields) -> Q:
    collapsed = collapse_text(query)
    if not collapsed or not fields:
        return Q(pk__in=[])
    combined = Q()
    for field in fields:
        combined |= field_contains_q(field, collapsed)
    return combined


def _score_pair(needle: str, haystack: str) -> float:
    if not needle or not haystack:
        return 0.0
    if needle == haystack:
        return 1.0
    if abs(len(needle) - len(haystack)) > 8:
        return 0.0
    return SequenceMatcher(None, needle, haystack).ratio()


def nearest_ids(queryset, query: str, fields, *, scan_limit: int = _SCAN_LIMIT) -> list:
    needle = compact_text(query)
    if len(needle) < 4 or not _has_name_letters(query, 4) or not fields:
        return []
    scored = []
    rows = queryset.order_by("-pk").values("pk", *fields)[:scan_limit]
    for row in rows:
        best = 0.0
        parts = []
        for field in fields:
            text = row.get(field) or ""
            parts.append(str(text))
            best = max(best, _score_pair(needle, compact_text(text)))
        best = max(best, _score_pair(needle, compact_text(" ".join(parts))))
        if best >= _NEAR_RATIO:
            scored.append((best, row["pk"]))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return [pk for _, pk in scored]


def apply_text_search(queryset, query: str, fields, *, extra_q: Q | None = None, nearest: bool = True):
    """Filter to space-insensitive matches, then the closest names if that finds nothing."""
    collapsed = collapse_text(query)
    if not collapsed:
        return queryset
    exact = text_search_q(collapsed, fields)
    if extra_q is not None and extra_q.children:
        exact |= extra_q
    matched = queryset.filter(exact).distinct()
    if matched.exists():
        return matched
    if not nearest:
        return queryset.none()
    ids = nearest_ids(queryset, collapsed, fields)
    if not ids:
        return queryset.none()
    return queryset.filter(pk__in=ids).distinct()
