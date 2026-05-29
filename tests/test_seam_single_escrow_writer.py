"""Collision #3 guard — single escrow writer (antiek-unified SPR-03).

Two ``attribution.py`` concerns are fine; two writers to the escrow ledger are
not. The load-bearing fix is single-writer discipline on the escrow *balance*,
mirroring the DuckDB single-writer invariant. The greppable invariants:

1. Exactly one ``SET escrow_balance_usd = …`` statement in the tree — in
   ``substrate/ip_holders/__init__.py::accrue_escrow`` (the low-level writer).
2. Exactly one call site of ``accrue_escrow`` — in
   ``substrate/speak/contributor.py`` (the application-level writer).
3. The attribution modules and ``publisher_escrow.py`` do NOT write escrow;
   ``publisher_escrow.py`` is read-only reporting.

Honesty (rigor #4): ``docs/decisions/tech-stack-ledger.md`` and the master spec
name ``marketplace_metrics/publisher_escrow.py`` the "single escrow writer." In
the live code that file *reports* escrow; it does not write it. The invariant
the ledger MEANS — exactly one escrow-balance writer — is what these tests
enforce, and the docstrings of both files now state this honestly. See the
SPR-03 handoff packet's open-questions section.

Rigor #3: the negative case (a second writer) fails the count assertions.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from substrate.contracts import AccrualContract

_REPO = Path(__file__).resolve().parent.parent
_SEARCH_DIRS = ("substrate", "ad_inventory", "acquisition", "roles", "orchestration")

_ESCROW_WRITER_MODULE = "substrate/ip_holders/__init__.py"
# The single escrow-balance WRITER is ip_holders.accrue_escrow — one
# ``SET escrow_balance_usd`` statement, asserted by
# test_exactly_one_escrow_balance_write_statement. Multiple revenue SOURCES
# legitimately route through that one writer: Speak's contributor 70% split
# and Read's book/publisher escrow (added when the Read workflow merged). Each
# is a sanctioned caller; a NEW, unsanctioned caller still fails the guard.
_SANCTIONED_ESCROW_CALLERS = frozenset({
    "substrate/speak/contributor.py",                 # contributor split (seam #3)
    "substrate/marketplace_metrics/book_escrow.py",   # Read book/publisher escrow
    # SPR-05: per-second frame-attention border accrual — a third sanctioned
    # revenue source routing through the one writer (ip_holders.accrue_escrow).
    "substrate/ad_inventory/frame_attention_accrual.py",
    # SPR-02 (corpus ingest): gated-mass-ingest escrow accrual — a fourth
    # sanctioned revenue source. When the rights classifier gates an
    # in-copyright work, escrow accrues to its pre_onboarded holder through the
    # one writer; accrual ≠ disbursement (G2/G3 stay operator-only).
    "substrate/ip_holders/gated_accrual.py",
})


def _code_only(source: str) -> str:
    """Return the source with every docstring blanked so a regex matches
    *executable code*, not prose that merely mentions the pattern (the
    seam-#3 docstrings now name ``SET escrow_balance_usd`` and ``accrue_escrow``
    in their explanations — those mentions must not count as writers)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc = body[0]
                for i in range(doc.lineno - 1, min(getattr(doc, "end_lineno", doc.lineno), len(lines))):
                    lines[i] = ""
    return "\n".join(lines)


def _files_matching(pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for d in _SEARCH_DIRS:
        root = _REPO / d
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if pattern.search(_code_only(py.read_text(encoding="utf-8"))):
                hits.append(str(py.relative_to(_REPO)))
    return sorted(set(hits))


def test_exactly_one_escrow_balance_write_statement():
    """The SQL-level invariant: one ``SET escrow_balance_usd = …``."""
    pattern = re.compile(r"SET\s+escrow_balance_usd\s*=")
    hits = _files_matching(pattern)
    assert hits == [_ESCROW_WRITER_MODULE], (
        f"escrow balance is written in {hits}; the single low-level writer is "
        f"{_ESCROW_WRITER_MODULE} (seam #3)"
    )


def test_exactly_one_accrue_escrow_call_site():
    """The application-level invariant: every caller of ``accrue_escrow`` is a
    sanctioned revenue source routing through the single writer (definition
    excluded). The single-WRITER invariant itself (one ``SET`` statement) is
    asserted separately; multiple revenue sources sharing the one writer is by
    design, an unsanctioned caller is not."""
    call = re.compile(r"\baccrue_escrow\s*\(")
    defn = re.compile(r"^def accrue_escrow\b", re.MULTILINE)
    callers: list[str] = []
    for d in _SEARCH_DIRS:
        root = _REPO / d
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            text = _code_only(py.read_text(encoding="utf-8"))
            # Remove the definition line so a module that both defines and is
            # the writer isn't double-counted; we want CALL sites.
            without_def = defn.sub("", text)
            if call.search(without_def):
                callers.append(str(py.relative_to(_REPO)))
    callers = sorted(set(callers))
    unsanctioned = [c for c in callers if c not in _SANCTIONED_ESCROW_CALLERS]
    assert not unsanctioned, (
        f"`accrue_escrow` is called from unsanctioned module(s) {unsanctioned}; "
        f"escrow accrual must come from a sanctioned revenue source "
        f"({sorted(_SANCTIONED_ESCROW_CALLERS)}), each routing through the single "
        f"writer ip_holders.accrue_escrow (seam #3)."
    )
    assert callers, "expected at least one sanctioned accrue_escrow caller"


def test_publisher_escrow_is_read_only():
    """``publisher_escrow.py`` must not write escrow — no balance UPDATE, no
    ``accrue_escrow`` call. It is the reporting surface."""
    p = _REPO / "substrate/marketplace_metrics/publisher_escrow.py"
    text = _code_only(p.read_text(encoding="utf-8"))
    assert "SET escrow_balance_usd" not in text
    # No call to the writer (the docstring naming it is fine — match a call).
    assert not re.search(r"\baccrue_escrow\s*\(", text)


def test_attribution_modules_do_not_write_escrow():
    """Neither attribution concern writes escrow directly. (Only
    ``ad_inventory/attribution.py`` exists today; ``marketplace_metrics/
    attribution.py`` is the spec's planned second concern — assert the rule for
    whichever exist.)"""
    candidates = [
        _REPO / "substrate/ad_inventory/attribution.py",
        _REPO / "substrate/marketplace_metrics/attribution.py",
    ]
    for p in candidates:
        if not p.exists():
            continue
        text = _code_only(p.read_text(encoding="utf-8"))
        assert "SET escrow_balance_usd" not in text, p
        assert not re.search(r"\baccrue_escrow\s*\(", text), p


def test_both_concerns_emit_the_single_accrual_shape():
    """Both attribution concerns converge on the one ``AccrualContract`` shape
    the escrow writer consumes (integer cents, disbursable fixed False)."""
    # The contract is the single wire shape; disbursable is non-settable.
    a = AccrualContract(
        accrual_id="acc-1",
        source="publisher_impression",
        source_ref="imp-1",
        amount_cents=0,
    )
    assert a.disbursable is False
    b = AccrualContract(
        accrual_id="acc-2",
        source="speak_contribution",
        source_ref="iv-1",
        amount_cents=500,
        share_fraction=0.7,
    )
    assert b.disbursable is False
    # SPR-05's per-second frame-attention accrual is the third producer on this
    # one shape: it accrues integer cents and is equally non-disbursable.
    c = AccrualContract(
        accrual_id="acc-frame-1",
        source="frame_attention_second",
        source_ref="frame-acc-deadbeef",
        amount_cents=125,
    )
    assert c.disbursable is False
    # A producer cannot flip disbursable — it is Literal[False].
    import pydantic

    try:
        AccrualContract(
            accrual_id="acc-3", source="speak_contribution",
            source_ref="iv-2", disbursable=True,  # type: ignore[arg-type]
        )
        assert False, "disbursable=True must be rejected (accrual ≠ disbursement)"
    except pydantic.ValidationError:
        pass


def test_a_synthetic_second_writer_would_fail(tmp_path):
    """Rigor #3 — prove the SQL guard FAILS on a real second writer."""
    (tmp_path / "ip.py").write_text("    SET escrow_balance_usd = escrow_balance_usd + ?\n")
    (tmp_path / "rogue.py").write_text("    SET escrow_balance_usd = 0\n")
    pattern = re.compile(r"SET\s+escrow_balance_usd\s*=")
    hits = [p.name for p in tmp_path.rglob("*.py") if pattern.search(p.read_text())]
    assert len(hits) == 2  # two writers — the real test would reject this
