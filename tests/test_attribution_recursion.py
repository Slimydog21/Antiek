"""Attribution recursion — one metered attention-second reaching the writers.

The done-bar these tests hold, from
``.infinite/goal-2026-09-18-operational/specs/ads-settlement-and-attribution-recursion.md``
SPR-2:

1. One attention-second on a synthesis splits across the sourced
   ``ip_holder_id``s and the author, summing to EXACTLY one second including
   the unattributed remainder.
2. The split is reproducible from the event log alone.
3. It names its algorithm version.
4. Recursion depth is capped and the remainder is explicit.
5. No money moves while §9.0 is open — asserted here, not assumed.
"""

from __future__ import annotations

import glob
import json
import os
import tempfile

import pytest

from substrate.attribution.algorithms import ATTRIBUTION_SHARE_MATH_VERSION
from substrate.attribution.recursion import (
    ATTRIBUTION_RECURSION_VERSION,
    AUTHOR_SHARE_FIXED,
    AUTHOR_SHARE_POLICY,
    GATE_DISPLAY,
    MAX_RECURSION_DEPTH,
    REASON_AUTHOR_UNRESOLVED,
    REASON_CYCLE,
    REASON_DEPTH_CAP,
    REASON_OWNER_UNKNOWN,
    REASON_UNRESOLVED_SYNTHESIS,
    SUBJECT_AUTHOR,
    SUBJECT_IP_HOLDER,
    SUBJECT_UNATTRIBUTED,
    UNITS_PER_ATTENTION_SECOND,
    StaticProvenanceResolver,
    SynthesisProvenance,
    apportion_units,
    compute_recursive_attribution,
    replay,
    split_attention,
)
from substrate.schemas import TYPED_PAYLOAD_ACTION_TYPES, ActionType


def _resolver(*provenance: SynthesisProvenance) -> StaticProvenanceResolver:
    return StaticProvenanceResolver({p.synthesis_id: p for p in provenance})


def _units(split, kind: str, subject: str | None = None) -> int:
    return sum(
        s.units for s in split.shares
        if s.subject_kind == kind and (subject is None or s.subject_id == subject)
    )


# ─────────────────────────────────────────────────────────────────────
# 1. Conservation — the split sums to exactly one second
# ─────────────────────────────────────────────────────────────────────


def test_one_second_splits_across_sources_and_author_and_conserves():
    """The thesis, in one assertion: a second on a synthesis lands on the
    holders it sourced AND on its author, and nothing is created or lost."""
    split = split_attention(
        "syn-1",
        resolver=_resolver(SynthesisProvenance(
            synthesis_id="syn-1",
            author_user_id="writer-1",
            document_shares={"doc-a": 0.75, "doc-b": 0.25},
            document_ip_holders={"doc-a": "holder-a", "doc-b": "holder-b"},
        )),
    )
    assert split.conserves()
    assert split.total_units == UNITS_PER_ATTENTION_SECOND
    assert sum(s.units for s in split.shares) == UNITS_PER_ATTENTION_SECOND

    author = _units(split, SUBJECT_AUTHOR, "writer-1")
    assert author == int(UNITS_PER_ATTENTION_SECOND * AUTHOR_SHARE_FIXED)
    # The sourced remainder splits 75/25 between the two rights holders.
    assert _units(split, SUBJECT_IP_HOLDER, "holder-a") == 525_000
    assert _units(split, SUBJECT_IP_HOLDER, "holder-b") == 175_000
    assert split.unattributed_units() == 0


def test_many_seconds_conserve():
    split = split_attention(
        "syn-1",
        seconds=3_600,
        resolver=_resolver(SynthesisProvenance(
            synthesis_id="syn-1",
            author_user_id="writer-1",
            document_shares={f"doc-{i}": 1.0 / 7 for i in range(7)},
            document_ip_holders={f"doc-{i}": f"holder-{i}" for i in range(7)},
        )),
    )
    assert split.total_units == 3_600 * UNITS_PER_ATTENTION_SECOND
    assert split.conserves()


@pytest.mark.parametrize("n_docs", [1, 2, 3, 7, 11, 13, 97])
def test_conservation_holds_for_awkward_denominators(n_docs: int):
    """Largest-remainder, not rounding: seven or ninety-seven equal sources do
    not divide a second evenly, and the split must still sum back exactly."""
    split = split_attention(
        "syn-1",
        resolver=_resolver(SynthesisProvenance(
            synthesis_id="syn-1",
            author_user_id="writer-1",
            document_shares={f"d{i}": 1.0 for i in range(n_docs)},
            document_ip_holders={f"d{i}": f"h{i}" for i in range(n_docs)},
        )),
    )
    assert sum(s.units for s in split.shares) == UNITS_PER_ATTENTION_SECOND


def test_zero_seconds_is_an_empty_conserved_split():
    split = split_attention(
        "syn-1",
        seconds=0,
        resolver=_resolver(SynthesisProvenance(
            synthesis_id="syn-1", author_user_id="w",
            document_shares={"d": 1.0}, document_ip_holders={"d": "h"},
        )),
    )
    assert split.total_units == 0
    assert split.shares == ()
    assert split.conserves()


# ─────────────────────────────────────────────────────────────────────
# 2. The remainder is explicit — never silently vanished
# ─────────────────────────────────────────────────────────────────────


def test_unresolved_author_parks_units_under_a_named_reason():
    """A `syntheses` row carries no owner, so most real syntheses have no
    resolvable author. Those units must be visibly unattributed, not quietly
    handed to the sources — which would overstate what the sources are owed."""
    split = split_attention(
        "syn-1",
        resolver=_resolver(SynthesisProvenance(
            synthesis_id="syn-1",
            author_user_id=None,
            document_shares={"doc-a": 1.0},
            document_ip_holders={"doc-a": "holder-a"},
        )),
    )
    assert split.conserves()
    reasons = {s.reason for s in split.shares if s.subject_kind == SUBJECT_UNATTRIBUTED}
    assert reasons == {REASON_AUTHOR_UNRESOLVED}
    assert split.unattributed_units() == int(
        UNITS_PER_ATTENTION_SECOND * AUTHOR_SHARE_FIXED
    )
    assert _units(split, SUBJECT_IP_HOLDER, "holder-a") == 700_000


def test_document_without_an_owner_is_unattributed_not_redistributed():
    split = split_attention(
        "syn-1",
        resolver=_resolver(SynthesisProvenance(
            synthesis_id="syn-1",
            author_user_id="writer-1",
            document_shares={"doc-a": 0.5, "doc-b": 0.5},
            document_ip_holders={"doc-a": "holder-a", "doc-b": None},
        )),
    )
    assert split.conserves()
    assert _units(split, SUBJECT_IP_HOLDER, "holder-a") == 350_000
    unowned = [
        s for s in split.shares
        if s.subject_kind == SUBJECT_UNATTRIBUTED and s.reason == REASON_OWNER_UNKNOWN
    ]
    assert [s.units for s in unowned] == [350_000]


def test_unresolvable_synthesis_parks_the_whole_second():
    split = split_attention("syn-missing", resolver=_resolver())
    assert split.conserves()
    assert split.unattributed_units() == UNITS_PER_ATTENTION_SECOND
    assert split.shares[0].reason == REASON_UNRESOLVED_SYNTHESIS


def test_synthesis_with_no_sources_is_entirely_its_author():
    """A synthesis that cites nothing is all new ideas. There is no sourced
    material for the author's leg to compete with, so the author takes the
    whole second rather than 30% of it with the rest unattributed."""
    split = split_attention(
        "syn-1",
        resolver=_resolver(SynthesisProvenance(
            synthesis_id="syn-1", author_user_id="writer-1",
        )),
    )
    assert split.conserves()
    assert _units(split, SUBJECT_AUTHOR, "writer-1") == UNITS_PER_ATTENTION_SECOND


# ─────────────────────────────────────────────────────────────────────
# 3. Depth — capped, remainder explicit, cycles terminate
# ─────────────────────────────────────────────────────────────────────


def _chain(depth: int) -> StaticProvenanceResolver:
    """syn-0 → syn-1 → ... → syn-{depth-1} → a plain document."""
    provs = []
    for i in range(depth):
        provs.append(SynthesisProvenance(
            synthesis_id=f"syn-{i}",
            author_user_id=f"writer-{i}",
            document_shares={f"syn-{i + 1}": 1.0},
            document_ip_holders={f"syn-{i + 1}": None},
            nested_syntheses={f"syn-{i + 1}": f"syn-{i + 1}"},
        ))
    provs.append(SynthesisProvenance(
        synthesis_id=f"syn-{depth}",
        author_user_id=f"writer-{depth}",
        document_shares={"doc-deep": 1.0},
        document_ip_holders={"doc-deep": "holder-deep"},
    ))
    return _resolver(*provs)


def test_nested_synthesis_recurses_to_the_deep_rights_holder():
    """A synthesis citing a synthesis pays the writers the inner one sourced —
    the recursion, as opposed to crediting the inner synthesis as one asset."""
    split = split_attention("syn-0", resolver=_chain(1))
    assert split.conserves()
    assert _units(split, SUBJECT_AUTHOR, "writer-0") == 300_000
    assert _units(split, SUBJECT_AUTHOR, "writer-1") == 210_000  # 70% × 30%
    assert _units(split, SUBJECT_IP_HOLDER, "holder-deep") == 490_000
    assert split.unattributed_units() == 0
    assert {s.depth for s in split.shares} == {0, 1}


def test_depth_cap_parks_the_remainder_rather_than_recursing_forever():
    """A chain deeper than the cap stops, and the units it stopped carrying
    are a named line. Never a silent loss and never an unbounded walk."""
    deep = _chain(MAX_RECURSION_DEPTH + 2)
    split = split_attention("syn-0", resolver=deep)
    assert split.conserves()
    capped = [s for s in split.shares if s.reason == REASON_DEPTH_CAP]
    assert capped, "a chain past the cap must produce an explicit depth_cap line"
    assert all(s.depth == MAX_RECURSION_DEPTH + 1 for s in capped)
    # Nothing beyond the cap was credited to anyone.
    assert max(s.depth for s in split.shares) == MAX_RECURSION_DEPTH + 1


def test_depth_cap_is_configurable_and_the_default_is_the_constant():
    shallow = split_attention("syn-0", resolver=_chain(3), max_depth=1)
    assert shallow.conserves()
    assert shallow.max_depth == 1
    assert any(s.reason == REASON_DEPTH_CAP for s in shallow.shares)
    assert split_attention("syn-0", resolver=_chain(1)).max_depth == MAX_RECURSION_DEPTH


def test_cycle_terminates_and_is_reported():
    """syn-a cites syn-b which cites syn-a. Provenance graphs can contain
    this; a walk that loops is an outage, and a walk that silently drops the
    units is a dispute."""
    cyclic = _resolver(
        SynthesisProvenance(
            synthesis_id="syn-a", author_user_id="w-a",
            document_shares={"syn-b": 1.0},
            document_ip_holders={"syn-b": None},
            nested_syntheses={"syn-b": "syn-b"},
        ),
        SynthesisProvenance(
            synthesis_id="syn-b", author_user_id="w-b",
            document_shares={"syn-a": 1.0},
            document_ip_holders={"syn-a": None},
            nested_syntheses={"syn-a": "syn-a"},
        ),
    )
    split = split_attention("syn-a", resolver=cyclic)
    assert split.conserves()
    assert any(s.reason == REASON_CYCLE for s in split.shares)


def test_self_citing_synthesis_terminates():
    selfish = _resolver(SynthesisProvenance(
        synthesis_id="syn-a", author_user_id="w-a",
        document_shares={"syn-a": 1.0},
        document_ip_holders={"syn-a": None},
        nested_syntheses={"syn-a": "syn-a"},
    ))
    split = split_attention("syn-a", resolver=selfish)
    assert split.conserves()
    assert any(s.reason == REASON_CYCLE for s in split.shares)


# ─────────────────────────────────────────────────────────────────────
# 4. Versioning — every split names what priced it
# ─────────────────────────────────────────────────────────────────────


def test_split_stamps_all_three_versions():
    split = split_attention(
        "syn-1",
        resolver=_resolver(SynthesisProvenance("syn-1", author_user_id="w")),
        share_algorithm="B",
        share_algorithm_version=ATTRIBUTION_SHARE_MATH_VERSION,
    )
    assert split.recursion_version == ATTRIBUTION_RECURSION_VERSION
    assert split.author_share_policy == AUTHOR_SHARE_POLICY
    assert split.share_algorithm == "B"
    assert split.share_algorithm_version == ATTRIBUTION_SHARE_MATH_VERSION
    assert split.gate == GATE_DISPLAY


def test_recursion_version_is_not_the_share_math_version():
    """Three decisions can move a split independently — the §9.3 share math,
    the recursion walk, and the author-share policy. Collapsing them into one
    constant would make a payout dispute unresolvable, and would also spend
    the ATTRIBUTION_ALGORITHM_VERSION bump that
    docs/decisions/afa-synthesis-attribution-canonical.md reserves for the
    operator's still-unratified Option-C unification."""
    from substrate.ad_inventory import ATTRIBUTION_ALGORITHM_VERSION

    assert ATTRIBUTION_RECURSION_VERSION != ATTRIBUTION_ALGORITHM_VERSION
    assert ATTRIBUTION_RECURSION_VERSION != ATTRIBUTION_SHARE_MATH_VERSION
    assert AUTHOR_SHARE_POLICY != ATTRIBUTION_RECURSION_VERSION
    # The ad_inventory constant is untouched by this lane.
    assert ATTRIBUTION_ALGORITHM_VERSION == "attr-math-v1"


def test_author_share_policy_name_carries_its_number():
    """A row stamped with the policy name can never be re-read under a
    different constant, because the constant is in the name."""
    assert str(int(AUTHOR_SHARE_FIXED * 100)) in AUTHOR_SHARE_POLICY


# ─────────────────────────────────────────────────────────────────────
# 5. Apportionment determinism
# ─────────────────────────────────────────────────────────────────────


def test_apportion_units_conserves():
    out = apportion_units({"a": 1.0, "b": 1.0, "c": 1.0}, 1_000_000)
    assert sum(out.values()) == 1_000_000


def test_apportion_units_is_insertion_order_independent():
    """The property the cents twin in ad_inventory does not have: a tie must
    break on the key, not on however the caller happened to build the dict,
    or a replay is only reproducible by luck."""
    forward = apportion_units({"a": 1.0, "b": 1.0, "c": 1.0}, 100)
    backward = apportion_units({"c": 1.0, "b": 1.0, "a": 1.0}, 100)
    assert forward == backward
    assert sum(forward.values()) == 100


def test_apportion_units_handles_degenerate_inputs():
    assert apportion_units({}, 10) == {}
    assert apportion_units({"a": 0.0}, 10) == {"a": 0}
    assert apportion_units({"a": 1.0}, 0) == {"a": 0}
    assert apportion_units({"a": -1.0, "b": 1.0}, 10) == {"a": 0, "b": 10}


# ─────────────────────────────────────────────────────────────────────
# 6. Reproducible from the event log alone
# ─────────────────────────────────────────────────────────────────────


def test_replay_reproduces_the_split_from_its_inputs():
    split = split_attention("syn-0", resolver=_chain(2))
    again = replay(split.inputs_json)
    assert again.shares == split.shares
    assert again.inputs_digest == split.inputs_digest
    assert again.total_units == split.total_units


def test_replay_needs_no_database():
    """The inputs snapshot carries every resolved provenance the walk used, so
    a replay is pure. A replay that had to re-read the substrate would
    reproduce today's graph, not the graph that priced the row."""
    split = split_attention("syn-0", resolver=_chain(2))
    payload = json.loads(split.inputs_json)
    assert {p["synthesis_id"] for p in payload["provenance"]} == {
        "syn-0", "syn-1", "syn-2",
    }
    assert replay(json.dumps(payload)).shares == split.shares


def test_recursion_action_type_is_in_the_typed_set():
    assert ActionType.SYNTHESIS_ATTRIBUTION_RECURSED.value in TYPED_PAYLOAD_ACTION_TYPES


# ─────────────────────────────────────────────────────────────────────
# 7. Against the real substrate
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def seeded_substrate(monkeypatch):
    """A temp DuckDB carrying two documents with rights holders, their chunks,
    and one archived synthesis citing both."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    tmp = tempfile.mkdtemp(prefix="antiek-attr-recursion-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    init_database_at_path(db_path)

    with connect_write(db_path, purpose="seed-recursion") as con:
        for holder in ("holder-a", "holder-b"):
            con.execute(
                "INSERT INTO ip_holders (ip_holder_id, display_name, status, "
                "escrow_balance_usd) VALUES (?, ?, 'pre_onboarded', 0)",
                [holder, holder.title()],
            )
        insert_document(
            con, document_id="doc-a", source_tier=1,
            document_type="academic_paper", title="Tier-1 Paper",
            investigation_id="inv-1", content_class="public_domain",
            ip_holder_id="holder-a", owner_user_id="writer-1",
        )
        insert_document(
            con, document_id="doc-b", source_tier=2,
            document_type="academic_paper", title="Tier-2 Paper",
            investigation_id="inv-1", content_class="public_domain",
            ip_holder_id="holder-b", owner_user_id="writer-1",
        )
        insert_document(
            con, document_id="doc-private", source_tier=1,
            document_type="academic_paper", title="A Private Read",
            investigation_id="inv-1", content_class="personal_reading",
            ip_holder_id="holder-private", owner_user_id="writer-1",
        )
        chunk_a = insert_chunk(con, document_id="doc-a", chunk_index=0, text="A.")
        chunk_b = insert_chunk(con, document_id="doc-b", chunk_index=0, text="B.")
        chunk_p = insert_chunk(
            con, document_id="doc-private", chunk_index=0, text="Private.",
        )
        thesis = {
            "thesis_components": [
                {"claim": "C1", "confidence": "very_high",
                 "supporting_chunk_ids": [chunk_a, chunk_b, chunk_p]},
                {"claim": "C2 (analogy only)", "confidence": "low",
                 "supporting_chunk_ids": [], "supporting_path_indices": [0]},
            ],
        }
        con.execute(
            "INSERT INTO syntheses "
            "(synthesis_id, investigation_id, target_question, "
            " synthesis_timestamp, status, implicit_recommendation, "
            " thesis, thesis_token_count) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, 0)",
            ["syn-real", "inv-1", "Does it recurse?", "passed", "proceed",
             json.dumps(thesis)],
        )
    yield {"db_path": db_path, "events_dir": events_dir, "synthesis_id": "syn-real"}


def test_live_walk_reaches_the_rights_holders_through_real_provenance(
    seeded_substrate,
):
    """chunk → document → ip_holder, over the real substrate, conserved."""
    split = compute_recursive_attribution(
        seeded_substrate["synthesis_id"], db_path=seeded_substrate["db_path"],
    )
    assert split.conserves()
    assert split.total_units == UNITS_PER_ATTENTION_SECOND
    assert _units(split, SUBJECT_IP_HOLDER, "holder-a") > 0
    assert _units(split, SUBJECT_IP_HOLDER, "holder-b") > 0
    # The investigation's documents agree on one owner, so the author resolves.
    assert _units(split, SUBJECT_AUTHOR, "writer-1") == 300_000
    assert split.share_algorithm_version == ATTRIBUTION_SHARE_MATH_VERSION


def test_display_gate_keeps_personal_reading_out_of_the_split(seeded_substrate):
    """The resolver inherits compute.py's §9.0 display gate, so a
    ``personal_reading`` document earns nothing and is not even named. Note
    this is the DISPLAY gate: it also withholds ``restricted_pending_opt_in``,
    which an EARN path must keep accruing to escrow under §9.10. That is why
    every split records ``gate``."""
    split = compute_recursive_attribution(
        seeded_substrate["synthesis_id"], db_path=seeded_substrate["db_path"],
    )
    assert _units(split, SUBJECT_IP_HOLDER, "holder-private") == 0
    assert "holder-private" not in split.inputs_json
    assert split.gate == GATE_DISPLAY


def test_live_walk_has_no_nested_syntheses_today(seeded_substrate):
    """Honest scope: nothing in the tree deposits a synthesis back into
    ``documents``, so the live depth is 1. The cap and the cycle guard are
    exercised above against an injected resolver and arm themselves the day a
    depositor exists. If this assertion ever fails, a depositor landed — which
    is good news, and the depth cap is already in the versioned contract."""
    split = compute_recursive_attribution(
        seeded_substrate["synthesis_id"], db_path=seeded_substrate["db_path"],
    )
    assert {s.depth for s in split.shares} == {0}


def test_event_carries_the_split_and_replays_from_the_log_alone(seeded_substrate):
    split = compute_recursive_attribution(
        seeded_substrate["synthesis_id"],
        db_path=seeded_substrate["db_path"],
        investigation_id="inv-1",
        emit_event=True,
    )
    files = glob.glob(
        os.path.join(seeded_substrate["events_dir"], "**", "*.jsonl"), recursive=True,
    )
    rows = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            rows.extend(json.loads(line) for line in fh if line.strip())
    recursed = [
        r for r in rows
        if r.get("action_type") == ActionType.SYNTHESIS_ATTRIBUTION_RECURSED.value
    ]
    assert len(recursed) == 1
    payload = recursed[0]["payload"]
    assert payload["recursion_version"] == ATTRIBUTION_RECURSION_VERSION
    assert payload["author_share_policy"] == AUTHOR_SHARE_POLICY
    assert payload["share_algorithm_version"] == ATTRIBUTION_SHARE_MATH_VERSION
    assert sum(line["units"] for line in payload["lines"]) == payload["total_units"]

    # The done-bar's "reproducible from the event log alone": nothing but the
    # event row is consulted here.
    rebuilt = replay(payload["inputs_json"])
    assert rebuilt.inputs_digest == payload["inputs_digest"]
    assert [
        {
            "subject_kind": s.subject_kind,
            "subject_id": s.subject_id,
            "units": s.units,
            "depth": s.depth,
            "via_synthesis_id": s.via_synthesis_id,
            "reason": s.reason,
        }
        for s in rebuilt.shares
    ] == payload["lines"]
    assert rebuilt.shares == split.shares


# ─────────────────────────────────────────────────────────────────────
# 8. The money boundary — §9.0 is open
# ─────────────────────────────────────────────────────────────────────


_MONEY_WRITERS = (
    "accrue_escrow",
    "escrow_balance_usd",
    "attempt_disbursement",
    "record_attribution",
    "frame_attention_accruals",
    "speak_accruals",
    "stripe",
    "payout",
)


def test_recursion_module_reaches_no_money_writer():
    """Asserted, not assumed. The recursion computes who is owed attention;
    turning attention into money is gated on §9.0 counsel, and the module must
    not contain the vocabulary to do it."""
    import ast

    from substrate.attribution import recursion

    path = recursion.__file__
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source)
    # Blank every docstring: the module's prose explains the money boundary at
    # length and those mentions are the opposite of a violation.
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef):
            doc = ast.get_docstring(node, clean=False)
            if doc is None or not node.body:
                continue
            first = node.body[0]
            for i in range(first.lineno - 1, (first.end_lineno or first.lineno)):
                lines[i] = ""
    code = "\n".join(lines)
    # Comments are prose too.
    code = "\n".join(line.split("#", 1)[0] for line in code.splitlines())
    hits = [w for w in _MONEY_WRITERS if w in code]
    assert not hits, (
        f"substrate/attribution/recursion.py names money-path symbol(s) {hits} in "
        "executable code. §9.0 is open: accrual is not disbursement and this "
        "module is not even accrual."
    )


def test_computing_a_split_moves_no_money(seeded_substrate):
    """Run the live path against a real DB and prove the balances are
    untouched and no accrual row appeared."""
    import duckdb

    def _balances() -> dict[str, float]:
        con = duckdb.connect(seeded_substrate["db_path"], read_only=True)
        try:
            return {
                str(r[0]): float(r[1])
                for r in con.execute(
                    "SELECT ip_holder_id, escrow_balance_usd FROM ip_holders",
                ).fetchall()
            }
        finally:
            con.close()

    before = _balances()
    assert before, "fixture must seed at least one ip_holder to be meaningful"

    split = compute_recursive_attribution(
        seeded_substrate["synthesis_id"],
        db_path=seeded_substrate["db_path"],
        investigation_id="inv-1",
        emit_event=True,
    )
    assert _units(split, SUBJECT_IP_HOLDER, "holder-a") > 0, (
        "the split must credit a holder, or this test proves nothing"
    )
    assert _balances() == before

    con = duckdb.connect(seeded_substrate["db_path"], read_only=True)
    try:
        tables = {
            str(r[0]) for r in con.execute("SHOW TABLES").fetchall()
        }
        for ledger in ("frame_attention_accruals", "speak_accruals", "payouts"):
            if ledger in tables:
                count = con.execute(f"SELECT COUNT(*) FROM {ledger}").fetchone()
                assert count is not None and count[0] == 0, (
                    f"computing a split wrote to {ledger}"
                )
    finally:
        con.close()


def test_recursion_is_not_a_sanctioned_escrow_caller():
    """Belt to the module-scan's braces: the single-escrow-writer seam's
    allow-list must not name this module. If someone wires settlement later
    they have to add it there deliberately, in front of a reviewer."""
    from tests.test_seam_single_escrow_writer import _SANCTIONED_ESCROW_CALLERS

    assert "substrate/attribution/recursion.py" not in _SANCTIONED_ESCROW_CALLERS


# ─────────────────────────────────────────────────────────────────────
# 9. The author-share decision — a tripwire, not a stub
# ─────────────────────────────────────────────────────────────────────


def test_fixed_author_share_is_live_because_epistemic_typing_cannot_exist_yet():
    """The spec prefers an author share proportional to non-quoted-span
    length, which needs the five-way epistemic typing (quotation / paraphrase
    / measurement / inference / synthesis) on each claim.

    That typing is not merely unpopulated. ``ThesisComponent`` declares
    ``extra="forbid"``, so no synthesis in the tree can carry the field even
    if a synthesizer emitted it. The fixed constant is therefore live, behind
    a version, and this assertion is the tripwire: when someone adds the
    typing, this test fails and points at the decision record rather than
    letting the fixed share quietly outlive its justification.
    """
    from substrate.schemas.events import ThesisComponent

    assert ThesisComponent.model_config.get("extra") == "forbid"
    fields = set(ThesisComponent.model_fields)
    epistemic = {
        "epistemic_type", "claim_type", "quotation_spans", "quoted_span_chars",
    }
    assert not (fields & epistemic), (
        "epistemic typing landed on ThesisComponent — the principled "
        "author share is now buildable. See "
        "docs/decisions/attribution-recursion-author-share.md and bump "
        "AUTHOR_SHARE_POLICY rather than editing AUTHOR_SHARE_FIXED in place."
    )


def test_path_only_claims_are_measured_even_though_they_price_nothing(
    seeded_substrate,
):
    """The measurement that makes the author-share decision cheap to revisit:
    a claim citing no chunk is the substrate's closest structural evidence of
    an unsourced contribution. The fixture's second claim is path-grounded."""
    split = compute_recursive_attribution(
        seeded_substrate["synthesis_id"], db_path=seeded_substrate["db_path"],
    )
    snapshot = json.loads(split.inputs_json)["provenance"][0]
    assert snapshot["claim_count"] == 2
    assert snapshot["path_only_claim_count"] == 1
    # It measures; it does not price. The author leg is still the constant.
    assert _units(split, SUBJECT_AUTHOR, "writer-1") == int(
        UNITS_PER_ATTENTION_SECOND * AUTHOR_SHARE_FIXED
    )
