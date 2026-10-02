"""The ONE deny-first rule the free-text public-domain gates share.

Three gates read a record's free-text rights fields and accept a public-
domain token unless the text also carries a negation, a copyright claim or
a non-serving jurisdiction: Internet Archive (``internet_archive.py``),
Library of Congress (``library_of_congress.py``) and archive.org via
``public_domain.py``. Each carried its own copy of the deny lists, and the
copies drifted: ``public_domain.py``'s copyright-claim regex lacked the
hedged forms ("may be / still / possibly under copyright"), Internet Archive
lacked "rights restricted", Library of Congress lacked "not public domain".
A record was therefore PD or not depending on which connector found it.

This module is the union of the three deny lists — strictly the most
conservative of them — plus the serving-jurisdiction rule. A gate calls
:func:`pd_denied_reason` on its lower-cased haystack BEFORE any acceptance
and stops on a non-None answer. Acceptance (which PD tokens / licence URLs
each source recognises) stays per gate: widening acceptance would loosen
the gate; widening denial only tightens it.
"""

from __future__ import annotations

import re

from acquisition.books.pd_jurisdiction import non_serving_pd_qualification

# Phrases that disqualify a record outright, whatever else it says.
NEGATIVE_TOKENS: tuple[str, ...] = (
    "all rights reserved",
    "rights reserved",
    "all rights",
    "in copyright",
    "in-copyright",
    "copyrighted",
    "under copyright",
    "rights restricted",
    "permission required",
    "not in the public domain",
    "not in public domain",
    "not public domain",
)

# "not / no / isn't / is not (in the) public domain" in any spacing.
NEGATED_PD_RE = re.compile(
    r"\b(?:not|no|isn't|is not)\s+(?:in\s+(?:the\s+)?)?public\s+domain"
)

# Any ©/(c) symbol, "copyright <year>", or a HEDGED copyright assertion
# ("may be / still / possibly / likely under/protected by copyright") — the
# hedge is the higher-cost false positive and is denied on purpose.
COPYRIGHT_CLAIM_RE = re.compile(
    r"©|\bcopyright\s+(?:\(c\)\s*)?\d{4}|\(c\)\s*\d{4}"
    r"|\b(?:may\s+be|still|possibly|likely)\s+(?:in\s+|under\s+|protected\s+by\s+)?copyright"
)


def pd_denied_reason(haystack: str) -> str | None:
    """Why ``haystack`` (already lower-cased, all rights fields joined) must
    NOT be accepted as public domain — or ``None`` when nothing denies it.

    Order is deny-first and total: a negative phrase, a negated PD phrase, a
    copyright claim, then a PD assertion limited to a non-serving
    jurisdiction. The reason names the rule and the text it matched, for the
    audit trail; callers only branch on ``is not None``.
    """
    for tok in NEGATIVE_TOKENS:
        if tok in haystack:
            return f"negative phrase: {tok!r}"
    m = NEGATED_PD_RE.search(haystack)
    if m:
        return f"negated public domain: {m.group(0)!r}"
    m = COPYRIGHT_CLAIM_RE.search(haystack)
    if m:
        return f"copyright claim: {m.group(0)!r}"
    place = non_serving_pd_qualification(haystack)
    if place is not None:
        return f"public domain only in a non-serving jurisdiction: {place!r}"
    return None


__all__ = ["COPYRIGHT_CLAIM_RE", "NEGATED_PD_RE", "NEGATIVE_TOKENS", "pd_denied_reason"]
