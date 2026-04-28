"""
Project-wide JSON response class that rewrites ISO date / datetime strings
to `DD-MM-YYYY` right before serialization.

Wired in main.py via `FastAPI(default_response_class=DateFormattedJSONResponse)`.
Affects every JSON response from any endpoint (MACRO, AHLOA, dashboards, pace
constraints, etc.) without touching individual services. Streaming responses
(CSV exports) are unaffected because they don't use this response class.
"""

import re
from fastapi.responses import JSONResponse

# Match a string that *starts with* YYYY-MM-DD and is either:
#   - exactly 10 chars (a pure date), or
#   - followed by a 'T' or space + a time component (ISO datetime).
# Anchoring with ^ and $ avoids matching dates embedded inside longer text
# (e.g. comments like "Suggested 2026-06-15 due to delay in NTP").
_ISO_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)


def _to_ddmmyyyy(s: str) -> str:
    """Take an ISO date or datetime string, return its DD-MM-YYYY date part."""
    y, m, d = s[:10].split("-")
    return f"{d}-{m}-{y}"


def reformat_dates(obj):
    """Walk a JSON-ready structure and rewrite ISO date strings in place-style."""
    if isinstance(obj, dict):
        return {k: reformat_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [reformat_dates(v) for v in obj]
    if isinstance(obj, str) and _ISO_DATE_RE.match(obj):
        return _to_ddmmyyyy(obj)
    return obj


class DateFormattedJSONResponse(JSONResponse):
    """JSONResponse that rewrites every ISO date string in the body to DD-MM-YYYY."""

    def render(self, content) -> bytes:
        return super().render(reformat_dates(content))
