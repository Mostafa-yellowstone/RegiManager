"""Configurable appetite — rules live on AppetiteRule, not inside connectors."""

from __future__ import annotations


class AppetiteDecision:
    def __init__(self, result: str, reasons: list[str]):
        self.result = result
        self.reasons = reasons


def evaluate_appetite(market, canonical: dict) -> AppetiteDecision:
    rules = list(market.appetite_rules.filter(is_active=True).order_by("priority", "id"))
    if not rules:
        return AppetiteDecision("unknown", ["No appetite rules configured for this market."])
    for rule in rules:
        matched, details = _match(rule.criteria or [], canonical)
        if matched:
            result = (rule.result_on_match or "eligible").lower()
            return AppetiteDecision(result, [f"Rule '{rule.name}' matched."] + details)
    return AppetiteDecision("ineligible", ["No appetite rule matched."])


def _match(criteria: list, canonical: dict) -> tuple[bool, list[str]]:
    details = []
    if not criteria:
        return True, ["Empty criteria (always match)."]
    for item in criteria:
        field = str(item.get("field") or "")
        op = str(item.get("op") or "eq")
        expected = item.get("value")
        actual = _dig(canonical, field)
        ok = _compare(op, actual, expected)
        details.append(f"{field} {op} {expected!r} (actual={actual!r}) -> {ok}")
        if not ok:
            return False, details
    return True, details


def _dig(data: dict, dotted: str):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _compare(op: str, actual, expected) -> bool:
    if op == "eq":
        return str(actual or "").lower() == str(expected or "").lower()
    if op == "in":
        values = expected if isinstance(expected, list) else [expected]
        return str(actual or "").upper() in {str(v).upper() for v in values}
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not actual
    return False
