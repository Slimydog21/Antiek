"""Foreign-HTML sanitizer (HPRJ SPR-07 M3).

For HTML that NEVER came from Antiek (acquisition/urls, the universal ingest),
this is the quarantine decision. It does NOT fork the ingest path — it REUSES
the SPR-02 zero-script gate's `find_violations` (script tags, event handlers,
javascript:/vbscript: with obfuscation decoding, external src/srcset, CSS
expression/url, meta refresh, base href, external object/link/svg/use fetch)
and ADDS the foreign-only buckets the gate (tuned for Antiek's own clean
output) does not target:

- ``data:`` payloads (`data:text/html` / `data:application/*` / `data:image/svg`)
  — executable/navigable without a remote fetch;
- SVG ``<foreignObject>`` — embeds arbitrary HTML/script inside SVG;
- iframe ``srcdoc`` — an inline HTML document, a nested vector;
- spoofed ``data-antiek`` island markers — a foreign file carrying Antiek's
  own markers is impersonating a born-Antiek artifact (D9: special markers as
  attack surface). Real born-Antiek artifacts go through the SIGNATURE-gated
  `ingest_antiek` path, never here.

Decision: ANY vector QUARANTINES. We do not attempt lossy in-place stripping —
quarantine-on-violation is the safe default; the violation list is the logged
reason. Clean HTML passes through to the existing ingest unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from services.html_projection.gate import Violation, find_violations

# data: with an executable/navigable media type (a plain data:image/png is not
# matched — that is an inert raster the ingest never executes).
_DATA_PAYLOAD_RE = re.compile(
    r"data:\s*(?:text/html|application/[^,;\"')\s]+|image/svg)", re.IGNORECASE
)
_FOREIGN_OBJECT_RE = re.compile(r"<\s*foreignObject\b", re.IGNORECASE)
_SRCDOC_RE = re.compile(r"\bsrcdoc\s*=", re.IGNORECASE)
_ANTIEK_MARKER_RE = re.compile(r"data-antiek\s*=", re.IGNORECASE)

# (kind, regex) — the foreign-only buckets, in deterministic order.
_FOREIGN_EXTRA: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("data_uri_payload", _DATA_PAYLOAD_RE),
    ("svg_foreign_object", _FOREIGN_OBJECT_RE),
    ("iframe_srcdoc", _SRCDOC_RE),
    ("spoofed_antiek_marker", _ANTIEK_MARKER_RE),
)


@dataclass(frozen=True)
class SanitizeResult:
    safe: bool
    quarantined: bool
    violations: list = field(default_factory=list)
    reason: str | None = None


def find_foreign_violations(html: str) -> list[Violation]:
    """Every vector that quarantines foreign HTML: the SPR-02 gate's set PLUS
    the foreign-only buckets. Pure + deterministic; reuses the gate (no fork)."""
    violations = list(find_violations(html))
    for kind, pattern in _FOREIGN_EXTRA:
        match = pattern.search(html)
        if match:
            violations.append(Violation(kind, match.group(0)[:60]))
    return violations


def sanitize_foreign_html(html: str) -> SanitizeResult:
    """Quarantine foreign HTML carrying ANY vector; pass clean HTML through."""
    violations = find_foreign_violations(html)
    if violations:
        kinds = sorted({v.kind for v in violations})
        return SanitizeResult(
            safe=False,
            quarantined=True,
            violations=violations,
            reason=f"foreign HTML carries vectors: {kinds}",
        )
    return SanitizeResult(safe=True, quarantined=False, violations=[], reason=None)


__all__ = [
    "SanitizeResult",
    "find_foreign_violations",
    "sanitize_foreign_html",
]
