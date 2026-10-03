"""Reformat pipeline + bite-provenance proofs (reformat-provenance SPR-01).

Real DuckDB fixtures, the deterministic fixture generator injected at the
documented seam (the daemon's SpawnFn precedent — the pipeline's MECHANICS
are what's proven; the real generator rides the one dispatch path, covered
by dispatch's own suites). The spec's seven proofs, including the review's
sharpen notes: the minimum verbatim-detection rate, pinned on the
operator's own acceptance prompt.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from runtime.db_lock import connect_read  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.feedback.domain import normalize_node_text  # noqa: E402
from substrate.graph.ops import insert_document  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402
from substrate.provenance.store import (  # noqa: E402
    ProvenanceStore,
    text_sha256,
)
from substrate.reformat.pipeline import (  # noqa: E402
    GeneratedBite,
    ReformatError,
    SourceBlock,
    reformat_document,
)

OWNER = "__operator__"

#: The operator's own acceptance prompt (the review's sharpen note — the
#: fixture is NAMED for it, not approximated).
ACCEPTANCE_PROMPT = "the 20-minute version, focused on the pricing chapters"

BODY = (
    "## Page 1\n\n"
    "The pricing argument opens here.\n\n"
    "A middle stretch of ordinary prose follows.\n\n"
    "## Page 2\n\n"
    "The pricing chapters conclude with a flourish."
)
# Chunks locate into the served body (the anchor-map's discipline).
CHUNKS = [
    ("c-1", "Page 1", "The pricing argument opens here.\n\nA middle stretch of ordinary prose follows."),
    ("c-2", "Page 2", "The pricing chapters conclude with a flourish."),
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "t.duckdb"
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events)}


def _seed_source(db: str, *, document_id: str = "doc-1", content_class: str = "public_domain") -> None:
    from runtime.db_lock import connect_write

    with connect_write(db, purpose="test/seed-reformat-source") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="The Pricing Book",
            raw_text=BODY,
            content_class=content_class,
            on_conflict="ignore",
        )
        for i, (chunk_id, section, text) in enumerate(CHUNKS):
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
                "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [chunk_id, document_id, i, section, text, len(text.split())],
            )


def _fixture_generator(
    prompt: str, blocks: list[SourceBlock], params: dict
) -> list[GeneratedBite]:
    """The deterministic fixture generator: one bite per class over the
    real blocks (verbatim = the block's EXACT text)."""
    return [
        GeneratedBite(
            text=blocks[0].text,
            contribution_class="author_verbatim",
            source_block_indices=(0,),
        ),
        GeneratedBite(
            text="pricing opens",
            contribution_class="llm_compressed",
            source_block_indices=(0,),
        ),
        GeneratedBite(
            text=blocks[2].text + " And what that means for the operator's margins.",
            contribution_class="llm_expanded",
            source_block_indices=(2,),
        ),
        GeneratedBite(
            text="The loop's diligence found the pricing power note.",
            contribution_class="research_supplemented",
            source_block_indices=(2,),
            investigation_id="inv-diligence-1",
        ),
    ]


def _seed_diligence_investigation(investigation_id: str = "inv-diligence-1") -> None:
    """Make the fixture generator's research claim TRUE: a genuine distilled
    product (one live insight node) for the investigation it cites, promoted
    through the real research path. A fixture that cites research without
    creating it is the exact defect the pipeline now reclassifies — the
    fixture must carry its evidence."""
    from substrate.graph.insight_question import promote_insight

    promote_insight(
        text="The loop's diligence found the pricing power note.",
        investigation_id=investigation_id,
        confidence="moderate",
        source_document_id="doc-1",
    )


def _source_body_hash(db: str, document_id: str = "doc-1") -> str:
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?", [document_id]
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    return hashlib.sha256(str(row[0]).encode()).hexdigest()


# ── Proof 1 (+ 7b: the acceptance prompt): every bite classed + traced ─────


def test_reformat_classes_and_traces_every_bite_source_byte_identical(env) -> None:
    _seed_source(env["db"])
    _seed_diligence_investigation()
    before = _source_body_hash(env["db"])

    result = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-1",
        prompt=ACCEPTANCE_PROMPT,
        mode="time_window",
        params={"model": "fixture-model"},
        generate_fn=_fixture_generator,
        events_dir=env["events"],
    )

    con = connect_read(env["db"])
    try:
        record = ProvenanceStore().get_generation(con, result.generation_id)
        assert record is not None
        assert record.prompt == ACCEPTANCE_PROMPT
        assert record.model == "fixture-model"
        assert record.source_document_id == "doc-1"
        assert record.derived_document_id == result.derived_document_id
        params = json.loads(record.params_json)
        assert params["mode"] == "time_window"

        bites = ProvenanceStore().bites_for_generation(con, result.generation_id)
    finally:
        con.close()

    assert [b.contribution_class for b in bites] == [
        "author_verbatim",
        "llm_compressed",
        "llm_expanded",
        "research_supplemented",
    ]
    assert [b.ordinal for b in bites] == [0, 1, 2, 3]
    # Every classed bite traced to its source spans (refs into the CORE doc).
    for b in bites:
        assert b.source_refs is not None
        for ref in b.source_refs:
            # corespan:{doc_id}:{chunk_id}:{start}:{end}
            parts = ref.split(":")
            assert parts[0] == "corespan"
            assert parts[2] in {"c-1", "c-2"}
            assert int(parts[4]) > int(parts[3])
    # The research-supplemented bite carries its investigation.
    assert bites[3].investigation_id == "inv-diligence-1"
    # The author-verbatim bite BYTE-VERIFIES (recomputed, not trusted).
    assert bites[0].source_span_sha256 == bites[0].derived_text_sha256
    assert bites[0].source_span_sha256 == text_sha256(
        normalize_node_text(CHUNKS[0][2].split("\n\n")[0])
    )
    # The source is byte-identical throughout.
    assert _source_body_hash(env["db"]) == before
    # And the derived document registered with its lineage.
    con = connect_read(env["db"])
    try:
        derived = con.execute(
            "SELECT content_class, metadata FROM documents WHERE document_id = ?",
            [result.derived_document_id],
        ).fetchone()
    finally:
        con.close()
    assert derived is not None
    assert derived[0] == "public_domain"  # the parent's posture, inherited
    metadata = json.loads(str(derived[1]))
    assert metadata["derived_from_document_id"] == "doc-1"
    assert metadata["provisional"] is True  # born provisional, never blessed


# ── Proof 2: a false verbatim claim is rejected and reclassed ──────────────


def test_a_false_verbatim_claim_is_reclassed_never_mislabeled(env) -> None:
    _seed_source(env["db"])

    def lying_generator(prompt, blocks, params):
        return [
            GeneratedBite(
                text="this is NOT the author's sentence",
                contribution_class="author_verbatim",
                source_block_indices=(0,),
            ),
            GeneratedBite(
                text=blocks[0].text,
                contribution_class="author_verbatim",
                source_block_indices=(0,),
            ),
        ]

    result = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-1",
        prompt="compress it",
        generate_fn=lying_generator,
        events_dir=env["events"],
    )
    assert result.reclassed_verbatim == 1
    assert result.contribution_classes == ["llm_compressed", "author_verbatim"]
    # The audit event landed (metadata-only, on the source's reading thread).
    rows = trajectory("read-doc-1", events_dir=env["events"])
    audits = [r for r in rows if r.get("action_type") == "reformat.verbatim_reclassified"]
    assert len(audits) == 1
    assert audits[0]["payload"]["reclassed"] == 1
    assert "text" not in json.dumps(audits[0]["payload"])


# ── Proof 3: the novelty ceiling ────────────────────────────────────────────


def test_past_the_novelty_ceiling_the_asset_reads_mostly_generated(env) -> None:
    _seed_source(env["db"])

    def novel_generator(prompt, blocks, params):
        return [
            GeneratedBite(
                text=blocks[0].text,
                contribution_class="author_verbatim",
                source_block_indices=(0,),
            ),
            *[
                GeneratedBite(
                    text=f"a genuinely novel connective thought {i}",
                    contribution_class="llm_expanded",
                    source_block_indices=None,  # the honest no-direct-source
                )
                for i in range(4)
            ],
        ]

    result = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-1",
        prompt="expand around the themes",
        mode="themes",
        generate_fn=novel_generator,
        events_dir=env["events"],
    )
    # 4 of 5 bites sourceless (80% > the 20% ceiling): the asset flips
    # honestly, the bites STAY (each honestly null-sourced), the audit fires.
    assert result.mostly_generated is True
    assert result.null_source_share == 0.8
    con = connect_read(env["db"])
    try:
        record = ProvenanceStore().get_generation(con, result.generation_id)
        assert record is not None and record.mostly_generated is True
        bites = ProvenanceStore().bites_for_generation(con, result.generation_id)
    finally:
        con.close()
    assert len(bites) == 5  # nothing hidden — the shape stays visible
    assert sum(1 for b in bites if b.source_refs is None) == 4
    rows = trajectory("read-doc-1", events_dir=env["events"])
    audits = [r for r in rows if r.get("action_type") == "reformat.novelty_ceiling"]
    assert len(audits) == 1
    assert audits[0]["payload"]["null_source_share"] == 0.8


# ── Proof 5: the rights inheritance ─────────────────────────────────────────


def test_a_withheld_sources_derived_asset_stays_owner_only(env) -> None:
    _seed_source(env["db"], document_id="doc-gated", content_class="personal_reading")
    _seed_diligence_investigation()
    result = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-gated",
        prompt="compress it",
        generate_fn=_fixture_generator,
        events_dir=env["events"],
    )
    con = connect_read(env["db"])
    try:
        row = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [result.derived_document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == "personal_reading"  # inherited — never laundered
    # The existing gates, exercised on the derived id: the PUBLIC serve path
    # withholds the derived body exactly as it does the source's.
    from substrate.books.serve_guard import serve_full_text_guarded

    con = connect_read(env["db"])
    try:
        public_serve = serve_full_text_guarded(con, result.derived_document_id, owner=False)
        owner_serve = serve_full_text_guarded(con, result.derived_document_id, owner=True)
    finally:
        con.close()
    assert public_serve.full_text is None  # the public gate withholds
    assert owner_serve.full_text is not None  # the owner lane reads


def test_a_taken_down_source_refuses_honestly(env) -> None:
    _seed_source(env["db"], document_id="doc-dead", content_class="personal_reading")
    if not _table_exists(env["db"], "book_assets"):
        pytest.skip("book_assets not on this schema")
    from runtime.db_lock import connect_write

    with connect_write(env["db"], purpose="test/takedown") as con:
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES ('doc-dead', TRUE) "
            "ON CONFLICT DO NOTHING"
        )
    with pytest.raises(ReformatError):
        reformat_document(
            env["db"],
            owner_user_id=OWNER,
            source_document_id="doc-dead",
            prompt="compress it",
            generate_fn=_fixture_generator,
            events_dir=env["events"],
        )


def _table_exists(db: str, name: str) -> bool:
    con = connect_read(db)
    try:
        return (
            con.execute(
                "SELECT 1 FROM duckdb_tables() WHERE table_name = ? LIMIT 1", [name]
            ).fetchone()
            is not None
        )
    finally:
        con.close()


# ── Proof 6: regeneration stability ─────────────────────────────────────────


def test_regeneration_reproduces_ordinals_and_classes_as_a_NEW_generation(env) -> None:
    _seed_source(env["db"])
    _seed_diligence_investigation()
    first = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-1",
        prompt=ACCEPTANCE_PROMPT,
        mode="time_window",
        params={"model": "fixture-model"},
        generate_fn=_fixture_generator,
        events_dir=env["events"],
    )
    second = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-1",
        prompt=ACCEPTANCE_PROMPT,
        mode="time_window",
        params={"model": "fixture-model"},
        generate_fn=_fixture_generator,
        events_dir=env["events"],
    )
    # Two lawful generations — never an in-place overwrite.
    assert first.generation_id != second.generation_id
    assert first.derived_document_id != second.derived_document_id
    assert first.contribution_classes == second.contribution_classes
    con = connect_read(env["db"])
    try:
        b1 = ProvenanceStore().bites_for_generation(con, first.generation_id)
        b2 = ProvenanceStore().bites_for_generation(con, second.generation_id)
    finally:
        con.close()
    assert [b.ordinal for b in b1] == [b.ordinal for b in b2]
    assert [b.derived_text_sha256 for b in b1] == [b.derived_text_sha256 for b in b2]
    assert [b.source_refs for b in b1] == [b.source_refs for b in b2]


# ── Proof 7 (the sharpen note): the MINIMUM verbatim-detection rate ─────────


def test_verbatim_detection_rate_pinned_on_the_acceptance_fixture(env) -> None:
    """A pipeline that mis-classes is worse than none. On the acceptance
    fixture (the operator's named prompt): PRECISION is 1.0 by construction
    (no bite is author_verbatim unless byte-verified); RECALL is pinned —
    every truly-verbatim bite the generator emits is classed author_verbatim."""
    _seed_source(env["db"])

    def generator(prompt, blocks, params):
        return [
            GeneratedBite(
                text=blocks[0].text,
                contribution_class="author_verbatim",
                source_block_indices=(0,),
            ),
            GeneratedBite(
                text=blocks[1].text,
                contribution_class="author_verbatim",
                source_block_indices=(1,),
            ),
            GeneratedBite(
                text=blocks[2].text,
                contribution_class="author_verbatim",
                source_block_indices=(2,),
            ),
            GeneratedBite(
                text="a compressed note on pricing",
                contribution_class="llm_compressed",
                source_block_indices=(0, 2),
            ),
        ]

    result = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-1",
        prompt=ACCEPTANCE_PROMPT,
        mode="time_window",
        generate_fn=generator,
        events_dir=env["events"],
    )
    con = connect_read(env["db"])
    try:
        bites = ProvenanceStore().bites_for_generation(con, result.generation_id)
    finally:
        con.close()
    verbatim = [b for b in bites if b.contribution_class == "author_verbatim"]
    truly_verbatim = 3  # the generator emitted three byte-exact bites
    # Precision: every verbatim-classed bite byte-verifies (recomputed).
    assert all(b.derived_text_sha256 == b.source_span_sha256 for b in verbatim)
    # Recall: all three truly-verbatim bites detected (the pinned floor).
    assert len(verbatim) / truly_verbatim >= 0.95
    assert result.reclassed_verbatim == 0


# ── Review hardening (2026-09-25): block offsets must be exact for ANY
# paragraph-separator run, and the derived document must carry the caller's
# ownership (the generation's owner and the asset's owner cannot disagree). ──


def test_source_block_spans_are_exact_across_long_newline_runs(env) -> None:
    from runtime.db_lock import connect_write
    from substrate.reformat.pipeline import _source_blocks

    body = "Para one before the gap.\n\n\n\nPara two after the drift."
    with connect_write(env["db"], purpose="test/seed-drift") as con:
        insert_document(
            con,
            document_id="doc-drift",
            source_tier=2,
            document_type="book",
            title="Drift",
            raw_text=body,
            content_class="public_domain",
            on_conflict="ignore",
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
            "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
            ["c-1-doc-drift", "doc-drift", 0, "Page 1", body, len(body.split())],
        )
    con = connect_read(env["db"])
    try:
        blocks = _source_blocks(con, "doc-drift", body)
    finally:
        con.close()
    assert [b.text for b in blocks] == [
        "Para one before the gap.",
        "Para two after the drift.",
    ]
    normalized = normalize_node_text(body)
    for block in blocks:
        sliced = normalized[block.start_scalar : block.end_scalar]
        assert sliced == block.text, (
            f"span {(block.start_scalar, block.end_scalar)} sliced {sliced!r}"
        )


def test_derived_document_carries_the_callers_ownership(env) -> None:
    _seed_source(env["db"])
    _seed_diligence_investigation()
    result = reformat_document(
        env["db"],
        owner_user_id="owner-x",
        source_document_id="doc-1",
        prompt=ACCEPTANCE_PROMPT,
        generate_fn=_fixture_generator,
        events_dir=env["events"],
    )
    con = connect_read(env["db"])
    try:
        doc_owner, gen_owner = con.execute(
            "SELECT d.owner_user_id, g.owner_user_id FROM documents d "
            "JOIN generation_records g ON g.derived_document_id = d.document_id "
            "WHERE d.document_id = ?",
            [result.derived_document_id],
        ).fetchone()
    finally:
        con.close()
    assert (doc_owner, gen_owner) == ("owner-x", "owner-x")


def test_derived_id_collision_refuses_and_attaches_nothing(env, monkeypatch) -> None:
    """Grok counter-review probe (2026-09-25): a pre-existing derived id
    owned by ANOTHER owner must abort the whole write scope — never attach
    chunks or a generation record to the foreign document."""
    import substrate.reformat.pipeline as pipeline_mod

    monkeypatch.setattr(
        pipeline_mod, "mint_generation_id", lambda: "gen-deadbeefdeadbeef"
    )
    _seed_source(env["db"])
    with __import__("runtime.db_lock", fromlist=["connect_write"]).connect_write(
        env["db"], purpose="test/seed-collision"
    ) as con:
        insert_document(
            con,
            document_id="drv-deadbeefdeadbeef",
            source_tier=1,
            document_type="derived",
            title="Pre-existing foreign derived doc",
            raw_text="original foreign body",
            content_class="personal_reading",
            owner_user_id="owner-b",
            on_conflict="ignore",
        )
    with pytest.raises(ReformatError, match="derived document id collision"):
        reformat_document(
            env["db"],
            owner_user_id="owner-a",
            source_document_id="doc-1",
            prompt=ACCEPTANCE_PROMPT,
            generate_fn=_fixture_generator,
            events_dir=env["events"],
        )
    con = connect_read(env["db"])
    try:
        doc_row = con.execute(
            "SELECT owner_user_id, raw_text FROM documents "
            "WHERE document_id = 'drv-deadbeefdeadbeef'"
        ).fetchone()
        chunk_count = con.execute(
            "SELECT count(*) FROM chunks WHERE document_id = 'drv-deadbeefdeadbeef'"
        ).fetchone()[0]
        from substrate.provenance.schema import provenance_tables_exist

        # The aborted write scope never even created the provenance tables
        # (their DDL lands with the first record) — absence is the proof.
        gen_count = (
            0
            if not provenance_tables_exist(con)
            else con.execute(
                "SELECT count(*) FROM generation_records "
                "WHERE generation_id = 'gen-deadbeefdeadbeef' "
                "OR derived_document_id = 'drv-deadbeefdeadbeef'"
            ).fetchone()[0]
        )
    finally:
        con.close()
    assert doc_row == ("owner-b", "original foreign body")
    assert chunk_count == 0
    assert gen_count == 0


# ── R6 boundary repair (2026-10-02): the research-supplement claim is
# verified against the investigation's DISTILLED PRODUCT (the distill API's
# own read seam), never trusted by declaration — the same
# reclassify-with-evidence pattern as author_verbatim, one class over. ──────


def test_a_false_research_claim_is_reclassed_never_mislabeled(env) -> None:
    """Mirror of the verbatim proof: a research_supplemented bite whose
    investigation has NO distilled product in this substrate reclasses to
    llm_expanded, the id is nulled (the schema CHECK ties id to class), and
    the audit event fires — metadata only, never bite text."""
    _seed_source(env["db"])

    def lying_generator(prompt, blocks, params):
        return [
            GeneratedBite(
                text="Invented research supplementation.",
                contribution_class="research_supplemented",
                source_block_indices=(0,),
                investigation_id="inv-never-created",
            ),
        ]

    result = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-1",
        prompt="compress it",
        generate_fn=lying_generator,
        events_dir=env["events"],
    )
    assert result.reclassed_research == 1
    assert result.contribution_classes == ["llm_expanded"]
    con = connect_read(env["db"])
    try:
        bites = ProvenanceStore().bites_for_generation(con, result.generation_id)
    finally:
        con.close()
    assert bites[0].contribution_class == "llm_expanded"
    assert bites[0].investigation_id is None  # nulled with the class
    rows = trajectory("read-doc-1", events_dir=env["events"])
    audits = [
        r for r in rows if r.get("action_type") == "reformat.research_reclassified"
    ]
    assert len(audits) == 1
    assert audits[0]["payload"]["reclassed"] == 1
    assert audits[0]["payload"]["investigation_ids"] == ["inv-never-created"]
    assert "Invented research supplementation" not in json.dumps(audits[0]["payload"])


def test_a_genuine_research_claim_keeps_its_class_and_id(env) -> None:
    """THE NEGATIVE CONTROL: a research_supplemented bite whose investigation
    has a real distilled product (promoted through the real research path)
    is accepted with its class AND id intact — the gate is not stricter than
    the truth."""
    _seed_source(env["db"])
    _seed_diligence_investigation()

    def honest_generator(prompt, blocks, params):
        return [
            GeneratedBite(
                text="The diligence found the pricing power note.",
                contribution_class="research_supplemented",
                source_block_indices=(2,),
                investigation_id="inv-diligence-1",
            ),
        ]

    result = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-1",
        prompt="weave in the diligence",
        generate_fn=honest_generator,
        events_dir=env["events"],
    )
    assert result.reclassed_research == 0
    assert result.contribution_classes == ["research_supplemented"]
    con = connect_read(env["db"])
    try:
        bites = ProvenanceStore().bites_for_generation(con, result.generation_id)
    finally:
        con.close()
    assert bites[0].contribution_class == "research_supplemented"
    assert bites[0].investigation_id == "inv-diligence-1"
    rows = trajectory("read-doc-1", events_dir=env["events"])
    assert not [
        r for r in rows if r.get("action_type") == "reformat.research_reclassified"
    ]


def test_a_research_claim_without_an_id_still_refuses(env) -> None:
    """The pre-existing half of the contract holds: no investigation id at
    all is a refusal, not a reclass (there is nothing to verify against)."""
    _seed_source(env["db"])

    def idless_generator(prompt, blocks, params):
        return [
            GeneratedBite(
                text="claims research, names none",
                contribution_class="research_supplemented",
                source_block_indices=(0,),
                investigation_id=None,
            ),
        ]

    with pytest.raises(ReformatError, match="no investigation id"):
        reformat_document(
            env["db"],
            owner_user_id=OWNER,
            source_document_id="doc-1",
            prompt="compress it",
            generate_fn=idless_generator,
            events_dir=env["events"],
        )


# ── R6 boundary repair (2026-10-02): the generation record names the
# RESPONDER (dispatch's route receipt), not the requested string. ───────────


class _FixtureProvider:
    """A provider double on the router's public seam (register_provider —
    the same pattern as tests/test_dispatch.py): OpenAI-shaped usage, strict
    JSON body, no network."""

    name = "zai"  # the shipped flash tier's primary (config.yaml)

    def call(self, *, model, prompt, max_tokens, temperature):
        from substrate.dispatch.base import RawProviderResponse

        return RawProviderResponse(
            text=(
                '[{"text": "pricing, compressed", '
                '"contribution_class": "llm_compressed", '
                '"source_block_indices": [0], "investigation_id": null}]'
            ),
            raw_usage={"prompt_tokens": 12, "completion_tokens": 6},
            finish_reason="stop",
            latency_ms=4,
        )

    def normalize_usage(self, raw_usage):
        from substrate.dispatch.base import NormalizedUsage

        return NormalizedUsage(
            input_tokens=int(raw_usage.get("prompt_tokens", 0)),
            output_tokens=int(raw_usage.get("completion_tokens", 0)),
        )


def test_the_generation_record_names_the_responder_not_the_request(env) -> None:
    """The REAL dispatch path (no generate_fn): config.yaml routes
    reformat -> flash -> zai/glm-5.2. The record must carry the RESOLVED
    provider+model from the route receipt; the requested label
    ("operator-default", the pipeline's default) rides in
    params.requested_model."""
    from substrate.dispatch.router import register_provider, reset_provider_registry

    reset_provider_registry()
    register_provider(_FixtureProvider())
    try:
        _seed_source(env["db"])
        result = reformat_document(
            env["db"],
            owner_user_id=OWNER,
            source_document_id="doc-1",
            prompt=ACCEPTANCE_PROMPT,
            events_dir=env["events"],
        )
    finally:
        reset_provider_registry()
    assert result.contribution_classes == ["llm_compressed"]
    con = connect_read(env["db"])
    try:
        record = ProvenanceStore().get_generation(con, result.generation_id)
    finally:
        con.close()
    assert record is not None
    assert record.provider == "zai"  # the responder, from the receipt
    assert record.model == "glm-5.2"  # the tier's model — NOT the request
    params = json.loads(record.params_json)
    assert params["requested_model"] == "operator-default"  # the request, kept


def test_a_seam_generated_record_fabricates_no_identity(env) -> None:
    """The injectable seam has NO route receipt: provider stays NULL and the
    model column keeps the caller-declared label — the honest no-receipt
    state, never a fabricated responder."""
    _seed_source(env["db"])
    result = reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id="doc-1",
        prompt="compress it",
        params={"model": "fixture-model"},
        generate_fn=lambda prompt, blocks, params: [
            GeneratedBite(
                text="pricing, compressed",
                contribution_class="llm_compressed",
                source_block_indices=(0,),
            )
        ],
        events_dir=env["events"],
    )
    con = connect_read(env["db"])
    try:
        record = ProvenanceStore().get_generation(con, result.generation_id)
    finally:
        con.close()
    assert record is not None
    assert record.provider is None  # no receipt — honestly empty
    assert record.model == "fixture-model"  # the declared label, as such
    params = json.loads(record.params_json)
    assert params["requested_model"] == "fixture-model"
