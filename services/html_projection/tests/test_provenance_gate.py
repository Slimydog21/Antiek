"""SPR-05 M4: provenance-completeness gate.

The artifact is honest about incomplete provenance: a banner with real counts
rather than fabricated citation density, and a visible "(unsourced)" marker on
claims whose chain does not resolve.
"""

from __future__ import annotations

import json

from services.html_projection.adapters.synthesis import (
    Claim,
    SourceRef,
    SynthesisExport,
    adapt_synthesis,
)

SOURCED = SourceRef(
    document_id="doc-pd",
    document_title="T",
    content_class="public_domain",
    ip_holder_id=None,
    locator="/x",
    chunk_text="txt",
)
UNRESOLVED = SourceRef(
    document_id=None,
    document_title=None,
    content_class=None,
    ip_holder_id=None,
)


def _exp(claims) -> SynthesisExport:
    return SynthesisExport(synthesis_id="s", target_question="Q?", claims=claims)


def test_complete_provenance_has_no_banner():
    dm = adapt_synthesis(_exp([Claim("A", [SOURCED]), Claim("B", [SOURCED])]))
    assert dm["metadata"]["provenance"] == {
        "fully_sourced": 2,
        "total": 2,
        "complete": True,
    }
    assert "Provenance incomplete" not in json.dumps(dm)


def test_incomplete_provenance_banner_with_correct_counts():
    dm = adapt_synthesis(
        _exp([Claim("A", [SOURCED]), Claim("B", []), Claim("C", [UNRESOLVED])])
    )
    assert dm["metadata"]["provenance"] == {
        "fully_sourced": 1,
        "total": 3,
        "complete": False,
    }
    # ensure_ascii=False so the em-dash matches (the ASCII leak-absence checks
    # elsewhere are unaffected — secret text is ASCII and never escaped).
    blob = json.dumps(dm, ensure_ascii=False)
    assert "Provenance incomplete — 1 of 3 claims fully sourced." in blob
    assert "(unsourced)" in blob  # the no-source and the unresolved claim
