"""SPR-02 (Antiek × Hickey Decomplect) — the values-over-place floor.

Hickey, *Simple Made Easy*: prefer **values** (immutable data — identity is
not braided with time) over **place** (a mutable location whose contents
change in situ). Antiek already draws this line correctly at the
architectural level; this module turns the two halves of that line from a
*documented discipline* into a *mechanically-asserted fact* so a future
maintainer cannot silently erase it.

Two invariants are pinned here. Green means the invariant HOLDS; a red is a
real values/place violation to be reported, never relaxed.

VALUES side — the event log is append-only, no read-modify-write.
    Source of truth:
      * ``substrate/event_log/README.md`` §Contract: "Writes are append-only.
        No code path outside this module is permitted to mutate the log; even
        compaction is read-then-write to a new file followed by atomic rename."
      * ``substrate/event_log/events.py`` module docstring: "One JSON object
        per line, append-only. No read-modify-write."
    Observable failure guarded: if a body/row is rewritten in place, the
    trajectory the RL pipeline replays is silently corrupted — the sealed
    Parquet no longer equals the sequence of things that actually happened.

PLACE side — the DuckDB graph mutates, but only through the ONE serialized
single-writer lock (``runtime/db_lock.py``).
    Source of truth:
      * ``CLAUDE.md`` "Critical invariants #1 — DuckDB single-writer … enforced
        at ``runtime/db_lock.py``."
      * ``substrate/invariants/single-writer-per-graph.toml`` (registered,
        owner SPR-04) and ``single-writer-remote-exec.toml`` (guarded).
    Observable failure guarded: two concurrent writers on one DuckDB file
    corrupt or lose graph state.

Provenance floor (part of values-over-place): the cross-graph writer refuses
to propagate a rule whose ``evidence`` holds any non-hash value — the §13.3
"architecturally incapable of leaking" mechanism.

Relationship to existing assertions (for SPR-07 reconciliation):
    * The place-side *who-may-call-connect_write* scan already lives in
      ``tests/test_remote_exec_isolation.py::test_connect_write_only_in_funnel``
      and is composed by
      ``tests/test_integration_invariants.py::test_invariant_1_single_writer_isolation``.
      This module does NOT duplicate that scan — it pins a different, currently
      *unguarded* thing: that ``runtime/db_lock.py`` itself still opens the
      write connection *behind* an exclusive flock (the serializer's own
      internals), plus the observable serialization behavior.
    * The hash-only cross-graph evidence refusal already has behavioral
      coverage in ``tests/test_cross_graph_writer.py`` and
      ``tests/test_architectural_incapability.py``. Here it is re-framed as the
      values-over-place provenance floor and those tests are cited, not
      re-implemented wholesale.

Coverage gaps (honest scope — what this module does NOT prove):
    * "Who may open a graph WRITE connection" is NOT guarded repo-wide. The
      cited ``test_connect_write_only_in_funnel`` scans ONLY
      ``runtime/remote_exec/*.py`` (a ``glob`` over one package), so it proves
      "no remote-exec file bypasses the funnel" — not "no file anywhere calls
      ``duckdb.connect`` for writing." Concretely, ``runtime/db_lock.py:154``
      (``_log_write_event``) opens its own write connection OUTSIDE
      ``connect_write`` to append to ``write_log``; that is a *legitimate*
      internal writer (it sits behind the same exclusive flock — see
      ``test_db_lock_connect_write_is_exclusive_single_writer``), but it means
      neither the remote-exec scan nor this module asserts a repo-wide
      single-writer-connection property. A future repo-wide "every
      ``duckdb.connect(...)`` without ``read_only=True`` is inside a flock"
      audit would be the SPR-07 place to close this — it is out of scope here.
    * The append-only static scan (T1) is a tripwire over four open forms in
      ``substrate/event_log/`` only; it does not foreclose mutation via mmap /
      C-extension / subprocess / fully-dynamic open. The realistic append
      regression is backstopped behaviorally by T3.

Hermeticity: every test uses ``tmp_path``; none touch the operator's real
``~/.antiek`` event or graph store. No network. Runs in well under 5s.

Concurrency note (rigor #3): the event-log append path is deliberately NOT
serialized through a lock — each investigation writes its own JSONL and a
single line ≤ PIPE_BUF is atomic at the OS level, so there is no interleaving
to test on the values side. The single-writer lock is the *place*-side
mechanism; its serialization IS exercised behaviorally below. Neither arm
tries to fabricate a multi-writer race the architecture forecloses.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EVENT_LOG_DIR = REPO_ROOT / "substrate" / "event_log"
DB_LOCK_FILE = REPO_ROOT / "runtime" / "db_lock.py"


# ---------------------------------------------------------------------------
# AST helpers (stdlib only; no imports of the code under test needed to walk it)
# ---------------------------------------------------------------------------


def _literal_mode(node: ast.Call, mode_arg_index: int) -> tuple[str, bool]:
    """Resolve the literal string mode of an open-like call.

    Returns ``(mode, dynamic)``. ``mode`` is the literal mode string, defaulting
    to ``"r"`` when no mode argument is supplied — exactly as ``open()`` itself
    does. ``dynamic`` is True ONLY when a mode argument IS present (positionally
    at ``mode_arg_index`` or as ``mode=``) but is a non-literal expression we
    cannot classify here.

    ``mode_arg_index`` differs by call form: builtin ``open`` / ``io.open`` take
    ``(path, mode)`` so mode is positional index 1; the ``Path.open`` /
    ``<expr>.open`` method form takes ``(mode)`` on ``self`` so mode is index 0.
    """
    mode = "r"
    dynamic = False
    if len(node.args) > mode_arg_index:
        arg = node.args[mode_arg_index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            mode = arg.value
        else:
            dynamic = True
    for kw in node.keywords:
        if kw.arg == "mode":
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                mode = kw.value.value
            else:
                dynamic = True
    return mode, dynamic


def _os_open_flag_tokens(node: ast.Call) -> set[str] | None:
    """Return the set of ``O_*`` flag token names in an ``os.open(path, flags)``
    flags argument (e.g. ``{"O_WRONLY", "O_TRUNC"}``), or ``None`` when the flags
    argument is absent or fully opaque — a bare variable / call result with no
    readable ``O_*`` token, which we cannot classify statically.
    """
    if len(node.args) < 2:
        return None
    flags = node.args[1]
    tokens: set[str] = set()
    for n in ast.walk(flags):
        if isinstance(n, ast.Attribute) and n.attr.startswith("O_"):
            tokens.add(n.attr)
        elif isinstance(n, ast.Name) and n.id.startswith("O_"):
            tokens.add(n.id)
    return tokens or None


def _open_like_findings(tree: ast.AST):
    """Yield ``(lineno, violation_reason_or_None, is_append_write)`` for every
    open-like call in ``tree``.

    Four call forms that can open a file for writing are recognized:
      * builtin ``open(path, mode)``            — mode = 2nd positional / ``mode=``
      * ``io.open(path, mode)``                 — same signature as builtin open
      * ``<expr>.open(mode)`` (e.g. ``pathlib.Path.open``) — mode = 1st positional
      * ``os.open(path, flags)``                — low-level; classified by O_* flags

    ``violation_reason`` is non-None when the call can truncate (``w*`` /
    ``O_TRUNC``) or seek-rewrite (``r+`` / a write handle without append) an
    existing file's bytes, OR when the mode/flags are a non-literal indirection
    we cannot classify (so a computed truncating mode cannot be smuggled past).
    ``is_append_write`` is True only for a pure-append (``'a'`` / ``'a+'``)
    builtin/io/method open — the realistic append the non-vacuity guard checks.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            style = "builtin"
        elif isinstance(func, ast.Attribute) and func.attr == "open":
            if isinstance(func.value, ast.Name) and func.value.id == "os":
                style = "os"
            elif isinstance(func.value, ast.Name) and func.value.id == "io":
                style = "io"
            else:
                style = "method"
        else:
            continue

        if style == "os":
            tokens = _os_open_flag_tokens(node)
            if tokens is None:
                yield node.lineno, "os.open(...) with non-literal/opaque flags", False
            elif "O_TRUNC" in tokens:
                yield node.lineno, "os.open(..., O_TRUNC) truncates existing bytes", False
            elif ("O_WRONLY" in tokens or "O_RDWR" in tokens) and "O_APPEND" not in tokens:
                yield (
                    node.lineno,
                    "os.open(..., O_WRONLY/O_RDWR without O_APPEND) can rewrite existing bytes",
                    False,
                )
            # else: O_RDONLY or an O_APPEND write — cannot rewrite an existing
            # row; not our append non-vacuity signal either (os.open is low-level).
            continue

        mode_index = 1 if style in ("builtin", "io") else 0
        mode, dynamic = _literal_mode(node, mode_index)
        if dynamic:
            yield node.lineno, f"{style} open() with non-literal mode", False
            continue
        is_append = ("a" in mode) and not _mode_rewrites_existing_bytes(mode)
        if _mode_rewrites_existing_bytes(mode):
            yield node.lineno, f"{style} open(..., {mode!r}) rewrites existing bytes", False
        else:
            yield node.lineno, None, is_append


def _calls_os_replace(node: ast.AST) -> bool:
    """True if ``node`` contains a genuine ``os.replace(...)`` call — the atomic
    rename primitive — as opposed to any ``.replace`` attribute (e.g. the string
    method ``line.replace(...)``), which a bare attr-name scan would conflate.
    """
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "replace"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "os"
        ):
            return True
    return False


def _mode_rewrites_existing_bytes(mode: str) -> bool:
    """True if ``mode`` can truncate or update-in-place an existing file's
    bytes — i.e. it is NOT append-only / read-only / write-a-new-file.

    * ``'w'`` family truncates the target.
    * ``'r+'`` family opens for in-place read/write (seek-rewrite).
    * ``'a'`` / ``'a+'`` only ever append (writes go to EOF), ``'r'`` reads,
      ``'x'`` creates a brand-new file — none can rewrite an existing row.
    """
    return ("w" in mode) or ("r" in mode and "+" in mode)


def _funcdef(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found — did db_lock.py change shape?")


def _duckdb_connect_calls(node: ast.AST):
    """Yield every ``duckdb.connect(...)`` Call node under ``node``."""
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "connect"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "duckdb"
        ):
            yield n


def _has_read_only_true(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "read_only" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def _attr_names(node: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


# ---------------------------------------------------------------------------
# M2 · VALUES arm — the event log is append-only, no read-modify-write
# ---------------------------------------------------------------------------


def test_event_log_append_only_no_truncating_open_modes():
    """VALUES (static): no open-like call in ``substrate/event_log/`` opens an
    event-store file in a truncating or seek-rewrite form.

    Invariant: "the event log is values — append-only, no read-modify-write"
    (event_log/README.md §Contract; events.py module docstring).

    Honest scope of THIS scan (it is a static tripwire, not a proof of the
    module-wide invariant): it recognizes four write-capable open forms and
    flags the ones that can clobber existing bytes —
      * builtin ``open(path, mode)`` with a truncating (``w*``) / seek-rewrite
        (``r+``) literal mode,
      * ``io.open(path, mode)`` (same signature) with such a mode,
      * ``<expr>.open(mode)`` (e.g. ``pathlib.Path.open``) with such a mode,
      * ``os.open(path, flags)`` whose flags include ``O_TRUNC`` or a write
        handle (``O_WRONLY`` / ``O_RDWR``) without ``O_APPEND``,
    plus any non-literal/opaque mode-or-flags indirection (flagged so a
    computed truncating mode cannot be smuggled past). It does NOT prove that
    "nothing is allowed to mutate the log" — a determined maintainer could
    still mutate via ``mmap``, a C extension, a fully-dynamic ``getattr`` open,
    or a subprocess. The realistic append-mutation regression is backstopped
    BEHAVIORALLY by ``test_event_log_second_append_does_not_alter_first_event_bytes``.

    Guards against: a maintainer changing the append (``'a'``) write to a
    truncating/rewriting mode — including the attribute-form clobbers
    (``os.open(..., O_TRUNC)``, ``Path.open('w')``) the earlier bare-``open``
    scan let slip — which would let a later event silently rewrite an earlier
    row and destroy the replay trajectory. Failure names file:line:reason.
    """
    assert EVENT_LOG_DIR.is_dir(), f"event_log dir missing at {EVENT_LOG_DIR}"
    py_files = sorted(EVENT_LOG_DIR.rglob("*.py"))
    assert py_files, "no event_log python files found to walk"

    violations: list[str] = []
    saw_append_write = False
    for py in py_files:
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for lineno, reason, is_append in _open_like_findings(tree):
            if is_append:
                saw_append_write = True
            if reason is not None:
                violations.append(f"{py.name}:{lineno}: {reason}")

    assert violations == [], (
        "event log is NOT provably append-only — read-modify-write reached the "
        f"values side: {violations}. Per event_log/README.md the log must never "
        "be mutated in place; report this, do not relax the assertion."
    )
    # Non-vacuity: the module really does an append write somewhere (an empty
    # module would pass the negative check for the wrong reason).
    assert saw_append_write, (
        "no append-mode write found in substrate/event_log/ — the values-side "
        "guard would be vacuous. Expected the JSONL append in events.py."
    )


def test_event_log_seal_is_write_new_then_atomic_rename_immutable():
    """VALUES: sealing JSONL → Parquet writes a NEW file and atomically
    renames it into place — it never rewrites the sealed file in situ.

    Invariant: "even compaction is read-then-write to a new file followed by
    atomic rename" (event_log/README.md §Contract). This positively pins the
    legitimate seal pattern so (a) the static arm above is not mistaken for
    forbidding sealing, and (b) a maintainer who changes seal to mutate the
    Parquet in place trips a red.

    Guards against: turning the immutable write-new-then-rename seal into an
    in-place Parquet mutation, which would braid the sealed trajectory's
    identity with time (place), not values.
    """
    events_src = (EVENT_LOG_DIR / "events.py").read_text(encoding="utf-8")
    tree = ast.parse(events_src)
    seal = _funcdef(tree, "seal_investigation")
    # Couple the check to a genuine ``os.replace(...)`` call — not any
    # ``.replace`` attribute (a bare attr-name scan would also match the string
    # method ``line.replace(...)``, giving a false green if the atomic rename
    # were removed but some unrelated ``.replace`` remained).
    assert _calls_os_replace(seal), (
        "seal_investigation no longer calls os.replace — the atomic "
        "write-new-then-rename seal (values discipline) was removed."
    )
    # The write target is a temp sibling, not the sealed path itself.
    src = ast.get_source_segment(events_src, seal) or ""
    assert ".tmp" in src, (
        "seal_investigation no longer writes to a '.tmp' sibling before rename — "
        "the write-to-new-file half of the immutable seal is gone."
    )


def test_event_log_second_append_does_not_alter_first_event_bytes(tmp_path, monkeypatch):
    """VALUES (behavioral): appending a second event does not change one byte
    of the first event's on-disk representation.

    This is the observable meaning of "no read-modify-write": the first row's
    bytes are a strict prefix of the file after the second append. A count of
    events is NOT an immutability proof; byte-prefix identity is.

    Invariant source: events.py ``_append_jsonl`` opens in ``'a'`` mode.
    Guards against: any change that rewrites or reorders earlier rows when a
    new event lands.
    """
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    from substrate.event_log.events import _jsonl_path, log_event

    ev = str(tmp_path / "events")
    iid = "inv-spr02-values"

    e1 = log_event(iid, "phase.enter", payload={"n": 1}, events_dir=ev)
    assert e1, "first emit returned no event_id (events disabled?)"
    path = _jsonl_path(iid, events_dir=ev)
    after_first = pathlib.Path(path).read_bytes()
    assert after_first.count(b"\n") == 1

    e2 = log_event(iid, "phase.exit", payload={"n": 2}, events_dir=ev)
    assert e2 and e2 != e1
    after_second = pathlib.Path(path).read_bytes()

    assert after_second.startswith(after_first), (
        "the second append rewrote the first event's bytes — this is a "
        "read-modify-write on the event log (a values violation). REPORT it."
    )
    assert after_second.count(b"\n") == 2
    assert after_second[: len(after_first)] == after_first


def test_event_log_every_event_carries_policy_id_provenance(tmp_path, monkeypatch):
    """VALUES/provenance: every emitted event carries a non-null ``policy_id``.

    Invariant: ``policy_id`` is REQUIRED (events.py schema docstring: "identifies
    the policy that produced the artifact … lets downstream pipelines exclude
    closed-weight trajectories from open-weight RL training"). Out-of-scope per
    the sprint: no simplification may drop a provenance field.

    Guards against: an emit path that writes an event with no policy provenance,
    which would poison the RL trajectory partitioning.
    """
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    from substrate.event_log.events import log_event, trajectory
    from substrate.schemas.events import DEFAULT_POLICY_ID

    ev = str(tmp_path / "events")
    iid = "inv-spr02-policy"
    log_event(iid, "phase.enter", events_dir=ev)  # default policy_id path
    log_event(iid, "phase.exit", policy_id="deepseek-chat/v3-prompt7", events_dir=ev)

    rows = trajectory(iid, events_dir=ev)
    assert len(rows) == 2
    for r in rows:
        assert r.get("policy_id"), f"event missing policy_id provenance: {r.get('event_id')}"
    by_action = {r["action_type"]: r["policy_id"] for r in rows}
    assert by_action["phase.enter"] == DEFAULT_POLICY_ID
    assert by_action["phase.exit"] == "deepseek-chat/v3-prompt7"


def test_event_log_values_readback_sorts_by_emitted_at_then_event_id(tmp_path, monkeypatch):
    """VALUES: ``trajectory`` returns events in a canonical order
    (``emitted_at`` then ``event_id``) REGARDLESS of their on-disk order — and
    that order is stable across re-reads.

    A value is stable across time (Hickey): the sequence downstream RL replay
    consumes must be a deterministic function of the event *contents*, not of
    the incidental order lines happened to land in the file.

    Why this test writes the JSONL by hand instead of calling ``log_event``:
    the production emit path stamps ``emitted_at`` with ``datetime.now()``, so
    events appended in call order are ALSO already in ``emitted_at`` order —
    making file-order == sorted-order and the ``rows.sort(...)`` in
    ``trajectory`` a no-op the test could never exercise. (That is exactly why
    the previous version of this test was tautological: it compared two reads of
    the same already-sorted data.) To give the sort teeth we materialize rows
    whose file order deliberately DIFFERS from the intended sorted order —
    including a tie on ``emitted_at`` written in reverse ``event_id`` order to
    exercise the secondary sort key — then assert ``trajectory`` reorders them.

    Guards against: removing/weakening the ``trajectory`` sort (a maintainer
    "simplifying" the read path), which would surface events in raw file order
    and silently corrupt the replayed trajectory. Removing the ``.sort(...)`` in
    events.py MUST turn this test red.
    """
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    from substrate.event_log.events import _jsonl_path, trajectory

    ev = str(tmp_path / "events")
    iid = "inv-spr02-order"

    def _row(event_id: str, emitted_at: str, action_type: str) -> dict:
        return {
            "event_id": event_id,
            "investigation_id": iid,
            "action_type": action_type,
            "payload": {},
            "policy_id": "orchestrator-deterministic",
            "emitted_at": emitted_at,
        }

    # On-disk (file/insertion) order is scrambled on BOTH sort keys.
    # evt-a1 and evt-a2 share an emitted_at and are written a2-before-a1 so the
    # secondary event_id key must reorder them.
    file_order = [
        _row("evt-d", "2020-01-01T00:00:04Z", "phase.exit"),
        _row("evt-b", "2020-01-01T00:00:02Z", "role.call.start"),
        _row("evt-a2", "2020-01-01T00:00:01Z", "note.append"),
        _row("evt-a1", "2020-01-01T00:00:01Z", "phase.enter"),
        _row("evt-c", "2020-01-01T00:00:03Z", "role.call.end"),
    ]
    path = pathlib.Path(_jsonl_path(iid, events_dir=ev))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in file_order),
        encoding="utf-8",
    )

    # Sanity: the fixture really is out of order on disk (guards the guard —
    # if the rows were already sorted, removing the sort couldn't be detected).
    on_disk_ids = [json.loads(line)["event_id"] for line in path.read_text().splitlines()]
    canonical_ids = ["evt-a1", "evt-a2", "evt-b", "evt-c", "evt-d"]
    assert on_disk_ids != canonical_ids, "fixture is not scrambled — the test would be vacuous"

    rows_a = trajectory(iid, events_dir=ev)
    rows_b = trajectory(iid, events_dir=ev)

    assert len(rows_a) == 5
    # The core ordering guard: trajectory MUST return canonical order, not file
    # order. Remove events.py's `rows.sort(...)` and this assertion goes red.
    assert [r["event_id"] for r in rows_a] == canonical_ids, (
        "trajectory did not sort by (emitted_at, event_id) — it surfaced events "
        "in raw file order. The replayed RL trajectory would be corrupted. REPORT."
    )
    assert [r["action_type"] for r in rows_a] == [
        "phase.enter", "note.append", "role.call.start", "role.call.end", "phase.exit",
    ]
    # Stability across re-reads (the "stable value" half of the invariant).
    assert [r["event_id"] for r in rows_a] == [r["event_id"] for r in rows_b]


# ---------------------------------------------------------------------------
# M3 · PLACE arm — the DuckDB graph mutates only through the one serialized lock
# ---------------------------------------------------------------------------


def test_db_lock_connect_write_is_exclusive_single_writer():
    """PLACE (static): ``connect_write`` takes an EXCLUSIVE flock BEFORE opening
    the DuckDB write connection, and never opens the write connection read-only.

    Invariant: DuckDB single-writer, enforced at ``runtime/db_lock.py``
    (CLAUDE.md critical invariant #1; §16). Place may mutate, but only through
    this one serialized writer. No existing test guards ``db_lock``'s own
    internals (the remote-exec test guards *who calls* connect_write; this
    guards that connect_write *still serializes*) — this is the gap SPR-02 fills.

    Guards against: (a) dropping the ``fcntl.flock(LOCK_EX)`` so writers stop
    serializing, (b) downgrading to a shared lock (``LOCK_SH``) that admits
    concurrent writers, (c) opening the graph after (or without) acquiring the
    lock. Any of these reintroduces multi-writer DuckDB corruption.
    """
    tree = ast.parse(DB_LOCK_FILE.read_text(encoding="utf-8"))
    cw = _funcdef(tree, "connect_write")

    attrs = _attr_names(cw)
    assert "LOCK_EX" in attrs, "connect_write no longer acquires an EXCLUSIVE flock (LOCK_EX)"
    assert "LOCK_SH" not in attrs, (
        "connect_write acquired a SHARED lock (LOCK_SH) — shared locks admit "
        "concurrent writers and break single-writer place."
    )

    flock_ex_linenos = [
        n.lineno
        for n in ast.walk(cw)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "flock"
        and "LOCK_EX" in _attr_names(n)
    ]
    connects = list(_duckdb_connect_calls(cw))
    assert flock_ex_linenos, "no exclusive-flock acquisition found in connect_write"
    assert connects, "connect_write no longer opens a DuckDB connection"
    assert min(flock_ex_linenos) < max(c.lineno for c in connects), (
        "connect_write opens the DuckDB connection before/without taking the "
        "exclusive lock — the write connection escapes the serializer."
    )
    for c in connects:
        assert not _has_read_only_true(c), (
            "connect_write opened the write connection with read_only=True — "
            "that is not a writer; the single-writer path is broken."
        )


def test_db_lock_connect_read_is_read_only_not_a_writer():
    """PLACE (static): ``connect_read`` opens the graph with ``read_only=True``.

    Invariant: readers are not writers — read-only connections may run
    concurrently with the single writer without contending for the lock
    (``runtime/db_lock.py`` docstring). Guards against ``connect_read`` silently
    becoming a second write path (dropping ``read_only=True``), which would
    admit a concurrent writer and violate single-writer place.
    """
    tree = ast.parse(DB_LOCK_FILE.read_text(encoding="utf-8"))
    cr = _funcdef(tree, "connect_read")
    connects = list(_duckdb_connect_calls(cr))
    assert connects, "connect_read no longer opens a DuckDB connection"
    assert all(_has_read_only_true(c) for c in connects), (
        "connect_read opened a connection without read_only=True — a reader that "
        "can write is a second writer; single-writer place is broken."
    )


def test_place_graph_write_serializes_through_single_writer_lock(tmp_path):
    """PLACE (behavioral): while one ``connect_write`` holds the graph, a second
    writer cannot acquire it — the single serialized writer is real, not prose.

    Invariant: DuckDB single-writer via ``runtime/db_lock.py``. This exercises
    the *serialization behavior* (no existing test raises ``WriteLockTimeout``
    on contention — it is only mentioned in a docstring), then proves the write
    committed and is visible to a fresh writer after release. Hermetic: a temp
    DuckDB file under ``tmp_path``; the real graph is never opened.

    Guards against: a lock that does not actually block a second writer (the
    corruption path the invariant exists to foreclose).
    """
    from runtime.db_lock import WriteLockTimeout, connect_write, is_locked

    db = str(tmp_path / "graph.duckdb")

    con = connect_write(db, purpose="spr02-holder")
    try:
        con.execute("CREATE TABLE t (x INTEGER)")
        con.execute("INSERT INTO t VALUES (42)")
        assert is_locked(db) is True, "lock not held while a writer is active"
        with pytest.raises(WriteLockTimeout):
            connect_write(db, timeout_s=0.5, poll_interval_s=0.05, purpose="spr02-contender")
    finally:
        con.close()

    # After release, a fresh writer acquires and sees the committed place-state.
    con2 = connect_write(db, purpose="spr02-verify")
    try:
        assert con2.execute("SELECT x FROM t").fetchone()[0] == 42
    finally:
        con2.close()


# ---------------------------------------------------------------------------
# M3 · Provenance floor — hash-only cross-graph evidence (values, immutable)
# ---------------------------------------------------------------------------


def test_discovered_rule_is_immutable_value():
    """VALUES: a ``DiscoveredRule`` (and its propagation event) is an immutable
    frozen value — its identity is not braided with time.

    Hickey framing that no existing test makes: the artifact that crosses the
    personal→shared boundary is a *value*. Guards against making
    ``DiscoveredRule`` mutable (place), which would let evidence be swapped in
    place after construction/validation — smuggling raw content past the
    hash-only floor.
    """
    from substrate.cross_graph_writer import DiscoveredRule, RulePropagationEvent, propose_rule

    assert DiscoveredRule.__dataclass_params__.frozen is True
    assert RulePropagationEvent.__dataclass_params__.frozen is True

    rule = propose_rule(
        proposer_user_id="u-1",
        rule_kind="skill_patch",
        rule_payload="Lukin papers = Tier-1",
        supporting_chunks=[b"private chunk"],
        strength_score=0.7,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        rule.strength_score = 0.0  # type: ignore[misc]


def test_cross_graph_evidence_is_hash_only_provenance_floor():
    """PLACE/provenance: the cross-graph writer refuses to propagate a rule
    whose ``evidence`` holds any non-hash value.

    Invariant: §13.3 "architecturally incapable of leaking" — the structural
    ``_HASH_PATTERN`` check in ``cross_graph_writer/queue.py``. Part of the
    values-over-place floor: only a hash (a value about content) crosses the
    boundary, never the mutable place the content lived in.

    NOTE for SPR-07 reconciliation — this EXTENDS/CITES, does not duplicate:
    the canonical behavioral coverage is
    ``tests/test_cross_graph_writer.py::test_enqueue_refuses_non_hash_evidence``
    and ``tests/test_architectural_incapability.py::test_attacker_constructing_rule_with_raw_evidence_is_refused``.
    Here the same mechanism is asserted as the decomplecting provenance floor.
    """
    from substrate.cross_graph_writer import (
        CrossGraphWriterQueue,
        DiscoveredRule,
        RulePropagationEventKind,
        enqueue_for_propagation,
        propose_rule,
    )
    from substrate.cross_graph_writer.queue import _HASH_PATTERN

    q = CrossGraphWriterQueue()

    good = propose_rule(
        proposer_user_id="u-1",
        rule_kind="skill_patch",
        rule_payload="x",
        supporting_chunks=[b"raw private chunk A", b"raw private chunk B"],
        strength_score=0.6,
    )
    for entry in good.evidence:
        assert _HASH_PATTERN.match(entry), "propose_rule stored a non-hash evidence entry"
    ok = enqueue_for_propagation(q, good)
    assert ok.kind == RulePropagationEventKind.ENQUEUED
    assert good in q.pending

    leaky = DiscoveredRule(
        rule_id="rule-attacker",
        proposer_user_id="u-1",
        rule_kind="skill_patch",
        rule_payload="x",
        evidence=("this is raw private content, not a sha256 hash",),
        strength_score=0.9,
    )
    refused = enqueue_for_propagation(q, leaky)
    assert refused.kind == RulePropagationEventKind.REFUSED_NON_HASH_EVIDENCE
    assert leaky not in q.pending, "a raw-content rule reached the propagation queue — leak floor breached"
