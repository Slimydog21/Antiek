"""Cross-source dedup collapse (SPR-07 G3).

The same paper surfaced via CORE + Semantic Scholar + arXiv-bulk under ONE
shared DOI collapses to exactly one document — keyed through the single
``substrate.dedup`` identity ladder (DOI precedence). Papers are the source
family where cross-source duplication is most severe, so this is the
load-bearing correctness gate.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.corpus_quality import dedup_candidates  # noqa: E402
from acquisition.papers import paper_candidate_ref  # noqa: E402
from acquisition.papers.arxiv_bulk import paper_to_record as bulk_to_record  # noqa: E402
from acquisition.papers.core import work_to_record as core_to_record  # noqa: E402
from acquisition.papers.semantic_scholar import paper_to_record as s2_to_record  # noqa: E402
from acquisition.arxiv.client import ArxivPaper  # noqa: E402
from substrate.dedup import KeyType, collapse, identity_key  # noqa: E402

_SHARED_DOI = "10.1234/the-same-paper"
_CC_BY = "https://creativecommons.org/licenses/by/4.0/"


def _core_record():
    return core_to_record(
        {"id": "core-1", "doi": _SHARED_DOI, "title": "The Same Paper",
         "license": _CC_BY, "downloadUrl": "https://core/x.pdf"}
    )


def _s2_record():
    return s2_to_record(
        {"corpusId": 555, "title": "The Same Paper",
         "externalIds": {"DOI": _SHARED_DOI},
         "openAccessPdf": {"url": "https://s2/x.pdf", "license": "CC-BY"}}
    )


def _arxiv_bulk_record():
    return bulk_to_record(
        ArxivPaper(
            arxiv_id="2401.55555", version="v1", title="The Same Paper",
            authors=["Ada Lovelace"], abstract="a", categories=["cs.LG"],
            primary_category="cs.LG", published_at=None, updated_at=None,
            abs_url="https://arxiv.org/abs/2401.55555",
            pdf_url="https://arxiv.org/pdf/2401.55555",
            license_uri=_CC_BY, raw_id="2401.55555",
            metadata={"source": "arxiv_bulk", "doi": _SHARED_DOI},
        )
    )


def test_three_sources_same_doi_collapse_to_one_document():
    records = [_core_record(), _s2_record(), _arxiv_bulk_record()]
    # Each independently resolves to the SAME DOI identity key.
    for rec in records:
        ikey = identity_key(paper_candidate_ref(rec).identity_record())
        assert ikey.key_type is KeyType.DOI
        assert ikey.key == _SHARED_DOI.lower()

    refs = [paper_candidate_ref(rec) for rec in records]
    result = dedup_candidates(refs)
    # Exactly one document survives; the other two are dropped duplicates.
    assert len(result.kept) == 1
    assert len(result.dropped) == 2


def test_collapse_records_all_three_contributing_sources():
    records = [_core_record(), _s2_record(), _arxiv_bulk_record()]
    identity_records = []
    from substrate.dedup import IdentityRecord

    for rec in records:
        cr = paper_candidate_ref(rec)
        identity_records.append(
            IdentityRecord(
                ref_id=cr.ref_id, source=rec.source, doi=cr.doi,
                arxiv_id=cr.arxiv_id, source_id=cr.source_id,
                title=cr.title, author=cr.author,
            )
        )
    works = collapse(identity_records)
    assert len(works) == 1
    # All three sources are recorded as contributors (defensibility / audit).
    assert set(works[0].contributing_sources) == {
        "core", "semantic_scholar", "arxiv_bulk"
    }


def test_distinct_papers_do_not_collapse():
    """Two genuinely different DOIs stay two documents — collapse is keyed on
    real identity, not a generic title."""
    a = core_to_record(
        {"id": "a", "doi": "10.1/aaa", "title": "Study", "license": _CC_BY, "downloadUrl": "u"}
    )
    b = core_to_record(
        {"id": "b", "doi": "10.1/bbb", "title": "Study", "license": _CC_BY, "downloadUrl": "u"}
    )
    result = dedup_candidates([paper_candidate_ref(a), paper_candidate_ref(b)])
    assert len(result.kept) == 2
