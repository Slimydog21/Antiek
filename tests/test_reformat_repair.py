"""LB-4a: the reformat pipeline works, registers honestly and follows its source.

The forensic audit of the reformat stack (specs/antiek-mothership/cockpit/
FORENSIC-SWEEP-V2-KIMI-COCKPIT-2026-09-26.md §8.2 LB-4a) found it could not run
in production and, when it did write, mis-registered what it wrote:

- the real generator's dispatch role was unregistered (KeyError -> HTTP 500);
- the generation record stored the literal "operator-default", never the model
  that wrote the text;
- the derived document had no book_assets row, so the reader 404'd;
- the derived row was USER_CONTENT, ip_holder NULL, source_tier 1 (highest
  trust), with the content class copied once;
- a source takedown or reclassification never reached the derived text;
- a research_supplemented bite accepted any investigation id, real or not;
- the whole source went to the model in one unbounded call.

Each proof below failed before its fix.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_read, connect_write
from substrate.event_log import log_event
from substrate.graph.ops import insert_document, update_document_gate_columns
from substrate.reformat.pipeline import (
    GeneratedBite,
    ReformatError,
    SourceBlock,
    reformat_document,
)
from tests.test_reformat_pipeline import BODY, CHUNKS, env  # noqa: F401 - fixture used by name

OWNER = "__operator__"


@pytest.fixture(autouse=True)
def _scrub_operator_auth_env(monkeypatch):
    for key in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_COOKIE_INSECURE",
    ):
        monkeypatch.delenv(key, raising=False)


def _seed(db: str, *, document_id: str = "doc-1", content_class: str = "public_domain",
          ip_holder_id: str | None = None, owner: str = OWNER, book: bool = False) -> None:
    with connect_write(db, purpose="test/seed-reformat-repair") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="The Pricing Book",
            raw_text=BODY,
            content_class=content_class,
            ip_holder_id=ip_holder_id,
            owner_user_id=owner,
            on_conflict="ignore",
        )
        for i, (chunk_id, section, text) in enumerate(CHUNKS):
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
                "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [f"{chunk_id}-{document_id}", document_id, i, section, text, len(text.split())],
            )
        if book:
            from substrate.books.model import upsert_book_asset

            upsert_book_asset(con, document_id=document_id)


def _verbatim_generator(prompt: str, blocks: list[SourceBlock], params: dict) -> list[GeneratedBite]:
    return [
        GeneratedBite(text=blocks[0].text, contribution_class="author_verbatim", source_block_indices=(0,)),
        GeneratedBite(text="pricing, compressed", contribution_class="llm_compressed", source_block_indices=(0,)),
    ]


def _run(env, **kw):  # noqa: F811 - env is the pipeline fixture
    return reformat_document(
        env["db"],
        owner_user_id=OWNER,
        source_document_id=kw.pop("source_document_id", "doc-1"),
        prompt="the 20-minute version",
        generate_fn=kw.pop("generate_fn", _verbatim_generator),
        events_dir=env["events"],
        **kw,
    )


def _doc(db: str, document_id: str) -> tuple:
    con = connect_read(db)
    try:
        return con.execute(
            "SELECT content_class, ip_holder_id, source_tier, document_type "
            "FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()


# ── (c) the model that wrote the text is recorded ─────────────────────────


def _dispatch_result(text: str, *, model: str = "deepseek-v4-pro", event_id: str = "evt-disp-1",
                     cost: float = 0.0125):
    from substrate.dispatch.base import NormalizedUsage
    from substrate.dispatch.router import DispatchResult

    return DispatchResult(
        text=text,
        usage=NormalizedUsage(input_tokens=100, output_tokens=50),
        cost_usd=cost,
        latency_ms=10,
        provider="deepseek",
        model=model,
        tier="pro",
        finish_reason="stop",
        fallback_chain_index=0,
        event_id=event_id,
    )


def test_the_generation_record_names_the_model_that_wrote_it(env, monkeypatch) -> None:  # noqa: F811
    import substrate.dispatch.router as router

    _seed(env["db"])
    bites = [{"text": "pricing, compressed", "contribution_class": "llm_compressed",
              "source_block_indices": [0], "investigation_id": None}]
    monkeypatch.setattr(router, "dispatch", lambda *a, **k: _dispatch_result(json.dumps(bites)))
    result = reformat_document(env["db"], owner_user_id=OWNER, source_document_id="doc-1",
                               prompt="the 20-minute version", events_dir=env["events"])
    con = connect_read(env["db"])
    try:
        row = con.execute(
            "SELECT model, provider, dispatch_event_ids, cost_usd FROM generation_records "
            "WHERE generation_id = ?", [result.generation_id]
        ).fetchone()
    finally:
        con.close()
    assert row[0] == "deepseek-v4-pro"
    assert row[1] == "deepseek"
    assert json.loads(row[2]) == ["evt-disp-1"]
    assert row[3] == pytest.approx(0.0125)


# ── (b) an unavailable generator is a 503, never a 500 ─────────────────────


@pytest.mark.parametrize("failure", ["unregistered_role", "provider_down"])
def test_an_unavailable_generator_answers_503(env, monkeypatch, failure) -> None:  # noqa: F811
    import substrate.dispatch.router as router
    from interfaces.research.api.app import create_app
    from substrate.dispatch.base import ProviderError

    def boom(*a, **k):
        if failure == "unregistered_role":
            raise KeyError("Role 'reformat' not in config.role_tiers")
        raise ProviderError("every tier failed", provider="deepseek", model="m", latency_ms=1)

    _seed(env["db"])
    monkeypatch.setattr(router, "dispatch", boom)
    client = TestClient(create_app(register_wrestling=False), raise_server_exceptions=False)
    resp = client.post("/books/doc-1/reformats", json={"prompt": "the 20-minute version"})
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"] == "reformat_generator_unavailable"


# ── (d) the derived document opens in the reader; it is not in the library ─


def test_the_derived_document_opens_in_the_reader(env, monkeypatch) -> None:  # noqa: F811
    from interfaces.research.api import reformat_routes
    from interfaces.research.api.app import create_app

    _seed(env["db"])
    monkeypatch.setattr(reformat_routes, "_generate_fn_override", _verbatim_generator)
    client = TestClient(create_app(register_wrestling=False))
    created = client.post("/books/doc-1/reformats", json={"prompt": "the 20-minute version"})
    assert created.status_code == 201, created.text
    drv = created.json()["derived_document_id"]
    detail = client.get(f"/books/{drv}")
    assert detail.status_code == 200, detail.text
    # Provisional: reviewable in the reader, never library-listed at birth.
    listed = {b["document_id"] for b in client.get("/books").json()["books"]}
    assert drv not in listed


# ── (e) the derived row carries the source's rights, not USER_CONTENT/tier 1 ─


def test_a_licensed_sources_holder_and_class_follow_the_derived_text(env) -> None:  # noqa: F811
    from substrate.ip_holders import create_pre_onboarded

    with connect_write(env["db"], purpose="test/holder") as con:
        holder = create_pre_onboarded(con, display_name="The Pricing Press")
    _seed(env["db"], content_class="opt_in_licensed", ip_holder_id=holder)
    result = _run(env)
    content_class, ip_holder_id, tier, doc_type = _doc(env["db"], result.derived_document_id)
    assert content_class == "opt_in_licensed"
    assert ip_holder_id == holder
    # Generated text is never primary evidence: lowest trust tier.
    assert tier == 5
    assert doc_type == "derived"


def test_the_derivation_inherits_its_sources_class_and_binds_its_rights_basis(env) -> None:  # noqa: F811
    _seed(env["db"])
    result = _run(env)
    content_class, ip_holder_id, tier, _ = _doc(env["db"], result.derived_document_id)
    # THREAD-CONTRACT §1.11a: the reader view inherits its core document's
    # class and holder; generated text is never higher trust than its source.
    assert content_class == "public_domain"
    assert ip_holder_id is None
    assert tier == 5
    con = connect_read(env["db"])
    try:
        basis = con.execute(
            "SELECT rights_basis FROM generation_records WHERE generation_id = ?",
            [result.generation_id],
        ).fetchone()[0]
    finally:
        con.close()
    assert json.loads(basis) == {
        "core_documents": ["doc-1"],
        "most_restrictive_class": "public_domain",
        "holder_set": [],
    }


def test_a_derived_source_is_refused_until_chains_are_supported(env) -> None:  # noqa: F811
    _seed(env["db"])
    first = _run(env)
    with pytest.raises(ReformatError, match="derived_source_unsupported"):
        _run(env, source_document_id=first.derived_document_id)


def test_a_personal_reading_derivative_stays_owner_only(env) -> None:  # noqa: F811
    _seed(env["db"], content_class="personal_reading")
    result = _run(env)
    content_class, _, tier, _ = _doc(env["db"], result.derived_document_id)
    assert content_class == "personal_reading"
    assert tier == 5


# ── (f) the source's current gate reaches the derived text ─────────────────


def _serve(db: str, document_id: str, *, owner: bool = False):
    from substrate.books.serve import serve_full_text

    con = connect_read(db)
    try:
        return serve_full_text(con, document_id, owner=owner)
    finally:
        con.close()


def test_a_source_takedown_stops_the_derived_text(env) -> None:  # noqa: F811
    from substrate.books.takedown import reinstate, take_down

    _seed(env["db"], book=True)
    result = _run(env)
    drv = result.derived_document_id
    before = _serve(env["db"], drv)
    assert before.full_text is not None
    with connect_write(env["db"], purpose="test/takedown") as con:
        assert take_down(con, "doc-1", reason="removal demand") is True
    for owner in (False, True):
        after = _serve(env["db"], drv, owner=owner)
        assert after.full_text is None and after.snippet is None, owner
        assert after.reason in ("taken_down", "source_taken_down")
    # The derived book row is taken down too, so every retrieval path that
    # keys off content_class drops it, not only the full-text serve.
    con = connect_read(env["db"])
    try:
        row = con.execute(
            "SELECT b.taken_down, d.content_class FROM book_assets b "
            "JOIN documents d ON d.document_id = b.document_id WHERE b.document_id = ?",
            [drv],
        ).fetchone()
    finally:
        con.close()
    assert row[0] is True
    with connect_write(env["db"], purpose="test/reinstate") as con:
        assert reinstate(con, "doc-1") is True
    con = connect_read(env["db"])
    try:
        derived_down = con.execute(
            "SELECT taken_down FROM book_assets WHERE document_id = ?", [drv]
        ).fetchone()[0]
    finally:
        con.close()
    assert derived_down is False


def test_a_source_reclassification_caps_the_derived_serve(env) -> None:  # noqa: F811
    _seed(env["db"])
    result = _run(env)
    drv = result.derived_document_id
    assert _serve(env["db"], drv).full_text is not None
    with connect_write(env["db"], purpose="test/reclassify") as con:
        update_document_gate_columns(
            con, "doc-1", content_class="restricted_pending_opt_in", set_content_class=True,
        )
    capped = _serve(env["db"], drv)
    assert capped.full_text is None
    # No snippet either: the derived text carries the source's own words.
    assert capped.snippet is None
    assert capped.reason == "source_gated"


# ── (g) research ids must be real and the requester's ─────────────────────


def _research_generator(investigation_id: str):
    def gen(prompt: str, blocks: list[SourceBlock], params: dict) -> list[GeneratedBite]:
        return [GeneratedBite(text="a finding, woven in", contribution_class="research_supplemented",
                              source_block_indices=(0,), investigation_id=investigation_id)]
    return gen


def _start(events: str, investigation_id: str, owner: str | None = None) -> None:
    payload = {"question": "q"}
    if owner is not None:
        payload["owner_user_id"] = owner
    log_event(investigation_id, "investigation.start_requested", payload=payload, events_dir=events)


@pytest.mark.parametrize("bad", ["inv-never-ran", "../inv-escape", "inv-someone-elses"])
def test_a_research_bite_must_cite_a_real_owned_investigation(env, bad) -> None:  # noqa: F811
    _seed(env["db"])
    _start(env["events"], "inv-someone-elses", owner="someone-else")
    with pytest.raises(ReformatError, match="research_investigation"):
        _run(env, generate_fn=_research_generator(bad))


def test_a_research_bite_citing_a_real_investigation_is_kept(env) -> None:  # noqa: F811
    _seed(env["db"])
    _start(env["events"], "inv-real")
    _start(env["events"], "inv-mine", owner=OWNER)
    for iid in ("inv-real", "inv-mine"):
        result = _run(env, generate_fn=_research_generator(iid))
        assert result.contribution_classes == ["research_supplemented"]


# ── (i) the request is bounded ─────────────────────────────────────────────


def test_a_long_source_is_generated_in_bounded_windows(env, monkeypatch) -> None:  # noqa: F811
    import substrate.reformat.pipeline as pipeline

    _seed(env["db"])
    monkeypatch.setattr(pipeline, "WINDOW_CHARS", 40)  # every block becomes its own window
    seen: list[list[int]] = []

    def gen(prompt: str, blocks: list[SourceBlock], params: dict) -> list[GeneratedBite]:
        seen.append([b.index for b in blocks])
        return [GeneratedBite(text=blocks[0].text, contribution_class="author_verbatim",
                              source_block_indices=(blocks[0].index,))]

    result = _run(env, generate_fn=gen)
    assert len(seen) == 3 and all(len(w) == 1 for w in seen)
    assert len(result.bite_ids) == 3


def test_a_source_past_the_ceiling_is_refused_not_truncated(env, monkeypatch) -> None:  # noqa: F811
    import substrate.reformat.pipeline as pipeline

    _seed(env["db"])
    monkeypatch.setattr(pipeline, "MAX_SOURCE_CHARS", 20)
    with pytest.raises(ReformatError, match="source_too_long"):
        _run(env)


# ── (h) the engagement is not an investigation ─────────────────────────────


def test_the_route_returns_no_fake_thread_id(env, monkeypatch) -> None:  # noqa: F811
    from interfaces.research.api import reformat_routes
    from interfaces.research.api.app import create_app

    _seed(env["db"])
    monkeypatch.setattr(reformat_routes, "_generate_fn_override", _verbatim_generator)
    client = TestClient(create_app(register_wrestling=False))
    body = client.post("/books/doc-1/reformats", json={"prompt": "the 20-minute version"}).json()
    assert "thread_id" not in body
    assert body["generation_id"].startswith("gen-")
