"""Note-taker replay recovery: yield to a queued writer, back off, aggregate.

Prod 2026-10-01: `interfaces/research/api/note_taking.py::start_replay_recovery`
retried every investigation every poll and printed one stderr line per failure,
with no backoff and no awareness that another process was queued for the DuckDB
write lock. Across a multi-hour `arxiv_oai_sync --bulk` pass (which holds the
file ~15s of every 15.5s) that produced 2,624 Binder/IO lines in 29h while the
recovery made NO projection progress, and `/health` answered "ok" throughout.

These tests pin the three properties that was missing, and the state dict the
health surface now publishes.
"""

from __future__ import annotations

import inspect
import threading
import time
from types import SimpleNamespace

import pytest

from interfaces.research.api import note_taking
from runtime import db_lock


class _StubService:
    def __init__(self, db_path: str, events_dir: str, behaviour):
        self.db_path = db_path
        self.events_dir = events_dir
        self._behaviour = behaviour
        self.calls: list[str] = []

    def catch_up(self, investigation_id: str):
        self.calls.append(investigation_id)
        self._behaviour(investigation_id)
        return []


@pytest.fixture()
def worker_env(tmp_path, monkeypatch):
    """A stub replay service + one discovered investigation, wired like prod."""
    db = tmp_path / "graph.duckdb"
    db.write_text("")  # os.path.exists(service.db_path) must be true
    events = tmp_path / "events"
    events.mkdir()

    from substrate.graph import knowledge_event_projector

    monkeypatch.setattr(
        knowledge_event_projector, "discover_investigations", lambda root: ["inv-1"]
    )
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    return db, str(events)


def _start(monkeypatch, tmp_path, db, events, behaviour, **env):
    service = _StubService(str(db), events, behaviour)
    monkeypatch.setattr(note_taking, "_default_replay_service", lambda **_: service)
    monkeypatch.setenv("ANTIEK_NOTE_TAKER_REPLAY_LOCK_YIELD_S", "0")
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    state: dict = {}
    stop = threading.Event()
    kwargs: dict = {
        "db_path": str(db),
        "events_dir": events,
        "stop_event": stop,
        "poll_interval_s": 0.02,
    }
    # `state` is the capability under test. Passing it unconditionally would
    # make the pre-fix worker fail on a TypeError instead of on BEHAVIOUR, so a
    # red run would prove nothing about the yield/backoff/aggregation.
    if "state" in inspect.signature(note_taking.start_replay_recovery).parameters:
        kwargs["state"] = state
    thread = note_taking.start_replay_recovery(**kwargs)
    return service, state, stop, thread


def _settle(stop, thread):
    stop.set()
    thread.join(5)
    assert not thread.is_alive()


def test_recovery_waits_out_a_queued_writer_instead_of_failing_into_it(
    tmp_path, monkeypatch, worker_env
):
    """While a writer is queued the worker must NOT attempt a catch-up: each
    attempt inside the holder's window is the failure that filled stderr."""
    db, events = worker_env
    # The queued writer must be published BEFORE the worker starts, or its
    # first pass legitimately runs before there is anything to yield to.
    waiter = db_lock._register_write_waiter(str(db))
    try:
        service, state, stop, thread = _start(monkeypatch, tmp_path, db, events, lambda _id: None)
        try:
            # Give the worker several poll intervals with the writer queued.
            time.sleep(0.4)
            assert service.calls == [], (
                "the worker attempted a catch-up while a writer was queued: "
                f"{service.calls}"
            )
            assert state.get("status") == "waiting_for_writer"
        except BaseException:
            _settle(stop, thread)
            raise
    finally:
        db_lock._unregister_write_waiter(waiter)
    try:
        deadline = time.monotonic() + 3
        while not service.calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service.calls == ["inv-1"], "the worker never resumed after the writer withdrew"
        assert state.get("status") == "current"
    finally:
        _settle(stop, thread)


def test_recovery_backs_off_and_aggregates_failures(tmp_path, monkeypatch, worker_env, capsys):
    """A contended/stuck writer must not produce one log line per failure, and
    the retry rate must decay instead of running at poll speed forever."""
    db, events = worker_env

    def always_fail(_id: str) -> None:
        raise RuntimeError("Could not set lock on file: conflicting lock is held")

    service, state, stop, thread = _start(
        monkeypatch,
        tmp_path,
        db,
        events,
        always_fail,
        ANTIEK_NOTE_TAKER_REPLAY_BACKOFF_BASE_S=0.001,
        ANTIEK_NOTE_TAKER_REPLAY_BACKOFF_MAX_S=0.002,
        ANTIEK_NOTE_TAKER_REPLAY_LOG_INTERVAL_S=0.15,
    )
    try:
        time.sleep(0.8)
    finally:
        _settle(stop, thread)
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if "remains pending" in line]
    failures = len(service.calls)
    assert failures > 3, f"the worker barely ran; cannot judge aggregation ({failures} calls)"
    # The behavioural claim first: failures must not each cost a log line.
    assert len(lines) < failures / 2, (
        f"{failures} failures produced {len(lines)} log lines — not aggregated"
    )
    assert any("suppressed" in line for line in lines), (
        "the aggregated line must carry what it swallowed"
    )
    assert state.get("status") == "backoff"
    assert state.get("consecutive_barren_passes", 0) >= 2
    assert state.get("backoff_s", 0) > 0
    assert state.get("last_failure_class") == "RuntimeError"


def test_recovery_resets_backoff_after_a_success(tmp_path, monkeypatch, worker_env):
    """Backoff is a property of a barren run, not of the worker's lifetime."""
    db, events = worker_env
    remaining = {"failures": 3, "succeeded": False}

    def fail_then_succeed(_id: str) -> None:
        if remaining["failures"] > 0:
            remaining["failures"] -= 1
            raise RuntimeError("Could not set lock on file: conflicting lock is held")
        remaining["succeeded"] = True

    service, state, stop, thread = _start(
        monkeypatch,
        tmp_path,
        db,
        events,
        fail_then_succeed,
        ANTIEK_NOTE_TAKER_REPLAY_BACKOFF_BASE_S=0.02,
        ANTIEK_NOTE_TAKER_REPLAY_BACKOFF_MAX_S=0.05,
        ANTIEK_NOTE_TAKER_REPLAY_LOG_INTERVAL_S=60,
    )
    try:
        deadline = time.monotonic() + 5
        while not remaining["succeeded"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert remaining["succeeded"], "the stub never reached its success"
        deadline = time.monotonic() + 3
        while state.get("status") != "current" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert state.get("status") == "current"
        assert state.get("consecutive_barren_passes") == 0
        assert state.get("failures") == 0
    finally:
        _settle(stop, thread)


def test_recovery_state_dict_is_updated_in_place(tmp_path, monkeypatch, worker_env):
    """The caller publishes the dict to /health, so the worker must mutate it
    rather than replace it."""
    db, events = worker_env
    service, state, stop, thread = _start(monkeypatch, tmp_path, db, events, lambda _id: None)
    try:
        deadline = time.monotonic() + 3
        while not state and time.monotonic() < deadline:
            time.sleep(0.01)
        assert state, "the worker published nothing into the caller's dict"
        assert state is not None and "status" in state
    finally:
        _settle(stop, thread)


@pytest.mark.parametrize("reuse_app", [True, False], ids=["repeated-startup", "multiple-apps"])
def test_startup_recovery_logs_once_per_database_interval(
    monkeypatch, worker_env, capsys, reuse_app
):
    """Repeated production starts must not reset the database's log interval."""
    from interfaces.research.api.app import create_app

    db, events = worker_env
    alias = db.with_name("alias.duckdb")
    alias.symlink_to(db)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_NOTE_TAKER_REPLAY_LOCK_YIELD_S", "0")
    monkeypatch.setattr(note_taking, "_resolve_replay_tuning", lambda: (3600.0, 3600.0, 30.0))
    clock = [120.0]
    monkeypatch.setattr(
        note_taking, "time", SimpleNamespace(monotonic=lambda: clock[0], time=time.time)
    )

    barrier = None if reuse_app else threading.Barrier(6)
    synchronize = [True]

    def always_fail(_id):
        if barrier is not None and synchronize[0]:
            barrier.wait(5)
        raise RuntimeError("conflicting lock is held")

    service = _StubService(str(db), events, always_fail)

    def replay_service(**kwargs):
        instance = _StubService(kwargs.get("db_path") or str(db), events, always_fail)
        instance.calls = service.calls
        return instance

    monkeypatch.setattr(note_taking, "_default_replay_service", replay_service)
    original_start = note_taking.start_replay_recovery
    workers = []

    def observed_start(**kwargs):
        stop = kwargs["stop_event"]
        passed = threading.Event()
        original_wait = stop.wait

        def observed_wait(timeout=None):
            # The failure is logged and the report updated before this wait.
            passed.set()
            return original_wait(timeout)

        monkeypatch.setattr(stop, "wait", observed_wait)
        thread = original_start(**kwargs)
        workers.append((stop, thread, passed, kwargs["state"]))
        return thread

    monkeypatch.setattr(note_taking, "start_replay_recovery", observed_start)
    app = create_app(register_providers=False, register_wrestling=False)

    def start_replay(application, *, wait_for_pass=True):
        callbacks = [
            callback for callback in application.router.on_startup
            if callback.__name__ == "_recover_note_taker_replay"
        ]
        assert len(callbacks) == 1
        callbacks[0]()
        if wait_for_pass:
            assert workers[-1][2].wait(5), "recovery never finished its first pass"

    try:
        for index in range(6):
            if index and not reuse_app:
                monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(alias if index % 2 else db))
                app = create_app(register_providers=False, register_wrestling=False)
            start_replay(app, wait_for_pass=reuse_app)
        for _, _, passed, _ in workers:
            assert passed.wait(5), "recovery never finished its first pass"
        lines = [line for line in capsys.readouterr().err.splitlines() if "remains pending" in line]
        assert len(lines) == 1, f"six startup calls produced {len(lines)} log lines: {lines}"
        assert len(workers) == (1 if reuse_app else 6)
        assert len(service.calls) == len(workers)
        assert app.state.note_taker_recovery is workers[-1][3]
        assert all(thread.is_alive() for _, thread, _, _ in workers)

        if reuse_app:
            shutdown = next(
                callback for callback in app.router.on_shutdown
                if callback.__name__ == "_stop_note_taker_replay"
            )
            shutdown()
            assert not workers[0][1].is_alive()
            start_replay(app)
            assert len(workers) == 2, "a stopped worker must be restartable"
            assert app.state.note_taker_recovery is workers[-1][3]
            assert "remains pending" not in capsys.readouterr().err
        else:
            synchronize[0] = False
            clock[0] += 30.0
            app = create_app(register_providers=False, register_wrestling=False)
            start_replay(app)
            lines = [
                line for line in capsys.readouterr().err.splitlines() if "remains pending" in line
            ]
            assert len(lines) == 1
            assert "(+5 suppressed)" in lines[0]

            other_db = db.with_name("other.duckdb")
            other_db.write_text("")
            monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(other_db))
            app = create_app(register_providers=False, register_wrestling=False)
            start_replay(app)
            lines = [
                line for line in capsys.readouterr().err.splitlines() if "remains pending" in line
            ]
            assert len(lines) == 1, "a separate database must have its own log window"
            assert "suppressed" not in lines[0]
    finally:
        if barrier is not None:
            barrier.abort()
        # Retain every handle even on the red run, where app.state orphans five.
        for stop, thread, _, _ in workers:
            _settle(stop, thread)


def test_backoff_survives_a_pass_count_that_overflows_a_float() -> None:
    """The cap must not be the only thing between the worker and a crash.

    `base_s` is a float, so the multiplication converts the exponent's result to float and
    raises at exponent 1024. Before the clamp, a recovery worker that stayed barren long
    enough died instead of backing off:

        barren_passes=1024 -> 60.0
        barren_passes=1025 -> OverflowError: int too large to convert to float

    Reachable in roughly 17 hours of idling, because the sleep caps at 60s.
    """
    from interfaces.research.api.note_taking import _backoff_seconds

    assert _backoff_seconds(1, 1.0, 60.0) == 1.0
    assert _backoff_seconds(2, 1.0, 60.0) == 2.0
    assert _backoff_seconds(10, 1.0, 60.0) == 60.0

    for passes in (1024, 1025, 10_000, 10**6):
        assert _backoff_seconds(passes, 1.0, 60.0) == 60.0, passes
