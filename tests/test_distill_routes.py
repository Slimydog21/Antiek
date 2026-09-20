"""SPR-03 transport — the distill REST surface (insights / questions / living
notes) wired through the real ``create_app`` over a tmp DB.

Exercises the gates the sprint page names:

* M2 — ``GET /research/{id}/distill`` returns the insight + question nodes a
  research distilled, read off the graph (not re-derived).
* M3 — challenging a note that resolves mutates it in place (no duplicate);
  the determinism rule is the shipped one (verified at the unit level in
  ``test_async_note_taker.py``).
* M4 — an unresolvable challenge escalates with a reserved child id and
  launches NOTHING (no ``investigation.start_requested``); with no model
  configured the challenge returns 503 (honest no-key), never a fabricated
  refinement and never a spurious escalation.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.distill_routes as dr
from interfaces.research.api.app import create_app
from substrate.event_log import trajectory
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.schemas.events import ActionType


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture
def env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="distill-api-test-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    ensure_initialized(db)
    # register_providers=False = the honest no-key state. The dispatch
    # provider registry is process-global and can be polluted by
    # import-order side effects (provider modules registering at import
    # time); reset it so this fixture's "no provider" contract holds
    # regardless of what ran before in the same worker.
    from substrate.dispatch.router import reset_provider_registry

    reset_provider_registry()
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return {"client": TestClient(app), "db": db, "events": events, "mp": monkeypatch}


def _seed(env, *, insights=(), questions=()):
    """Promote some insight/question nodes for inv-1, as a research would."""
    ids = {"insights": [], "questions": []}
    for t in insights:
        ids["insights"].append(promote_insight(
            text=t, investigation_id="inv-1", confidence="moderate",
            source_document_id="doc-1"))
    for t in questions:
        ids["questions"].append(promote_question(
            text=t, investigation_id="inv-1", source_document_id="doc-1"))
    return ids


# --------------------------------------------------------------------------
# M2 — read the distilled insights + open questions
# --------------------------------------------------------------------------


def test_get_distillation_returns_graph_nodes(env):
    _seed(env, insights=["GPUs gate scale."], questions=["What is the moat?"])
    r = env["client"].get("/research/inv-1/distill")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [n["text"] for n in body["insights"]] == ["GPUs gate scale."]
    assert [n["text"] for n in body["questions"]] == ["What is the moat?"]
    assert body["insights"][0]["source_document_id"] == "doc-1"


def test_get_distillation_empty_is_honest(env):
    # No notes for this research → empty lists, not canned content.
    r = env["client"].get("/research/inv-nothing/distill")
    assert r.status_code == 200
    body = r.json()
    assert body["insights"] == [] and body["questions"] == []


# --------------------------------------------------------------------------
# M3 — challenge that resolves: mutate in place, no duplicate
# --------------------------------------------------------------------------


def test_challenge_resolves_mutates_in_place(env):
    ids = _seed(env, insights=["Acme is small."])
    nid = ids["insights"][0]
    # Inject a deterministic resolver that refines (stand-in for the model).
    env["mp"].setattr(dr, "make_dispatch_resolver",
                      lambda inv, **k: (lambda cur, ch: "Acme is mid-sized."))
    r = env["client"].post(f"/research/notes/{nid}/challenge",
                           json={"investigation_id": "inv-1", "challenge_text": "it grew"})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is True and r.json()["new_text"] == "Acme is mid-sized."
    # The distill view now reflects the mutation; still exactly one insight.
    body = env["client"].get("/research/inv-1/distill").json()
    assert [n["text"] for n in body["insights"]] == ["Acme is mid-sized."]


# --------------------------------------------------------------------------
# M4 — escalation reserves, does NOT launch
# --------------------------------------------------------------------------


def test_unresolvable_challenge_escalates_without_launch(env):
    ids = _seed(env, insights=["Margins are healthy."])
    nid = ids["insights"][0]
    # A resolver that declines → the escalation seam fires.
    env["mp"].setattr(dr, "make_dispatch_resolver",
                      lambda inv, **k: (lambda cur, ch: None))
    r = env["client"].post(f"/research/notes/{nid}/challenge",
                           json={"investigation_id": "inv-1", "challenge_text": "source?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalated"] is True
    assert body["reserved_child_investigation_id"]
    # The escalation event carries the reserved id …
    rows = trajectory("inv-1", events_dir=env["events"])
    esc = [x for x in rows if x["action_type"] == ActionType.QUESTION_ESCALATED_TO_RESEARCH.value]
    assert esc and esc[0]["payload"]["child_investigation_id"] == body["reserved_child_investigation_id"]
    # … and NOTHING is launched: no investigation.start_requested anywhere.
    assert all(x["action_type"] != ActionType.INVESTIGATION_START_REQUESTED.value for x in rows)


# --------------------------------------------------------------------------
# SPR-04 M2 — the chase REUSES the reserved escalation id (no orphan)
# --------------------------------------------------------------------------


def test_chase_reuses_reserved_escalation_id(env):
    """The full seam SPR-04 M2 depends on: SPR-03 escalation reserves a child
    id (launches nothing); SPR-04's chase launches INTO that exact id via the
    same POST /investigations path SPR-01 uses. The escalated question gets
    one research under the reserved id — not a rogue second child — and that
    research is parented to the source research."""
    client = env["client"]
    # 1. Escalate: an unresolvable challenge reserves a child id, launches nothing.
    ids = _seed(env, insights=["Margins are healthy."])
    nid = ids["insights"][0]
    env["mp"].setattr(dr, "make_dispatch_resolver",
                      lambda inv, **k: (lambda cur, ch: None))
    esc_body = client.post(f"/research/notes/{nid}/challenge",
                           json={"investigation_id": "inv-1", "challenge_text": "source?"}).json()
    reserved = esc_body["reserved_child_investigation_id"]
    assert reserved
    # Nothing launched yet — the reserved id has no research.
    assert client.get(f"/investigations/{reserved}").json()["status"] == "not_found"

    # 2. Chase: launch INTO the reserved id (what ChaseThread does on the
    #    explicit gesture). Same endpoint, with investigation_id set.
    launch = client.post("/investigations", json={
        "question": "Where do the margins come from?",
        "investigation_id": reserved,
        "parent_investigation_id": "inv-1",
        "spawn_context": "Margins are healthy.",
    })
    assert launch.status_code == 202, launch.text
    # The research lands under EXACTLY the reserved id — no orphan, no new id.
    assert launch.json()["investigation_id"] == reserved

    # 3. The reserved research now exists, parented to the source research.
    rows = trajectory(reserved, events_dir=env["events"])
    starts = [x for x in rows if x["action_type"] == ActionType.INVESTIGATION_START_REQUESTED.value]
    spawned = [x for x in rows if x["action_type"] == ActionType.INVESTIGATION_SPAWNED_FROM.value]
    assert len(starts) == 1, "exactly one launch — not a rogue second child"
    assert spawned and spawned[0]["payload"]["parent_investigation_id"] == "inv-1"


def test_challenge_with_no_provider_is_honest_503(env):
    # The real resolver runs (no provider registered) → ChallengeUnavailable
    # → 503, NOT a fabricated refinement and NOT a spurious escalation.
    ids = _seed(env, insights=["A grounded claim."])
    nid = ids["insights"][0]
    r = env["client"].post(f"/research/notes/{nid}/challenge",
                           json={"investigation_id": "inv-1", "challenge_text": "really?"})
    assert r.status_code == 503, r.text
    assert "no model is configured" in r.json()["detail"]
    # No escalation was recorded — the note is untouched.
    rows = trajectory("inv-1", events_dir=env["events"])
    assert all(x["action_type"] != ActionType.QUESTION_ESCALATED_TO_RESEARCH.value for x in rows)
    assert all(x["action_type"] != ActionType.NOTE_REFINED.value for x in rows)


def test_challenge_unknown_note_404(env):
    env["mp"].setattr(dr, "make_dispatch_resolver",
                      lambda inv, **k: (lambda cur, ch: "x"))
    r = env["client"].post("/research/notes/node-does-not-exist/challenge",
                           json={"investigation_id": "inv-1"})
    assert r.status_code == 404


@pytest.mark.store_isolation_contract
def test_graph_db_path_honors_env_override(monkeypatch, tmp_path):
    """The graph writer (promotion + living-note) and all readers must converge
    on one file: graph_db_path() follows ANTIEK_DUCKDB_PATH (the SPR-03
    split-writer fix). Without this, a prod env that sets the override splits
    the writer from the readers across two DuckDB files."""
    from substrate.graph.insight_question import graph_db_path

    target = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", target)
    assert graph_db_path() == target

    monkeypatch.delenv("ANTIEK_DUCKDB_PATH", raising=False)
    assert graph_db_path() != target  # falls back to the constant path
    # SPR-04 teardown guard: restore tmp override so default_db_path() is not
    # left on the real store when the autouse isolation fixture checks.
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", target)
