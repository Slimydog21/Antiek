"""The write-atomicity lint must be able to fail, and must not fire falsely.

A gate with no proof of sensitivity is not a gate. These tests pin both
directions: the shapes that lost data in production are caught, and the two
legitimate ways of being atomic are not flagged.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_LINT = _ROOT / "tools" / "lint" / "write_atomicity_check.py"

_spec = importlib.util.spec_from_file_location("write_atomicity_check", _LINT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["write_atomicity_check"] = _mod
_spec.loader.exec_module(_mod)


def _scan(src: str):
    scan = _mod._Scan()
    scan.visit(ast.parse(src))
    return scan.blocks


UNPROTECTED = '''
def handler():
    with connect_write(db, purpose="x") as con:
        con.execute("DELETE FROM t WHERE k = ?", [k])
        con.execute("INSERT INTO t VALUES (?, ?)", [k, v])
'''

TRANSACTION = '''
def handler():
    with connect_write(db, purpose="x") as con:
        with con.transaction():
            con.execute("DELETE FROM t WHERE k = ?", [k])
            con.execute("INSERT INTO t VALUES (?, ?)", [k, v])
'''

RAW_BEGIN = '''
def handler():
    with connect_write(db, purpose="x") as con:
        con.execute("BEGIN")
        con.execute("DELETE FROM t WHERE k = ?", [k])
        con.execute("INSERT INTO t VALUES (?, ?)", [k, v])
        con.execute("COMMIT")
'''

SINGLE_WRITE = '''
def handler():
    with connect_write(db, purpose="x") as con:
        con.execute("UPDATE t SET v = ? WHERE k = ?", [v, k])
'''

DDL_ONLY = '''
def handler():
    with connect_write(db, purpose="x") as con:
        con.execute("CREATE TABLE t (k TEXT)")
        con.execute("DROP TABLE old")
'''


def test_the_shape_that_lost_data_is_caught():
    """DELETE + INSERT with no transaction — the reorder-block and notebook bug."""
    blocks = _scan(UNPROTECTED)
    assert len(blocks) == 1
    _lineno, mutating, protected = blocks[0]
    assert len(mutating) == 2
    assert protected is False, "an unprotected multi-write must be reported"


def test_transaction_contextmanager_counts_as_protection():
    _lineno, mutating, protected = _scan(TRANSACTION)[0]
    assert len(mutating) == 2
    assert protected is True


def test_raw_begin_counts_as_protection():
    """acquisition/arxiv/store.py hand-rolls BEGIN/COMMIT and is correct.

    The first version of this scan did not recognise it and produced a false
    positive on a block that was already atomic.
    """
    _lineno, mutating, protected = _scan(RAW_BEGIN)[0]
    assert len(mutating) == 2
    assert protected is True


def test_a_single_write_is_never_a_violation():
    _lineno, mutating, _protected = _scan(SINGLE_WRITE)[0]
    assert len(mutating) == 1


def test_ddl_is_not_counted():
    """CREATE/DROP are excluded deliberately — see the module docstring."""
    _lineno, mutating, _protected = _scan(DDL_ONLY)[0]
    assert mutating == [], "DDL must not be counted as a mutating statement"


def test_the_lint_is_not_vacuous_against_the_real_tree():
    """If the file walk or the AST match broke, everything would pass silently."""
    listed = _mod.find_violations(list_all=True)
    assert len(listed) >= 50, (
        f"expected the scan to find many connect_write blocks, found "
        f"{len(listed)} — the file walk or the matcher has broken"
    )
    assert any("protected=True" in line for line in listed), (
        "no protected block found at all; the protection detector has broken "
        "and every atomic block would now be reported as a violation"
    )


def test_allowlist_entries_carry_a_reason():
    assert _mod._ALLOWLIST, "an empty allowlist means the exemptions were lost"
    for (path, lineno), reason in _mod._ALLOWLIST.items():
        assert isinstance(lineno, int) and lineno > 0, f"{path}: bad line"
        assert len(reason) >= 60, (
            f"{path}:{lineno} has a {len(reason)}-character reason. An "
            "exemption has to be argued, not asserted."
        )


def test_main_exits_clean_on_the_current_tree():
    """The tree must be green, so a future regression is visible as a change."""
    assert _mod.main([]) == 0, (
        "the tree has an unprotected multi-statement write that is not "
        "allowlisted; see the printed path:line"
    )
