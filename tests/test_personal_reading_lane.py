"""Personal-Reading Lane SPR-01 — the personal_reading content_class + serve gate.

These tests verify the two-sided gate the sprint creates:

  WRITE SIDE (deny-by-default): a third-party document_type ingested with no
  content_class lands ``personal_reading`` (never NULL-that-serves), and emits
  exactly one ``document.content_class_defaulted`` event. A genuine upload
  (book / paper) with no class stays NULL. An explicit class always wins.

  READ SIDE (allowlist): a ``personal_reading`` chunk is EXCLUDED from the
  public chunk-search gate on a default policy_tag and INCLUDED on the
  privileged owner path; ``serve_full_text`` returns ``servable=False`` for it
  on the public path and the full body only on the explicit ``owner=True``
  path; ``curate_reading_list`` omits it; it is non-attributable, absent from
  the public graph, non-trainable, and projects to ``PERSONAL_READABLE``.

All against a temp DuckDB with a deterministic stub embedding — no live
network, no prod DB.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.constants import (
    NON_TRAINABLE_CONTENT_CLASSES,
    PERSONAL_READABLE_CONTENT_CLASSES,
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
    THIRD_PARTY_DOCUMENT_TYPES,
)
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database
from substrate.graph.search import (
    PERSONAL_ONLY_CONTENT_CLASSES,
    PRIVILEGED_CALLER_TOKEN,
    RESTRICTED_CONTENT_CLASSES,
    search,
)


class StubEmbedding:
    """Deterministic length-4 embedding (no sentence-transformers)."""

    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0,
            float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0,
            float((h >> 7) % 17) / 17.0,
        ]


@pytest.fixture
def env(monkeypatch):
    """Temp DuckDB + a temp events dir routed via the env var the event log
    reads, so emitted events land where the test can read them."""
    tmp = tempfile.mkdtemp(prefix="antiek-pr-lane-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    con = connect_write(db_path, purpose="pr-lane-setup")
    init_database(con)
    con.close()
    return {"db_path": db_path, "events_dir": events_dir}


def _content_class_of(db_path: str, document_id: str):
    con = connect_write(db_path, purpose="read-class")
    try:
        row = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def _defaulted_events(events_dir: str) -> list[dict]:
    """All document.content_class_defaulted events across the events dir."""
    from substrate.event_log.events import trajectory

    out: list[dict] = []
    if not os.path.isdir(events_dir):
        return out
    for fn in os.listdir(events_dir):
        if not (fn.endswith(".jsonl") or fn.endswith(".parquet")):
            continue
        iid = fn.rsplit(".", 1)[0]
        for ev in trajectory(iid, events_dir=events_dir):
            if ev.get("action_type") == "document.content_class_defaulted":
                out.append(ev)
    return out


# ---------------------------------------------------------------------------
# M1 / M4 — constants
# ---------------------------------------------------------------------------


def test_constants_personal_reading_not_servable():
    assert PERSONAL_READING_CONTENT_CLASS == "personal_reading"
    assert PERSONAL_READING_CONTENT_CLASS not in SERVABLE_CONTENT_CLASSES
    # strict superset by exactly one element
    assert PERSONAL_READABLE_CONTENT_CLASSES == (
        SERVABLE_CONTENT_CLASSES | {PERSONAL_READING_CONTENT_CLASS}
    )
    assert len(PERSONAL_READABLE_CONTENT_CLASSES) == len(SERVABLE_CONTENT_CLASSES) + 1


def test_constants_third_party_document_types_exact():
    assert THIRD_PARTY_DOCUMENT_TYPES == frozenset(
        {"web_article", "video_transcript", "social_thread", "newsletter_post"}
    )


def test_non_trainable_denylist_members():
    assert "personal_reading" in NON_TRAINABLE_CONTENT_CLASSES
    assert "restricted_pending_opt_in" in NON_TRAINABLE_CONTENT_CLASSES


# ---------------------------------------------------------------------------
# M2 — non-attribution + absent from the public graph (read-side proof)
# ---------------------------------------------------------------------------


def test_personal_reading_is_non_attributable():
    from substrate.collective_graph.eligibility import (
        NON_ATTRIBUTABLE_CONTENT_CLASSES,
        CollectiveGraphDocument,
        is_attribution_eligible,
    )

    assert "personal_reading" in NON_ATTRIBUTABLE_CONTENT_CLASSES
    doc = CollectiveGraphDocument(
        document_id="d1",
        note_id="n1",
        owner_user_id="u1",
        content_class="personal_reading",
        quality_gate_result=None,
    )
    assert is_attribution_eligible(doc) is False


def test_personal_reading_absent_from_public_graph_and_not_monetizable():
    from substrate.ad_inventory.attribution import (
        PUBLIC_GRAPH_CONTENT_CLASSES,
        eligibility_decision,
        monetization_eligible,
    )

    assert "personal_reading" not in PUBLIC_GRAPH_CONTENT_CLASSES
    assert monetization_eligible("personal_reading") is False
    # falls through to the deny-by-default branch
    assert eligibility_decision("personal_reading").eligible is False


def test_personal_reading_accrues_zero_attribution_share():
    """A personal_reading document is dropped from any attribution split — it
    earns nothing by construction (the money-path proof for M2)."""
    from substrate.ad_inventory.attribution import eligible_shares

    shares = {"doc-pr": 0.6, "doc-pd": 0.4}
    classes = {"doc-pr": "personal_reading", "doc-pd": "public_domain"}
    kept = eligible_shares(shares, classes)
    assert "doc-pr" not in kept
    # the eligible survivor renormalizes to the whole pool
    assert kept == {"doc-pd": 1.0}


# ---------------------------------------------------------------------------
# M3 — owner vs public read split (search gate)
# ---------------------------------------------------------------------------


def _seed_chunk(db_path: str, document_id: str, content_class, text: str):
    con = connect_write(db_path, purpose="seed-chunk")
    try:
        # explicit content_class so the third-party guard does not fire here —
        # we are seeding read-side fixtures, not exercising the write guard.
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="paper",
            title=f"Title {document_id}",
            content_class=content_class,
        )
        insert_chunk(
            con,
            document_id=document_id,
            chunk_index=0,
            text=text,
            token_count=10,
            embedding=StubEmbedding().encode(text),
        )
    finally:
        con.close()


def test_search_gate_excludes_personal_reading_on_default_policy(env):
    _seed_chunk(env["db_path"], "doc-pd", "public_domain", "quantum optics review")
    _seed_chunk(env["db_path"], "doc-pr", "personal_reading", "quantum optics review")
    con = connect_write(env["db_path"], purpose="search")
    try:
        res = search(con, "quantum", model=StubEmbedding(), top_k=10)
    finally:
        con.close()
    doc_ids = {r["document_id"] for r in res["results"]}
    assert "doc-pd" in doc_ids
    assert "doc-pr" not in doc_ids, "personal_reading leaked onto the public search gate"


def test_search_gate_includes_personal_reading_on_operator_only(env):
    _seed_chunk(env["db_path"], "doc-pr", "personal_reading", "quantum optics review")
    con = connect_write(env["db_path"], purpose="search")
    try:
        # operator_only is a privileged tag (the owner's full-read path). As of
        # SPR-03 a privileged tag is code-enforced: the caller MUST present
        # PRIVILEGED_CALLER_TOKEN, else search() raises PrivilegedPolicyTagError
        # (a money/ad-path caller cannot reach the bypass). The owner-read path
        # legitimately holds the token — same discipline as the grounder.
        res = search(
            con,
            "quantum",
            model=StubEmbedding(),
            top_k=10,
            policy_tag="operator_only",
            privileged_caller=PRIVILEGED_CALLER_TOKEN,
        )
    finally:
        con.close()
    doc_ids = {r["document_id"] for r in res["results"]}
    assert "doc-pr" in doc_ids, "owner operator_only path could not retrieve personal_reading"


def test_search_gate_personal_only_set_is_separate_from_restricted():
    """The two gate states are kept distinct (opposite economics)."""
    assert PERSONAL_ONLY_CONTENT_CLASSES == frozenset({"personal_reading"})
    assert RESTRICTED_CONTENT_CLASSES == frozenset({"restricted_pending_opt_in"})
    assert PERSONAL_ONLY_CONTENT_CLASSES.isdisjoint(RESTRICTED_CONTENT_CLASSES)


# ---------------------------------------------------------------------------
# M3 — owner vs public read split (serve gate)
# ---------------------------------------------------------------------------


def _seed_document(db_path: str, document_id: str, content_class, *, raw_text, document_type="web_article"):
    con = connect_write(db_path, purpose="seed-doc")
    try:
        insert_document(
            con,
            document_id=document_id,
            source_tier=3,
            document_type=document_type,
            title=f"Title {document_id}",
            raw_text=raw_text,
            content_class=content_class,
        )
    finally:
        con.close()


def test_serve_gate_public_path_does_not_serve_personal_reading(env):
    body = "A Paul Graham essay the owner saved for personal reading. " * 20
    _seed_document(env["db_path"], "doc-pr", "personal_reading", raw_text=body)
    from substrate.books.serve import serve_full_text

    con = connect_write(env["db_path"], purpose="serve")
    try:
        res = serve_full_text(con, "doc-pr")  # public path (owner defaults False)
    finally:
        con.close()
    assert res.servable is False
    assert res.full_text is None
    # the public path returns at most a bounded snippet, never the full body
    assert res.snippet is not None
    assert len(res.snippet) <= len(body)
    assert res.full_text != body


def test_serve_gate_owner_path_serves_full_personal_reading_body(env):
    body = "A Paul Graham essay the owner saved for personal reading. " * 20
    _seed_document(env["db_path"], "doc-pr", "personal_reading", raw_text=body)
    from substrate.books.serve import serve_full_text

    con = connect_write(env["db_path"], purpose="serve")
    try:
        res = serve_full_text(con, "doc-pr", owner=True)
    finally:
        con.close()
    # owner reads the full body…
    assert res.full_text == body
    # …but it is STILL not publicly servable / ad-eligible
    assert res.servable is False
    assert res.reason == "owner_personal_reading"


def test_serve_gate_owner_param_does_not_widen_servable_classes(env):
    """owner=True must not change the answer for a gated (non-personal) doc."""
    body = "gated copyrighted body " * 50
    _seed_document(
        env["db_path"], "doc-gated", "restricted_pending_opt_in", raw_text=body
    )
    from substrate.books.serve import serve_full_text

    con = connect_write(env["db_path"], purpose="serve")
    try:
        public = serve_full_text(con, "doc-gated")
        owner = serve_full_text(con, "doc-gated", owner=True)
    finally:
        con.close()
    assert public.servable is False and public.full_text is None
    # a gated book is NOT widened by the owner flag — only personal_reading is
    assert owner.servable is False and owner.full_text is None


# ---------------------------------------------------------------------------
# M3 — curate (public reading list) omits personal_reading
# ---------------------------------------------------------------------------


def test_curate_reading_list_omits_personal_reading(env):
    from substrate.books.curate import curate_reading_list

    db = env["db_path"]
    # one servable book and one personal_reading "book" (document_type=book so it
    # is curate-eligible by type; the content_class allowlist is what must reject it)
    for doc_id, cc in (("book-pd", "public_domain"), ("book-pr", "personal_reading")):
        con = connect_write(db, purpose="seed-book")
        try:
            text = "stoic philosophy on resilience and calm"
            insert_document(
                con,
                document_id=doc_id,
                source_tier=2,
                document_type="book",
                title=doc_id.upper(),
                raw_text=text,
                content_class=cc,
            )
            insert_chunk(
                con,
                document_id=doc_id,
                chunk_index=0,
                text=text,
                token_count=6,
                embedding=StubEmbedding().encode(text),
            )
            con.execute(
                "INSERT INTO book_assets (document_id, taken_down) VALUES (?, FALSE)",
                [doc_id],
            )
        finally:
            con.close()

    con = connect_write(db, purpose="curate")
    try:
        results = curate_reading_list(con, "stoic resilience", model=StubEmbedding(), limit=10)
    finally:
        con.close()
    ids = {r.document_id for r in results}
    assert "book-pd" in ids
    assert "book-pr" not in ids, "personal_reading leaked into the public reading list"


# ---------------------------------------------------------------------------
# M5 — deny-by-default guard in insert_document
# ---------------------------------------------------------------------------


def test_insert_document_deny_default_third_party_lands_personal_reading(env):
    con = connect_write(env["db_path"], purpose="ingest")
    try:
        insert_document(
            con,
            document_id="web-1",
            source_tier=3,
            document_type="web_article",
            title="An essay",
            raw_text="the body",
            # content_class deliberately omitted (None)
        )
    finally:
        con.close()
    assert _content_class_of(env["db_path"], "web-1") == "personal_reading"
    events = _defaulted_events(env["events_dir"])
    matching = [e for e in events if e.get("document_id") == "web-1"]
    assert len(matching) == 1, f"expected exactly one defaulting event, got {len(matching)}"
    payload = matching[0].get("payload") or {}
    assert payload.get("document_type") == "web_article"
    assert payload.get("applied_content_class") == "personal_reading"
    # §9.0 — the event carries NO body
    assert "raw_text" not in payload
    assert "the body" not in str(matching[0])


def test_insert_document_deny_default_covers_all_third_party_types(env):
    for i, dtype in enumerate(sorted(THIRD_PARTY_DOCUMENT_TYPES)):
        doc_id = f"tp-{i}"
        con = connect_write(env["db_path"], purpose="ingest")
        try:
            insert_document(
                con,
                document_id=doc_id,
                source_tier=3,
                document_type=dtype,
                title=doc_id,
            )
        finally:
            con.close()
        assert _content_class_of(env["db_path"], doc_id) == "personal_reading", dtype


def test_explicit_content_class_beats_default(env):
    con = connect_write(env["db_path"], purpose="ingest")
    try:
        insert_document(
            con,
            document_id="web-pd",
            source_tier=3,
            document_type="web_article",
            title="An openly licensed essay",
            content_class="public_domain",
        )
    finally:
        con.close()
    assert _content_class_of(env["db_path"], "web-pd") == "public_domain"
    # explicit class → no defaulting event
    matching = [e for e in _defaulted_events(env["events_dir"]) if e.get("document_id") == "web-pd"]
    assert matching == []


def test_non_third_party_with_none_stays_null(env):
    con = connect_write(env["db_path"], purpose="ingest")
    try:
        insert_document(
            con,
            document_id="book-legacy",
            source_tier=2,
            document_type="book",
            title="A genuine upload",
            # content_class None — a real upload keeps today's NULL behaviour
        )
    finally:
        con.close()
    assert _content_class_of(env["db_path"], "book-legacy") is None
    matching = [
        e for e in _defaulted_events(env["events_dir"]) if e.get("document_id") == "book-legacy"
    ]
    assert matching == [], "a non-third-party upload must not emit a defaulting event"


def test_on_conflict_ignore_does_not_re_emit_defaulting_event(env):
    """The on_conflict='ignore' early-return short-circuits BEFORE the guard, so
    re-inserting an existing third-party row never re-emits the event."""
    for _ in range(2):
        con = connect_write(env["db_path"], purpose="ingest")
        try:
            insert_document(
                con,
                document_id="web-dup",
                source_tier=3,
                document_type="web_article",
                title="An essay",
                on_conflict="ignore",
            )
        finally:
            con.close()
    assert _content_class_of(env["db_path"], "web-dup") == "personal_reading"
    matching = [
        e for e in _defaulted_events(env["events_dir"]) if e.get("document_id") == "web-dup"
    ]
    assert len(matching) == 1, f"re-insert re-emitted the defaulting event: {len(matching)}"


# ---------------------------------------------------------------------------
# M6 — servability projection
# ---------------------------------------------------------------------------


def test_servability_projection_personal_readable():
    from substrate.books.servability import (
        ServabilityStatus,
        is_servable_full_text,
        servability_of,
    )

    st = servability_of("personal_reading", taken_down=False)
    assert st is ServabilityStatus.PERSONAL_READABLE
    assert is_servable_full_text(st) is False


def test_servability_taken_down_personal_reading_is_taken_down():
    from substrate.books.servability import ServabilityStatus, servability_of

    st = servability_of("personal_reading", taken_down=True)
    assert st is ServabilityStatus.TAKEN_DOWN


def test_servability_drift_assertion_still_holds():
    """The import-time drift assertion (_PROJECTED_SERVABLE ==
    SERVABLE_CONTENT_CLASSES) must remain intact: personal_reading is NOT mapped
    through _CONTENT_CLASS_TO_STATUS to a servable status, so the projection set
    is unchanged. Re-import the module in a fresh subprocess so we don't mutate
    the shared module's enum identity (which an in-process importlib.reload would
    do, breaking other tests' `is` comparisons)."""
    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import substrate.books.servability as s; "
                "assert s.ServabilityStatus.PERSONAL_READABLE.value == 'personal_readable'; "
                "print('ok')"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


# ---------------------------------------------------------------------------
# M2 defense-in-depth — the live attribution-compute surface
# (substrate/attribution/compute.py, /attribution/synthesis/{id}) must drop a
# personal_reading document a synthesis happened to cite, exactly as it already
# drops restricted_pending_opt_in. This endpoint resolves WHATEVER chunks a
# synthesis cited (a synthesis built on a privileged owner path could have
# included personal_reading), so the gate that gives personal_reading zero ad
# attribution must hold HERE too, not only on the upstream search gate. This
# test BITES on the pre-sharpen RESTRICTED-only filter: against it, the
# personal_reading doc would receive a non-zero share + title.
# ---------------------------------------------------------------------------


def _seed_synthesis_citing(db_path: str, chunk_specs: list[tuple[str, str, str]]):
    """chunk_specs: list of (document_id, content_class, text). Seeds one
    document + one chunk per spec and a synthesis whose single thesis_component
    cites every chunk. Returns the synthesis_id."""
    import json

    con = connect_write(db_path, purpose="seed-syn")
    try:
        chunk_ids: list[str] = []
        for document_id, content_class, text in chunk_specs:
            insert_document(
                con,
                document_id=document_id,
                source_tier=2,
                document_type="paper",
                title=f"Title {document_id}",
                content_class=content_class,
            )
            cid = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=0,
                text=text,
                token_count=10,
                embedding=StubEmbedding().encode(text),
            )
            chunk_ids.append(cid)
        thesis = {
            "thesis_components": [
                {"claim": "C1", "confidence": "high", "supporting_chunk_ids": chunk_ids},
            ],
        }
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, target_question, "
            "synthesis_timestamp, status, implicit_recommendation, thesis, thesis_token_count) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, 0)",
            ["syn-pr", "inv-1", "Q?", "passed", "proceed", json.dumps(thesis)],
        )
    finally:
        con.close()
    return "syn-pr"


def test_attribution_compute_drops_personal_reading_doc(env, monkeypatch):
    from substrate.attribution.compute import compute_attribution_for_synthesis

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", env["db_path"])
    _seed_synthesis_citing(
        env["db_path"],
        [
            # DISTINCT text per chunk so insert_chunk derives distinct chunk_ids
            # (it hashes the body) — identical text would collide both chunks
            # onto one document and the test would no longer discriminate.
            ("doc-public", "public_domain", "public servable retrieval text"),
            ("doc-personal", "personal_reading", "owner-private third-party text"),
        ],
    )
    r = compute_attribution_for_synthesis("syn-pr", db_path=env["db_path"])
    for opt in (r.option_a, r.option_b, r.option_c):
        # personal_reading must be gone — not down-weighted, not titled.
        assert "doc-personal" not in opt.shares, opt.algorithm
        assert "doc-personal" not in opt.document_titles, opt.algorithm
        assert "Title doc-personal" not in opt.document_titles.values(), opt.algorithm
        assert "doc-personal" not in opt.document_ip_holders, opt.algorithm
    # The servable public document carries the FULL attribution — the
    # personal_reading source is excluded entirely, not merely reduced.
    assert r.option_b.shares == pytest.approx({"doc-public": 1.0})


def test_attribution_compute_still_drops_restricted_doc(env, monkeypatch):
    """Regression anchor — extending the filter to the excluded-union must NOT
    regress the restricted_pending_opt_in exclusion the union also contains."""
    from substrate.attribution.compute import compute_attribution_for_synthesis

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", env["db_path"])
    _seed_synthesis_citing(
        env["db_path"],
        [
            ("doc-public", "public_domain", "public servable retrieval text"),
            ("doc-restricted", "restricted_pending_opt_in", "gated restricted body text"),
        ],
    )
    r = compute_attribution_for_synthesis("syn-pr", db_path=env["db_path"])
    for opt in (r.option_a, r.option_b, r.option_c):
        assert "doc-restricted" not in opt.shares, opt.algorithm
        assert "doc-restricted" not in opt.document_titles, opt.algorithm
    assert r.option_b.shares == pytest.approx({"doc-public": 1.0})
