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
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.distill_routes as dr
from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.event_log import trajectory_authorized
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import (
    promote_insight_authorized,
    promote_question_authorized,
)
from substrate.graph.tenancy import (
    GraphTenancyState,
    initialize_graph_authority,
    transition_graph_tenancy_state,
)
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas.events import ActionType
from tests.research_quote_support import (
    configure_research_quote_authority,
    signed_reserved_body,
)


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
    configure_research_quote_authority(monkeypatch, tmpdir)
    ensure_initialized(db)
    authority = InvestigationAuthority("__operator__", "inv-1", root=Path(events))
    initialize_composite_stream(authority)
    with connect_write(db, purpose="test-enable-authorized-distillation") as con:
        initialize_graph_authority(con, authority)
        transition_graph_tenancy_state(
            con, expected=GraphTenancyState.UNSCOPED, desired=GraphTenancyState.COPYING
        )
        transition_graph_tenancy_state(
            con, expected=GraphTenancyState.COPYING, desired=GraphTenancyState.SHADOW
        )
    # register_providers=False = the honest no-key state.
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return {
        "client": TestClient(app), "db": db, "events": events,
        "mp": monkeypatch, "authority": authority,
    }


def _seed(env, *, insights=(), questions=()):
    """Promote some insight/question nodes for inv-1, as a research would."""
    ids = {"insights": [], "questions": []}
    for t in insights:
        ids["insights"].append(promote_insight_authorized(
            env["authority"], text=t, confidence="moderate",
            source_document_id="doc-1"))
    for t in questions:
        ids["questions"].append(promote_question_authorized(
            env["authority"], text=t, source_document_id="doc-1"))
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
    assert r.status_code >= 400


# --------------------------------------------------------------------------
# M3 — challenge that resolves: mutate in place, no duplicate
# --------------------------------------------------------------------------


def test_challenge_resolves_mutates_in_place(env):
    ids = _seed(env, insights=["Acme is small."])
    nid = ids["insights"][0]
    # Inject a deterministic resolver that refines (stand-in for the model).
    env["mp"].setattr(dr, "make_dispatch_resolver",
                      lambda inv, **k: (lambda cur, ch: "Acme is mid-sized."))
    r = env["client"].post(f"/research/inv-1/notes/{nid}/challenge",
                           json={"challenge_text": "it grew"})
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
    r = env["client"].post(f"/research/inv-1/notes/{nid}/challenge",
                           json={"challenge_text": "source?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalated"] is True
    assert body["reserved_child_investigation_id"]
    # The escalation event carries the reserved id …
    rows = trajectory_authorized(env["authority"])
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
    esc_body = client.post(f"/research/inv-1/notes/{nid}/challenge",
                           json={"challenge_text": "source?"}).json()
    reserved = esc_body["reserved_child_investigation_id"]
    assert reserved
    # Nothing launched yet — the reserved id has no research.
    assert client.get(f"/investigations/{reserved}").status_code >= 400

    question_id = esc_body["escalated_question_id"]
    assert question_id
    # 2. Chase: the server resolves the child from the exact parent reservation;
    #    the browser never submits the reserved child id.
    launch_body = {
        "question": "Where do the margins come from?",
        "context": "Margins are healthy.",
        "research_tier": "deep",
        "approved_run_ceiling_usd": 1.0,
        "approved_chase_ceiling_usd": 2.0,
    }
    signed_launch_body = signed_reserved_body(
        client, "inv-1", question_id, launch_body
    )
    launch = client.post(
        f"/research/inv-1/questions/{question_id}/reserved-launch",
        json=signed_launch_body,
    )
    assert launch.status_code == 202, launch.text
    assert launch.headers["cache-control"] == "no-store"
    # The research lands under EXACTLY the reserved id — no orphan, no new id.
    assert launch.json()["investigation_id"] == reserved
    replay = client.post(
        f"/research/inv-1/questions/{question_id}/reserved-launch",
        json=signed_launch_body,
    )
    assert replay.status_code == 202
    assert replay.json() == launch.json()
    changed_body = {
        "question": "Changed question", "context": "Margins are healthy.",
        "research_tier": "deep", "approved_run_ceiling_usd": 1.0,
        "approved_chase_ceiling_usd": 2.0,
    }
    changed = client.post(
        f"/research/inv-1/questions/{question_id}/reserved-launch",
        json=signed_reserved_body(client, "inv-1", question_id, changed_body),
    )
    assert changed.status_code == 409

    # 3. The reserved research now exists, parented to the source research.
    child_authority = InvestigationAuthority(
        "__operator__", reserved, root=Path(env["events"])
    )
    rows = trajectory_authorized(child_authority)
    starts = [x for x in rows if x["action_type"] == ActionType.INVESTIGATION_START_REQUESTED.value]
    spawned = [x for x in rows if x["action_type"] == ActionType.INVESTIGATION_SPAWNED_FROM.value]
    assert len(starts) == 1, "exactly one launch — not a rogue second child"
    assert spawned and spawned[0]["payload"]["parent_investigation_id"] == "inv-1"
    assert starts[0]["payload"]["source_question_id"] == question_id
    assert starts[0]["payload"]["reservation_event_id"]
    assert starts[0]["payload"]["chase_budget_usd"] == 2.0
    assert starts[0]["payload"]["chase_mode"] == "depth"
    assert starts[0]["payload"]["chase_value"] == 2


def test_challenge_with_no_provider_is_honest_503(env):
    # The real resolver runs (no provider registered) → ChallengeUnavailable
    # → 503, NOT a fabricated refinement and NOT a spurious escalation.
    ids = _seed(env, insights=["A grounded claim."])
    nid = ids["insights"][0]
    def unavailable(_investigation_id, **_kwargs):
        raise dr.ChallengeUnavailable("test has no configured provider")

    env["mp"].setattr(dr, "make_dispatch_resolver", unavailable)
    r = env["client"].post(f"/research/inv-1/notes/{nid}/challenge",
                           json={"challenge_text": "really?"})
    assert r.status_code == 503, r.text
    assert "no model is configured" in r.json()["detail"]
    # No escalation was recorded — the note is untouched.
    rows = trajectory_authorized(env["authority"])
    assert all(x["action_type"] != ActionType.QUESTION_ESCALATED_TO_RESEARCH.value for x in rows)
    assert all(x["action_type"] != ActionType.NOTE_REFINED.value for x in rows)


def test_challenge_unknown_note_404(env):
    env["mp"].setattr(dr, "make_dispatch_resolver",
                      lambda inv, **k: (lambda cur, ch: "x"))
    r = env["client"].post("/research/inv-1/notes/node-does-not-exist/challenge",
                           json={})
    assert r.status_code == 404


def test_challenge_rejects_caller_supplied_investigation_identity(env):
    ids = _seed(env, insights=["Identity comes from the path."])
    r = env["client"].post(
        f"/research/inv-1/notes/{ids['insights'][0]}/challenge",
        json={"investigation_id": "foreign", "challenge_text": "really?"},
    )
    assert r.status_code == 422


def test_reserved_launch_rejects_unreserved_question_and_caller_child_id(env):
    question_id = _seed(env, questions=["A question without a reservation."])[
        "questions"
    ][0]
    body = {
        "question": "Research this unreserved question",
        "context": "",
        "research_tier": "deep",
        "approved_run_ceiling_usd": 1.0,
        "approved_chase_ceiling_usd": 2.0,
    }
    missing = env["client"].post(
        f"/research/inv-1/questions/{question_id}/reserved-launch",
        json=signed_reserved_body(env["client"], "inv-1", question_id, body),
    )
    assert missing.status_code == 404
    forged = env["client"].post(
        f"/research/inv-1/questions/{question_id}/reserved-launch",
        json={**body, "investigation_id": "inv-forged-child"},
    )
    assert forged.status_code == 422


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
