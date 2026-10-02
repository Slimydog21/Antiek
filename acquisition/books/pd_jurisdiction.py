"""A public-domain assertion limited to a jurisdiction other than the one we
serve from is not public domain FOR US.

The three free-text rights gates (Internet Archive, Library of Congress,
archive.org via public_domain.py) accept any rights string that contains a
PD token unless a denylist of negations / copyright claims matches first.
"Public domain in Canada" and "Public Domain in the United Kingdom only"
contain the token, match no denied phrase, and were stamped ``public_domain``
— publicly servable and indexed — although the serving jurisdiction is the
United States (acquisition/books/hathitrust.py states the decision) and
such works are routinely still in US copyright (life+50 vs life+70 / the
1929 line).

This module is the one place the rule lives. It is written as an ALLOW
rule, not a longer denylist: a PD assertion that is qualified to a place
is accepted only when that place is the serving jurisdiction or the whole
world. Any other qualification — a named country, a region, "outside the
US", a place this module has never heard of — is not PD for serving. A new
country needs no code change to be gated; that is the point.
"""

from __future__ import annotations

import re

# The jurisdiction we serve from. hathitrust.py already encodes the same
# decision ("US is the serving jurisdiction, so both are servable").
SERVING_JURISDICTION_TOKENS: tuple[str, ...] = (
    "united states",
    "u.s",  # "U.S.", "U.S.A." — the clause regex may drop a final dot
    "usa",
    " us",  # "in the us", "in us"
    "america",
)
# Qualifications that mean "everywhere" and so include the serving jurisdiction.
_GLOBAL_TOKENS: tuple[str, ...] = (
    "worldwide",
    "world-wide",
    "globally",
    "everywhere",
    "all countries",
    "the world",
    "internationally",
)

# "public domain" followed (within the same clause) by a limiting preposition
# and the place it limits to. The place runs to the end of the clause.
# The place runs to the end of the clause; a dot inside an abbreviation
# ("U.S.") does not end it, a dot followed by whitespace or the end does.
_QUALIFIED_PD_RE = re.compile(
    r"public[\s-]*domain\s*\(?\s*(?:only\s+)?"
    r"(?P<prep>in|within|for|throughout|across|under|outside(?:\s+of)?)\s+"
    r"(?P<where>(?:[^.;:)\n]|\.(?!\s|$)){1,80})",
    re.IGNORECASE,
)


def non_serving_pd_qualification(rights_text: str) -> str | None:
    """The place a PD assertion in ``rights_text`` is limited to, when that
    place is NOT the serving jurisdiction (nor the whole world); ``None``
    when the assertion is unqualified, or qualified to the US / worldwide.

    A non-None result means: do not accept the PD token in this text.
    """
    for m in _QUALIFIED_PD_RE.finditer(rights_text or ""):
        place = m.group("where").strip()
        where = " " + place.lower()
        names_us = any(tok in where for tok in SERVING_JURISDICTION_TOKENS)
        names_world = any(tok in where for tok in _GLOBAL_TOKENS)
        if m.group("prep").lower().startswith("outside"):
            # "outside X" is PD everywhere EXCEPT X: it includes the serving
            # jurisdiction unless X is the serving jurisdiction (or the world).
            if names_us or names_world:
                return f"outside {place}"
            continue
        if names_us or names_world:
            continue
        return place
    return None


__all__ = ["SERVING_JURISDICTION_TOKENS", "non_serving_pd_qualification"]
