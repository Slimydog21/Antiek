"""SPR-02 · M3 — the static ungated-serve detector, red-proven both directions.

The load-bearing assertion is the NEGATIVE CONTROL: a synthetic function that
SELECTs ``canonical_label`` without the gate MUST be flagged. A detector that is
green on the clean tree but can't red an injected leak proves nothing — so we
construct the leak and observe the flag, then assert the real tree is clean.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.serve_gate_audit import (  # noqa: E402
    GATE_CALL,
    GUARDED_FIELD,
    SERVE_MODULES,
    audit,
    audit_source,
)

# ── NEGATIVE CONTROL: an injected ungated serve helper must be flagged ────────

_UNGATED_LEAK = '''
def leaky_serve(con, needle):
    """A serve helper that forgot the gate — the mistake M3 exists to catch."""
    return con.execute(
        "SELECT n.node_id, n.canonical_label FROM nodes n "
        "WHERE n.canonical_label ILIKE ?",
        [needle],
    ).fetchall()
'''

_GATED_OK = '''
def gated_serve(con, needle, policy_tag="attribution_eligible"):
    gate_sql, gate_params = _retrieval_gate.non_privileged_node_provenance_clause(
        node_alias="n", policy_tag=policy_tag,
    )
    return con.execute(
        f"SELECT n.node_id, n.canonical_label FROM nodes n "
        f"WHERE n.canonical_label ILIKE ?{gate_sql}",
        [needle, *gate_params],
    ).fetchall()
'''

_WRITE_PATH_NOT_A_SERVE = '''
def insert_node(con, node_id, label):
    con.execute(
        "INSERT INTO nodes (node_id, canonical_label) VALUES (?, ?)",
        [node_id, label],
    )
'''


def test_negative_control_ungated_serve_is_flagged():
    findings = audit_source(_UNGATED_LEAK, "synthetic/leak.py")
    assert len(findings) == 1, "an ungated canonical_label SELECT must be flagged"
    assert findings[0].qualname == "leaky_serve"
    assert GATE_CALL in findings[0].render()


def test_gated_serve_is_not_flagged():
    assert audit_source(_GATED_OK, "synthetic/ok.py") == [], (
        "a SELECT that routes through the gate must NOT be flagged"
    )


def test_write_path_is_not_a_serve_emission():
    # INSERT/UPDATE of canonical_label is a write, not a non-privileged serve —
    # requiring a read gate on the write path would be a false positive.
    assert audit_source(_WRITE_PATH_NOT_A_SERVE, "synthetic/write.py") == []


def test_fstring_sql_is_scanned():
    # The real emitters build gated SQL with f-strings; prove the detector reads
    # into a JoinedStr so an f-string leak can't slip the check.
    leak_fstring = (
        'def f(con, needle):\n'
        '    return con.execute(f"SELECT canonical_label FROM nodes '
        'WHERE canonical_label ILIKE {needle}").fetchall()\n'
    )
    findings = audit_source(leak_fstring, "synthetic/fstr.py")
    assert len(findings) == 1


# ── The real tree is clean (SPR-01 #202 + #292 gated every emitter) ───────────

def test_current_tree_has_zero_ungated_serve_paths():
    report = audit()
    assert report.modules_missing == [], (
        f"a configured serve module is missing (coverage gap): "
        f"{report.modules_missing}"
    )
    assert report.findings == [], (
        "ungated §9.0 serve path(s) on the current tree:\n"
        + "\n".join(f.render() for f in report.findings)
    )


def test_all_configured_serve_modules_exist_and_are_scanned():
    report = audit()
    assert set(report.modules_scanned) == set(SERVE_MODULES)
    assert report.ok


def test_guarded_field_and_gate_call_are_the_canonical_names():
    # Guards against a silent rename divorcing the detector from the real gate.
    assert GUARDED_FIELD == "canonical_label"
    assert GATE_CALL == "non_privileged_node_provenance_clause"
    from substrate.graph import retrieval_gate

    assert hasattr(retrieval_gate, GATE_CALL), (
        "the gate the detector requires must exist in retrieval_gate"
    )
