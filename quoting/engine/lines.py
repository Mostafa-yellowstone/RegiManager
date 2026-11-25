"""Line-of-business registry.

v1 registers personal auto in New York. Another line is a new validator
plus carriers that opt into it. The quote job does not special-case the line.
"""

from __future__ import annotations

from dataclasses import dataclass

from quoting.engine.types import Application, Issue


@dataclass(frozen=True)
class LineOfBusiness:
    key: str
    jurisdiction: str
    label: str


PERSONAL_AUTO_NY = LineOfBusiness(
    key="personal_auto",
    jurisdiction="NY",
    label="Personal auto",
)

_VALIDATORS = {
    (PERSONAL_AUTO_NY.key, PERSONAL_AUTO_NY.jurisdiction): "quoting.lines.personal_auto_ny",
}


def registered_lines() -> tuple[LineOfBusiness, ...]:
    return (PERSONAL_AUTO_NY,)


def line_supported(line: str, jurisdiction: str) -> bool:
    return (line, jurisdiction) in _VALIDATORS


def validate_application(application: Application, *, today) -> tuple[Issue, ...]:
    key = (application.line, application.jurisdiction)
    if key not in _VALIDATORS:
        label = application.line or "this line"
        state = application.jurisdiction or "this state"
        return (
            Issue(
                "line",
                f"{label} in {state} is not quotable in v1. The desk currently quotes New York personal auto.",
            ),
        )
    from quoting.lines.personal_auto_ny import validate

    return validate(application, today=today)
