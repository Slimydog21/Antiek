"""DRW SPR-05 — cascade planner.

Mechanical gates: decompose → focused tree; over-broad problem → deeper tree;
atomic problem → single leaf; max-branch cap surfaces; persist+reload
round-trips; edit round-trip re-opens approval; gap/note seeds record
provenance; approval gate blocks launch and re-opens on edit.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.cascade_planner import (
    MAX_BRANCHES,
    PlanNotApproved,
    SubQuestion,
    approve_plan,
    assert_launchable,
    build_plan,
    focus_check,
    is_plan_launchable,
    load_tree,
    persist_tree,
    plan_from_gap,
    plan_from_note_challenge,
)
from roles.cascade_planner.tree_contract import PlanTree
from substrate.graph.schema import init_database_at_path


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class FakeDecomposer:
    """Maps a question to sub-questions. Default: split on ' and ' for
    over-broad questions, else atomic ([])."""

    def __init__(self, mapping=None):
        self._mapping = mapping or {}

    def decompose(self, question, *, context=""):
        if question in self._mapping:
            return [SubQuestion(question=q, rationale="r", focus_boundary="b")
                    for q in self._mapping[question]]
        # default: split a conjunctive question into its clauses
        if " and " in question:
            return [SubQuestion(question=part.strip(" ?"), rationale="r")
                    for part in question.split(" and ")]
        return []  # atomic


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def db(monkeypatch):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "g.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    init_database_at_path(path)
    return path


# --------------------------------------------------------------------------
# M1 — decomposition into a tree
# --------------------------------------------------------------------------


def test_build_plan_produces_tree_with_rationale():
    dec = FakeDecomposer({"problem": ["focused sub one", "focused sub two"]})
    report = build_plan("problem", decomposer=dec)
    assert report.tree.root.question == "problem"
    assert len(report.tree.root.children) == 2
    assert all(c.rationale for c in report.tree.root.children)


# --------------------------------------------------------------------------
# M5 — focus heuristics
# --------------------------------------------------------------------------


def test_focus_check_flags_over_broad():
    assert focus_check("What is the moat?").is_focused
    v = focus_check("What is the moat and how is pricing set and why churn and when IPO?")
    assert not v.is_focused and "over-broad" in v.reason


def test_over_broad_problem_yields_deeper_tree():
    # root splits into a focused leaf + an over-broad child; the over-broad
    # child must be expanded one level deeper.
    dec = FakeDecomposer({
        "problem": ["focused leaf", "alpha and beta and gamma and delta"],
        "alpha and beta and gamma and delta": ["alpha", "beta", "gamma"],
    })
    report = build_plan("problem", decomposer=dec)
    children = report.tree.root.children
    broad = [c for c in children if "alpha and beta" in c.question][0]
    assert len(broad.children) == 3            # deepened, not left vague
    focused = [c for c in children if c.question == "focused leaf"][0]
    assert focused.is_leaf                       # focused branch stays shallow


def test_atomic_problem_stays_single_leaf():
    dec = FakeDecomposer({"atomic question?": []})
    report = build_plan("atomic question?", decomposer=dec)
    assert report.tree.root.is_leaf
    assert report.tree.leaves == [report.tree.root]


def test_max_branch_cap_surfaces():
    dec = FakeDecomposer({"problem": [f"sub {i}" for i in range(MAX_BRANCHES + 5)]})
    report = build_plan("problem", decomposer=dec)
    assert len(report.tree.root.children) == MAX_BRANCHES
    assert report.tree.root.local_id in report.capped_nodes   # surfaced, not silent


# --------------------------------------------------------------------------
# M2 — persist + reload round-trip
# --------------------------------------------------------------------------


def test_persist_and_reload_round_trips(db):
    dec = FakeDecomposer({"problem": ["sub one", "sub two"]})
    tree = build_plan("problem", decomposer=dec).tree
    root_id = persist_tree(tree, investigation_id="inv-1",
                           embedding_provider=_FakeEmbedding(), db_path=db)
    loaded = load_tree(root_id, db_path=db)
    assert loaded is not None
    assert loaded.root.question == "problem"
    assert {c.question for c in loaded.root.children} == {"sub one", "sub two"}


# --------------------------------------------------------------------------
# M3 — editable tree contract round-trip
# --------------------------------------------------------------------------


def test_tree_edit_ops_round_trip_and_reopen_approval():
    dec = FakeDecomposer({"problem": ["sub one"]})
    tree = build_plan("problem", decomposer=dec).tree
    tree.approval.state = "approved"            # pretend approved
    child = tree.root.children[0]
    assert tree.reword(child.local_id, "reworded sub")     # edit
    assert tree.approval.state == "draft"        # edit re-opened the gate
    # serialization round-trips the edit.
    d = tree.to_dict()
    restored = PlanTree.from_dict(d)
    assert restored.root.children[0].question == "reworded sub"
    # add/remove/split round-trip
    added = tree.add_child(tree.root.local_id, "new branch")
    assert added and any(c.question == "new branch" for c in tree.root.children)
    assert tree.remove(added.local_id)
    assert all(c.question != "new branch" for c in tree.root.children)


# --------------------------------------------------------------------------
# M4 — gap- and note-seeded planning
# --------------------------------------------------------------------------


def test_plan_from_gap_records_provenance():
    class _Gap:
        question = "why is this claim unsupported?"
        gap_id = "gap-42"
        kind = "unsupported_claim"
    report = plan_from_gap(_Gap(), decomposer=FakeDecomposer())
    assert report.tree.seed_kind == "gap"
    assert report.tree.seed_provenance["gap_id"] == "gap-42"


def test_plan_from_note_challenge_records_provenance():
    report = plan_from_note_challenge("node-7", "challenge text", decomposer=FakeDecomposer())
    assert report.tree.seed_kind == "note_challenge"
    assert report.tree.seed_provenance["note_node_id"] == "node-7"


# --------------------------------------------------------------------------
# M6 — approval gate
# --------------------------------------------------------------------------


def test_approval_gate_blocks_then_allows_launch(db):
    dec = FakeDecomposer({"problem": ["sub one"]})
    tree = build_plan("problem", decomposer=dec).tree
    root_id = persist_tree(tree, investigation_id="inv-1",
                           embedding_provider=_FakeEmbedding(), db_path=db)
    # Unapproved → not launchable; assert_launchable raises.
    assert not is_plan_launchable(root_id, db_path=db)
    with pytest.raises(PlanNotApproved):
        assert_launchable(root_id, db_path=db)
    # Approve → launchable; event recorded.
    approve_plan(root_id, approver="operator", investigation_id="inv-1", db_path=db)
    assert is_plan_launchable(root_id, db_path=db)
    assert_launchable(root_id, db_path=db)       # no raise


def test_editing_approved_plan_reopens_gate(db):
    dec = FakeDecomposer({"problem": ["sub one"]})
    tree = build_plan("problem", decomposer=dec).tree
    root_id = persist_tree(tree, investigation_id="inv-1",
                           embedding_provider=_FakeEmbedding(), db_path=db)
    approve_plan(root_id, approver="operator", investigation_id="inv-1", db_path=db)
    assert is_plan_launchable(root_id, db_path=db)
    # Edit the tree (re-opens) and re-persist the re-opened approval state.
    tree.approval.state = "approved"             # reflect persisted state
    tree.reword(tree.root.children[0].local_id, "edited")
    assert tree.approval.state == "draft"        # in-memory gate re-opened
    persist_tree(tree, investigation_id="inv-1",
                 embedding_provider=_FakeEmbedding(), db_path=db)
    assert not is_plan_launchable(root_id, db_path=db)   # graph reflects re-open


# --------------------------------------------------------------------------
# ANT-H2V SPR-03 — production DispatchDecomposer adapter (hermetic)
# --------------------------------------------------------------------------


def _minimal_decomposer_json(investigation_id: str) -> dict:
    """Minimal valid decomposer payload (4 sub_qs, 8 keywords) — no test-module import."""
    return {
        "investigation_id": investigation_id,
        "decomposition": [
            {
                "sub_question": "What primary evidence shows X is real?",
                "category": "technology_risk",
                "rationale": "Verification needed.",
                "evidence_type_required": "quantitative",
            },
            {
                "sub_question": "What is the addressable market size for X?",
                "category": "market_sizing",
                "rationale": "Magnitude matters.",
                "evidence_type_required": "quantitative",
            },
            {
                "sub_question": "What execution risks appear in comparable cases?",
                "category": "team_and_execution",
                "rationale": "Prior art bounds claims.",
                "evidence_type_required": "qualitative",
            },
            {
                "sub_question": "What regulatory exposure does X face?",
                "category": "regulatory_exposure",
                "rationale": "Regulatory blocks invalidate thesis.",
                "evidence_type_required": "mixed",
            },
        ],
        "keywords": [{"term": f"kw{i}", "synonyms": [f"alt{i}"]} for i in range(8)],
    }


def test_dispatch_decomposer_maps_stub_response(monkeypatch):
    """Exercises DispatchDecomposer (not FakeDecomposer): kwargs + parse path."""
    import json
    import uuid

    import roles.decomposer as dec_mod
    import substrate.dispatch as dispatch_mod
    from roles.cascade_planner.planner import DispatchDecomposer

    fixed = uuid.UUID("00000000-0000-0000-0000-000000000012")
    monkeypatch.setattr(uuid, "uuid4", lambda: fixed)

    inv = "decomp-000000000000"  # uuid4().hex[:12] for fixed UUID above
    payload = _minimal_decomposer_json(inv)

    render_calls: list[dict] = []
    dispatch_calls: list[dict] = []

    def tracking_render(*, investigation_id, question, context="", extra_user_prefix=""):
        render_calls.append(
            dict(investigation_id=investigation_id, question=question, context=context),
        )
        return f"PROMPT:{investigation_id}:{question}"

    def tracking_dispatch(prompt, role, *, investigation_id, **kwargs):
        dispatch_calls.append(dict(role=role, investigation_id=investigation_id, prompt=prompt))
        class _Result:
            text = json.dumps(payload)
        return _Result()

    monkeypatch.setattr(dec_mod, "render_full_prompt", tracking_render)
    monkeypatch.setattr(dispatch_mod, "dispatch", tracking_dispatch)

    subs = DispatchDecomposer().decompose("What is the TAM for photonics?", context="ctx")
    assert len(subs) == 4
    assert subs[0].question.startswith("What primary evidence")
    assert render_calls[0]["question"] == "What is the TAM for photonics?"
    assert render_calls[0]["context"] == "ctx"
    assert render_calls[0]["investigation_id"] == dispatch_calls[0]["investigation_id"]
    assert render_calls[0]["investigation_id"].startswith("decomp-")
    assert dispatch_calls[0]["role"] == "decomposer"
