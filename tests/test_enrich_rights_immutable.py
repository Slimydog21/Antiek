"""SPR-03 M3 — the LOAD-BEARING rights-immutability guard.

The hard rule of this sprint: OpenAlex may ENRICH an arXiv record but must NEVER
change ``license_uri`` or the rights tier. S2 / OpenAlex omit arXiv's
``<license>`` element; letting them touch rights would mis-grant. This test
proves the invariant DIRECTLY: snapshot the rights-bearing metadata BEFORE
enrichment, run a real (matched) enrichment through the DB path, then assert the
protected keys are BYTE-IDENTICAL after.

NO live HTTP: the OpenAlex fetch is exercised against a recorded ``/works``
response via ``httpx.MockTransport`` + a no-sleep throttle.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime

import duckdb
import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.adapter import arxiv_doc_id  # noqa: E402
from acquisition.arxiv.enrich_openalex import (  # noqa: E402
    PROTECTED_RIGHTS_KEYS,
    enrich_corpus,
    merge_enrichment,
)
from acquisition.arxiv.oai_persist import persist_oai_records  # noqa: E402
from acquisition.openaccess.throttle import OAThrottle  # noqa: E402
from substrate.schemas.documents import ArxivOaiRecord  # noqa: E402


def _no_sleep_throttle() -> OAThrottle:
    return OAThrottle(min_spacing_s=0.0, sleep=lambda _s: None)


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


# A work that, if its license were ever allowed to touch the row, would CHANGE
# the rights decision: OpenAlex says cc-by here, but the seeded arXiv row is the
# arXiv DEFAULT-terms license (gated). The enrichment must NOT promote it.
_ARXIV_ID = "2402.03300"
_ARXIV_DEFAULT_LICENSE = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"

_OPENALEX_CC_BY_WORK = {
    "results": [
        {
            "id": "https://openalex.org/W4392000001",
            "doi": "https://doi.org/10.48550/arxiv.2402.03300",
            "title": "Sample Paper About Decomposition",
            "cited_by_count": 7,
            # OpenAlex's (different!) view of the license — must be IGNORED for
            # rights. It would mis-grant the gated paper as servable-open.
            "best_oa_location": {"is_oa": True, "license": "cc-by"},
            "authorships": [
                {
                    "author_position": "first",
                    "author": {"display_name": "Jane Doe", "orcid": None},
                }
            ],
            "referenced_works": ["https://openalex.org/W1000"],
        }
    ]
}


@pytest.fixture
def temp_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-enrich-rights-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "tmpdir": tmpdir}


def _read_metadata(db_path: str, document_id: str) -> dict:
    con = duckdb.connect(db_path)
    try:
        (raw,) = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?", [document_id]
        ).fetchone()
    finally:
        con.close()
    return json.loads(raw) if isinstance(raw, str) else raw


def _seed(db_path: str, license_uri: str):
    rec = ArxivOaiRecord(
        arxiv_id=_ARXIV_ID,
        datestamp="2024-02-05",
        license_uri=license_uri,
        title="Sample Paper About Decomposition",
        categories=("cs.AI",),
    )
    persist_oai_records([rec], db_path=db_path)


# ---------------------------------------------------------------------------
# The load-bearing test: license_uri + rights_tier byte-identical pre/post.
# ---------------------------------------------------------------------------


def test_enrichment_does_not_change_license_or_tier(temp_db):
    db_path = temp_db["db_path"]
    _seed(db_path, _ARXIV_DEFAULT_LICENSE)  # gated arXiv-default license
    doc_id = arxiv_doc_id(_ARXIV_ID)

    # SNAPSHOT the rights-bearing metadata BEFORE enrichment.
    pre = _read_metadata(db_path, doc_id)
    pre_rights = {k: pre.get(k) for k in PROTECTED_RIGHTS_KEYS}
    assert pre_rights["license_uri"] == _ARXIV_DEFAULT_LICENSE
    assert pre_rights["rights_tier"] == "T3"  # arXiv-default -> gated floor

    # ENRICH (a real match; OpenAlex says cc-by — the trap).
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OPENALEX_CC_BY_WORK)

    cov = enrich_corpus(
        db_path=db_path, client=_mock_client(handler), throttle=_no_sleep_throttle(),
        fetched_at=datetime(2026, 5, 30, tzinfo=UTC),
    )
    assert cov.matched == 1  # the enrichment genuinely ran (not a no-op)

    # ASSERT byte-identical rights AFTER.
    post = _read_metadata(db_path, doc_id)
    post_rights = {k: post.get(k) for k in PROTECTED_RIGHTS_KEYS}
    assert post_rights == pre_rights
    # Specifically: license_uri AND tier unchanged despite OpenAlex's cc-by view.
    assert post["license_uri"] == _ARXIV_DEFAULT_LICENSE
    assert post["rights_tier"] == "T3"
    # And the enrichment DID land (additive), so this isn't passing by no-op.
    # The enrichment payload carries citation/author data only — NOT a license
    # field; OpenAlex's cc-by view was never copied anywhere onto the row.
    assert post["openalex_enrichment"]["source"] == "openalex"
    assert post["openalex_enrichment"]["cited_by_count"] == 7
    assert "license" not in post["openalex_enrichment"]
    assert "license_uri" not in post["openalex_enrichment"]


def test_enrichment_preserves_a_servable_license_too(temp_db):
    """Symmetry: a genuinely-open (CC-BY) arXiv row keeps its T1 tier; enrichment
    never DOWNGRADES rights either."""
    db_path = temp_db["db_path"]
    cc_by = "http://creativecommons.org/licenses/by/4.0/"
    _seed(db_path, cc_by)
    doc_id = arxiv_doc_id(_ARXIV_ID)

    pre = _read_metadata(db_path, doc_id)
    assert pre["license_uri"] == cc_by
    assert pre["rights_tier"] == "T1"

    def handler(req: httpx.Request) -> httpx.Response:
        # OpenAlex returns a work with NO license field at all.
        work = dict(_OPENALEX_CC_BY_WORK["results"][0])
        work["best_oa_location"] = {"is_oa": True, "license": None}
        return httpx.Response(200, json={"results": [work]})

    enrich_corpus(
        db_path=db_path, client=_mock_client(handler), throttle=_no_sleep_throttle(),
    )

    post = _read_metadata(db_path, doc_id)
    assert post["license_uri"] == cc_by          # unchanged
    assert post["rights_tier"] == "T1"           # NOT downgraded by OpenAlex's None
    assert "openalex_enrichment" in post


def test_merge_enrichment_rejects_a_rights_mutation():
    """Unit-level guard: ``merge_enrichment`` raises if its result ever differs
    from the input on a protected key (defends a future regression in the merge)."""
    existing = {
        "license_uri": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
        "rights_tier": "T3",
        "license_basis": "arXiv default terms — gated",
        "license_content_class": "restricted_pending_opt_in",
    }
    merged = merge_enrichment(existing, {"source": "openalex", "cited_by_count": 1})
    for key in PROTECTED_RIGHTS_KEYS:
        assert merged[key] == existing[key]
