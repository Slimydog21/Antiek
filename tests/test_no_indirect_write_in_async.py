"""Behaviour of the indirect write-lock lint, including what it must NOT flag.

A lint that reds correct code gets switched off, and then it protects nothing.
Half of these cases therefore assert silence: the sanctioned thread-hop shape,
the nested sync def, and the test-file exemption all have to stay quiet, or
the 49 already-migrated call sites in this repo would turn red on landing.
"""

from __future__ import annotations

from pathlib import Path

from tools.lints.no_indirect_write_in_async import scan_file, scan_paths

HEADER = "from runtime.db_lock import connect_write\nfrom contextlib import contextmanager\nimport asyncio\n\n"


def _mod(tmp_path: Path, body: str, name: str = "mod.py") -> Path:
    p = tmp_path / name
    p.write_text(HEADER + body, encoding="utf-8")
    return p


def test_flags_contextmanager_helper_called_from_async(tmp_path: Path) -> None:
    """The exact shape the sibling lint documents as invisible to it."""
    p = _mod(tmp_path, """
@contextmanager
def _write(purpose):
    con = connect_write("db", purpose=purpose)
    try:
        yield con
    finally:
        con.close()


async def handler():
    with _write("x") as con:
        con.execute("select 1")
""")
    v = scan_file(p)
    assert len(v) == 1, [x.format_line() for x in v]
    assert v[0].helper == "_write"
    assert v[0].func == "handler"


def test_flags_transitive_helper(tmp_path: Path) -> None:
    """A helper that calls a helper that takes the lock still counts."""
    p = _mod(tmp_path, """
def _inner():
    return connect_write("db")


def _outer():
    return _inner()


async def handler():
    _outer()
""")
    assert [x.helper for x in scan_file(p)] == ["_outer"]


def test_silent_on_thread_hop_dispatch(tmp_path: Path) -> None:
    """The sanctioned migration must not be flagged."""
    p = _mod(tmp_path, """
def _sync():
    with connect_write("db") as con:
        con.execute("select 1")


async def handler():
    await asyncio.to_thread(_sync)
""")
    assert scan_file(p) == []


def test_silent_on_nested_sync_def(tmp_path: Path) -> None:
    """Same reasoning as the sibling lint: the nested def is the fix shape."""
    p = _mod(tmp_path, """
def _write_it():
    connect_write("db")


async def handler():
    def _inner():
        _write_it()

    return _inner
""")
    assert scan_file(p) == []


def test_call_in_hop_argument_position_is_still_flagged(tmp_path: Path) -> None:
    """``to_thread(_write(...))`` evaluates _write on the calling thread.

    Only a callable defers acquisition. This mirrors the sibling lint's
    argument-position rule, so the two agree rather than disagreeing.
    """
    p = _mod(tmp_path, """
def _write(p):
    return connect_write(p)


async def handler():
    await asyncio.to_thread(_write("db"))
""")
    assert [x.helper for x in scan_file(p)] == ["_write"]


def test_skips_test_files(tmp_path: Path) -> None:
    p = _mod(tmp_path, """
def _write():
    connect_write("db")


async def handler():
    _write()
""", name="test_something.py")
    assert scan_file(p) == []


def test_silent_when_module_has_no_write_lock_helper(tmp_path: Path) -> None:
    p = _mod(tmp_path, """
def helper():
    return 1


async def handler():
    helper()
""")
    assert scan_file(p) == []


def test_speak_routes_stays_clean() -> None:
    """Regression anchor on the real tree.

    speak_routes.py routes every Speak write through one module-level
    ``@contextmanager _write``, which is why it held the majority of the
    exposure for so long: the indirect lint exists because of this file.
    The 2026-09 Speak write migration moved all 24 write routes into
    nested ``def _sync()`` helpers dispatched via ``_off_loop``, at which
    point — per this test's own earlier docstring — "the migration is done
    and the baseline should shrink to match" (it did, to zero). The anchor
    now points the other way: this file must stay at ZERO, so a single
    reverted or newly added on-loop write fails here by name instead of
    hiding in a whole-tree count.
    """
    root = Path(__file__).resolve().parents[1]
    target = root / "interfaces" / "research" / "api" / "speak_routes.py"
    if not target.exists():           # pragma: no cover - path moved
        return
    found = scan_paths([target])
    assert not found, (
        "speak_routes.py migrated to `_off_loop` on 2026-09; these on-loop "
        "write-lock calls are regressions: "
        + "; ".join(f"line {v.line} in async def {v.func}" for v in found)
    )
