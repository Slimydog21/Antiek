"""Local-only capacity harness for the Antiek substrate API (SPR-09).

Measures how the single-writer FastAPI service degrades as concurrent
authenticated READ traffic plus investigation STARTS scale up. It NEVER
talks to prod (api.antiek.ai) or any non-loopback host: every request goes
to a server this harness launches itself on 127.0.0.1, pointed at a fresh
temp DuckDB + temp event-log dir. Read-only against prod by construction —
prod is not contacted at all; the local server is a faithful stand-in
(same app factory, workers=1, operator-auth middleware active).

What one run (concurrency level N) does:

- N reader workers, each with its own ``httpx.Client``, round-robin over
  GET /health, GET /speak/projects, GET /speak/projects/{project_id},
  GET /trajectory?limit=20 for the wall-clock window, always carrying
  ``Authorization: Bearer <ANTIEK_OPERATOR_TOKEN>`` (that token is set in
  the child so the operator-auth middleware enforces it on every request).
- M start workers (``--starts``, default 2) POST /investigations with
  ``{"question": "capacity probe question <n>", "max_sub_questions": 1}``
  for the same window. Because the served app is built with
  ``register_providers=False`` (and ``register_wrestling=False``), the
  Loop-1 orchestrator is NOT subscribed: POST /investigations measures
  only the ADMISSION path — ACU capacity gate + start event + ACU commit —
  with no LLM dispatch anywhere on the measured paths.
- Per request timeout is 330s so a 300s write-lock stall is OBSERVED in
  the latency numbers, not hidden by a client timeout.
- Server CPU/RSS are sampled with ``ps -o %cpu=,rss= -p <pid>`` every
  ~0.25s (stdlib subprocess; works on macOS and Linux).

Write-lock instrumentation (HARNESS-ONLY; never in product code):

- WAIT time: before importing any substrate/app module, this module
  replaces ``runtime.db_lock.connect_write`` with a wrapper that times
  the call (``time.monotonic`` before/after — gate wait + flock wait +
  open, i.e. call-to-return) and appends one JSON line
  ``{"purpose", "wait_s", "ok"}`` to the ``--wait-log`` file (open/
  append/close per record, guarded by a ``threading.Lock``). It MUST be
  installed before ``import interfaces.research.api.app`` because many
  modules do ``from runtime.db_lock import connect_write`` and would
  otherwise bind the unwrapped function. Recorded in the JSON as
  ``write_lock_wait_source``.
- HOLD time: no second measurement is invented. The parent reads
  ``runtime/db_lock``'s own ``write_log`` table (``duration_s`` is
  acquisition-to-close, stamped on connection close) AFTER the server
  has exited, via a read-only DuckDB connection (read-write fallback if
  a WAL from a hard kill blocks read-only open; the serve child
  checkpoints on graceful exit because DuckDB 1.5.4 cannot replay a WAL
  holding schema ALTERs cross-process). Rows are attributed to a run by
  their ``logged_at`` wall-clock window. Recorded in the JSON as
  ``write_lock_hold_source``.

Isolation: the child scrubs ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` /
``XAI_API_KEY`` and every ``*_API_KEY`` from its environment before any
import, sets ``ANTIEK_DUCKDB_PATH`` / ``ANTIEK_RESEARCH_EVENTS_DIR`` /
``ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT=soft`` / ``ANTIEK_OPERATOR_TOKEN``,
and also drops ``PYTEST_CURRENT_TEST`` so the child does not silently
change db_lock behaviour (warm-writer keepalive, store guard) by thinking
it runs under pytest.

Read latency: ``p50_ms``/``p95_ms``/``p99_ms`` cover 2xx reads only
(``latency_basis``). Failed reads count in ``requests_failed`` and their
latency is reported separately as ``failed_p95_ms``.

Exit codes: 0 success; 2 setup/readiness/warm-up failure (naming the
path and status); 1 if any run completed zero read requests — the
stub-theater guard. The JSON is still written on exit 1.

Usage (parent):

    python benchmarks/capacity_probe.py --concurrency 1,5,25 \
        [--starts 2] [--duration-s 10] [--requests-per-worker N] \
        [--out benchmarks/results/cap_before.json]

Usage (child, launched by the parent — hidden):

    python benchmarks/capacity_probe.py --serve --port P --db PATH \
        --wait-log PATH
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import platform
import secrets
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The four read paths, round-robined per worker. {project_id} is filled
# from the seeded cap-probe project. The warm-up pass asserts every one
# of these answers 2xx with the bearer token before any measurement.
_READ_PATH_TEMPLATES: tuple[str, ...] = (
    "/health",
    "/speak/projects",
    "/speak/projects/{project_id}",
    "/trajectory?limit=20",
)

REQUEST_TIMEOUT_S = 330.0  # > the 300s db_lock timeout: observe stalls, don't hide them
DEFAULT_DURATION_S = 10.0
DEFAULT_START_WORKERS = 2
PS_SAMPLE_INTERVAL_S = 0.25
READINESS_TIMEOUT_S = 60.0
SERVER_STOP_GRACE_S = 15.0
SCHEMA_VERSION = 1

WRITE_LOCK_WAIT_SOURCE = (
    "harness wrapper around runtime.db_lock.connect_write (call-to-return)"
)
WRITE_LOCK_HOLD_SOURCE = "write_log.duration_s"

# Env keys scrubbed from the serve child before any import so nothing in
# the child can reach a model provider. The *_API_KEY suffix rule covers
# the three named keys; they are listed explicitly to match the contract.
_PROVIDER_KEY_ENV_SUFFIX = "_API_KEY"
_NAMED_PROVIDER_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY")
# Dropped so a harness spawned from inside pytest does not inherit
# pytest-mode behaviour in db_lock (keepalive off / store guard on).
_PYTEST_ENV_KEYS = ("PYTEST_CURRENT_TEST", "ANTIEK_ENFORCE_TEST_STORE_ISOLATION")


class SetupError(RuntimeError):
    """Readiness/seed/warm-up failure -> exit code 2."""


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_capacity_probe.py)
# ---------------------------------------------------------------------------


def percentile(values: Sequence[float], p: float) -> float | None:
    """Nearest-rank percentile of ``values`` (tolerates unsorted input).

    Returns None for an empty sequence. For [1..100]: p50=50, p95=95,
    p99=99 (rank = ceil(p/100 * n), 1-indexed).
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    return float(ordered[min(rank, len(ordered)) - 1])


def _is_2xx(status: object) -> bool:
    return isinstance(status, int) and 200 <= status < 300


def read_latency_summary(reads: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Read-latency fields for one run.

    ``p50_ms``/``p95_ms``/``p99_ms`` cover 2xx reads only (``latency_basis``
    says so), because a fast 503 is not a served read. A failed read is
    still reported: it counts in ``requests_failed``, and its latency goes
    into ``failed_p95_ms``, so a run full of failures cannot show the same
    percentiles as a clean one without the JSON saying so.
    """
    ok = [float(obs["ms"]) for obs in reads if _is_2xx(obs["status"])]
    failed = [float(obs["ms"]) for obs in reads if not _is_2xx(obs["status"])]
    return {
        "requests_completed": len(ok),
        "requests_failed": len(failed),
        "latency_basis": "2xx_reads_only",
        "p50_ms": percentile(ok, 50),
        "p95_ms": percentile(ok, 95),
        "p99_ms": percentile(ok, 99),
        "failed_p95_ms": percentile(failed, 95),
    }


def parse_ps_line(line: str) -> tuple[float, float] | None:
    """Parse one ``ps -o %cpu=,rss= -p <pid>`` output line.

    Returns (cpu_percent, rss_mb) — rss arrives in KiB on both macOS and
    Linux — or None when the line is empty/garbage (e.g. process gone).
    """
    parts = line.split()
    if len(parts) != 2:
        return None
    try:
        cpu = float(parts[0])
        rss_mb = float(parts[1]) / 1024.0
    except ValueError:
        return None
    return (cpu, rss_mb)


def parse_wait_log_text(text: str) -> list[dict[str, Any]]:
    """Parse wait-log JSONL into records, skipping blank/malformed lines.

    A valid record is a JSON object carrying a numeric ``wait_s``.
    """
    records: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("wait_s"), (int, float)):
            records.append(parsed)
    return records


def parse_wait_log_file(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    return parse_wait_log_text(p.read_text(encoding="utf-8"))


def parse_concurrency_spec(spec: str) -> list[int]:
    """Parse the --concurrency CLI value, e.g. "1,5,25" -> [1, 5, 25]."""
    levels: list[int] = []
    for chunk in spec.split(","):
        piece = chunk.strip()
        if not piece:
            continue
        try:
            level = int(piece)
        except ValueError as exc:
            raise ValueError(f"invalid concurrency level {piece!r} in {spec!r}") from exc
        if level < 1:
            raise ValueError(f"concurrency level must be >= 1, got {level}")
        levels.append(level)
    if not levels:
        raise ValueError("at least one concurrency level is required")
    return levels


def exit_code_for_runs(runs: Sequence[dict[str, Any]]) -> int:
    """Stub-theater guard: a run that completed zero reads is not a
    measurement. Any such run -> exit 1 (JSON is still written)."""
    if any(int(r.get("requests_completed", 0)) == 0 for r in runs):
        return 1
    return 0


# ---------------------------------------------------------------------------
# Environment scrubbing (parent builds the child env; child re-scrubs
# before any import — the guarantee holds no matter how --serve is begun)
# ---------------------------------------------------------------------------


def scrub_provider_env() -> None:
    """Remove every provider key (and pytest markers) from os.environ."""
    for key in list(os.environ):
        if key.endswith(_PROVIDER_KEY_ENV_SUFFIX) or key in _NAMED_PROVIDER_KEYS:
            del os.environ[key]
    for key in _PYTEST_ENV_KEYS:
        os.environ.pop(key, None)


def build_child_env(token: str) -> dict[str, str]:
    """Child process env: parent env minus provider keys / pytest markers,
    plus the one-time operator bearer token."""
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.endswith(_PROVIDER_KEY_ENV_SUFFIX) or key in _NAMED_PROVIDER_KEYS:
            continue
        if key in _PYTEST_ENV_KEYS:
            continue
        env[key] = value
    env["ANTIEK_OPERATOR_TOKEN"] = token
    return env


# ---------------------------------------------------------------------------
# Serve mode (child). Env FIRST, then imports — the ordering is the point.
# ---------------------------------------------------------------------------


def _install_wait_instrumentation(wait_log_path: str) -> None:
    """Wrap runtime.db_lock.connect_write with a call-to-return timer.

    Harness-only observability. Must run before importing any module that
    does ``from runtime.db_lock import connect_write`` (notably
    interfaces.research.api.app) so every import-time binding captures the
    wrapper. One JSON line per call is appended to the wait log; the file
    is opened per record under a lock (append-atomic enough for one
    writer process; every thread funnels through the same lock).
    """
    import runtime.db_lock as db_lock_module

    original = db_lock_module.connect_write
    file_lock = threading.Lock()

    def timed_connect_write(
        db_path: str,
        *,
        timeout_s: float = db_lock_module.DEFAULT_TIMEOUT_S,
        poll_interval_s: float = 0.25,
        purpose: str = "",
        close_log_max_wait_s: float = 0.25,
    ) -> Any:
        started = time.monotonic()
        ok = False
        try:
            con = original(
                db_path,
                timeout_s=timeout_s,
                poll_interval_s=poll_interval_s,
                purpose=purpose,
                close_log_max_wait_s=close_log_max_wait_s,
            )
            ok = True
            return con
        finally:
            record = {
                "purpose": purpose,
                "wait_s": time.monotonic() - started,
                "ok": ok,
            }
            with file_lock, open(wait_log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")

    db_lock_module.connect_write = timed_connect_write


def _serve(port: int, db_path: str, wait_log_path: str) -> None:
    """Hidden child sub-mode: run the isolated uvicorn server."""
    scrub_provider_env()
    token = os.environ.get("ANTIEK_OPERATOR_TOKEN", "").strip()
    if not token:
        print("cap-probe --serve: ANTIEK_OPERATOR_TOKEN missing", file=sys.stderr)
        raise SystemExit(2)

    db_path = os.path.abspath(db_path)
    events_dir = os.path.join(os.path.dirname(db_path), "events")
    os.environ["ANTIEK_DUCKDB_PATH"] = db_path
    os.environ["ANTIEK_RESEARCH_EVENTS_DIR"] = events_dir
    os.environ["ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT"] = "soft"
    os.makedirs(events_dir, exist_ok=True)

    # Standalone --serve must work without a preset PYTHONPATH.
    repo_root = str(Path(__file__).resolve().parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    # Instrument BEFORE any substrate/app import (see docstring).
    _install_wait_instrumentation(wait_log_path)

    import substrate.graph as graph

    graph.ensure_initialized(db_path)

    # Heavy import; the app module also builds a default app instance at
    # module scope, which cannot dispatch anything on its own (no events
    # flow on that instance's bus). Re-scrub afterwards so no .env keys
    # its boot may have loaded linger in the child environment.
    import interfaces.research.api.app as app_module

    scrub_provider_env()

    app = app_module.create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )

    # Checkpoint when the app shuts down gracefully. uvicorn 0.49
    # re-raises the captured SIGTERM right after graceful shutdown (exit
    # code -15 is its NORMAL exit), which kills the process inside
    # Server.run() — a try/finally around run() never executes. An app
    # shutdown handler runs during the graceful drain, before that
    # re-raise, and flushes the WAL so the parent's post-mortem read
    # works (DuckDB 1.5.4 cannot replay a WAL holding schema ALTERs
    # cross-process).
    def _checkpoint_on_shutdown() -> None:
        _checkpoint_best_effort(db_path)

    app.router.add_event_handler("shutdown", _checkpoint_on_shutdown)

    import uvicorn

    print(f"[cap-probe-serve] listening on 127.0.0.1:{port}", file=sys.stderr, flush=True)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        workers=1,
        log_level="warning",
        lifespan="on",
    )
    try:
        uvicorn.Server(config).run()
    finally:
        # Backup for non-signal exits; a no-op after the shutdown handler.
        _checkpoint_best_effort(db_path)


def _checkpoint_best_effort(db_path: str) -> None:
    """Flush the WAL after graceful shutdown so post-mortem reads work."""
    try:
        import duckdb

        con = duckdb.connect(db_path)
        try:
            con.execute("CHECKPOINT")
        finally:
            con.close()
    except Exception as exc:
        print(
            f"[cap-probe-serve] post-shutdown checkpoint failed: {exc}",
            file=sys.stderr,
            flush=True,
        )


# ---------------------------------------------------------------------------
# Parent: server lifecycle, load generation, resource sampling
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _ServerSampler:
    """Samples the server's %cpu + RSS via ps every PS_SAMPLE_INTERVAL_S."""

    def __init__(self, pid: int) -> None:
        self._pid = pid
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self.samples: list[tuple[float, float]] = []

    def _loop(self) -> None:
        while not self._stop.is_set():
            line = ""
            try:
                result = subprocess.run(
                    ["ps", "-o", "%cpu=,rss=", "-p", str(self._pid)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                line = result.stdout.strip()
            except (subprocess.SubprocessError, OSError):
                line = ""
            parsed = parse_ps_line(line)
            if parsed is not None:
                self.samples.append(parsed)
            self._stop.wait(PS_SAMPLE_INTERVAL_S)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5.0)

    def cpu_mean(self) -> float | None:
        if not self.samples:
            return None
        return statistics.fmean(cpu for cpu, _ in self.samples)

    def rss_max_mb(self) -> float | None:
        if not self.samples:
            return None
        return max(rss for _, rss in self.samples)


class _QuestionCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._n = 0

    def next(self) -> int:
        with self._lock:
            self._n += 1
            return self._n


def _reader_worker(
    base_url: str,
    headers: dict[str, str],
    urls: Sequence[str],
    deadline: float,
    cap: int | None,
) -> list[dict[str, Any]]:
    """One reader worker: one httpx.Client, round-robin reads until the
    wall-clock deadline (or per-worker request cap). Returns observations
    [{"path", "status", "ms"}]; transport errors get status "error:<Type>"."""
    import httpx

    observations: list[dict[str, Any]] = []
    turn = 0
    with httpx.Client(
        base_url=base_url, headers=headers, timeout=REQUEST_TIMEOUT_S
    ) as client:
        while time.monotonic() < deadline:
            if cap is not None and len(observations) >= cap:
                break
            url = urls[turn % len(urls)]
            turn += 1
            started = time.monotonic()
            try:
                resp = client.get(url)
                status: str | int = resp.status_code
            except httpx.HTTPError as exc:
                status = f"error:{type(exc).__name__}"
            observations.append(
                {
                    "path": url,
                    "status": status,
                    "ms": (time.monotonic() - started) * 1000.0,
                }
            )
    return observations


def _start_worker(
    base_url: str,
    headers: dict[str, str],
    deadline: float,
    cap: int | None,
    counter: _QuestionCounter,
) -> list[dict[str, Any]]:
    """One start worker: POSTs investigation starts for the same window."""
    import httpx

    observations: list[dict[str, Any]] = []
    with httpx.Client(
        base_url=base_url, headers=headers, timeout=REQUEST_TIMEOUT_S
    ) as client:
        while time.monotonic() < deadline:
            if cap is not None and len(observations) >= cap:
                break
            body = {
                "question": f"capacity probe question {counter.next()}",
                "max_sub_questions": 1,
            }
            started = time.monotonic()
            try:
                resp = client.post("/investigations", json=body)
                status: str | int = resp.status_code
            except httpx.HTTPError as exc:
                status = f"error:{type(exc).__name__}"
            observations.append(
                {
                    "path": "/investigations",
                    "status": status,
                    "ms": (time.monotonic() - started) * 1000.0,
                }
            )
    return observations


def _wait_until_ready(
    proc: subprocess.Popen[bytes],
    client: Any,
    deadline: float,
    stderr_path: Path,
) -> None:
    """Poll GET /health until 200. SetupError (exit 2) on timeout/child
    death, printing the child's stderr tail."""
    last_error = "no attempt"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SetupError(
                f"server child exited early (rc={proc.returncode}):\n"
                f"{_stderr_tail(stderr_path)}"
            )
        try:
            resp = client.get("/health")
            if resp.status_code == 200:
                return
            last_error = f"/health -> {resp.status_code}"
        except Exception as exc:  # httpx errors while server boots
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.25)
    raise SetupError(
        f"server not ready within {READINESS_TIMEOUT_S:.0f}s ({last_error}):\n"
        f"{_stderr_tail(stderr_path)}"
    )


def _stderr_tail(stderr_path: Path, lines: int = 40) -> str:
    try:
        content = stderr_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return f"<unreadable log: {stderr_path}>"
    return "\n".join(content.splitlines()[-lines:])


def _stop_server(proc: subprocess.Popen[bytes]) -> dict[str, Any]:
    """SIGTERM, wait out the grace period, then SIGKILL. Returns exit info.

    Note: uvicorn 0.49 re-raises the captured SIGTERM after its graceful
    drain, so returncode -15 is the EXPECTED normal exit, not a hard
    kill; ``had_to_sigkill`` records the parent-side fact instead.
    """
    had_to_sigkill = False
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=SERVER_STOP_GRACE_S)
        except subprocess.TimeoutExpired:
            had_to_sigkill = True
            proc.kill()
            # kill is final; the wait is belt-and-braces only
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=10)
    return {"returncode": proc.returncode, "had_to_sigkill": had_to_sigkill}


def _datetime_epoch(value: Any) -> float | None:
    """Epoch seconds for a DuckDB timestamp (naive values are local)."""
    if not isinstance(value, datetime):
        return None
    return value.timestamp()


def _analyze_write_log(
    db_path: str,
    window_start_epoch: float,
    window_end_epoch: float,
) -> tuple[float | None, int | None, int | None, str | None]:
    """Hold-time p95 (ms) + row count over the run's logged_at window, plus
    the table's total row count. Read-only open after server exit; falls
    back to read-write when a hard kill left a WAL read-only cannot replay.
    If neither open works, returns (None, None, None, error) — the harness
    reports the gap instead of crashing."""
    import duckdb

    window_lo = window_start_epoch - 0.5
    window_hi = window_end_epoch + 25.0
    con: Any = None
    try:
        try:
            con = duckdb.connect(db_path, read_only=True)
        except Exception:
            con = duckdb.connect(db_path)
        rows = con.execute(
            "SELECT log_id, duration_s, logged_at FROM write_log ORDER BY log_id"
        ).fetchall()
    except Exception as exc:
        return None, None, None, f"{type(exc).__name__}: {exc}"
    finally:
        if con is not None:
            con.close()

    durations: list[float] = []
    for _log_id, duration_s, logged_at in rows:
        epoch = _datetime_epoch(logged_at)
        if epoch is None or not window_lo <= epoch <= window_hi:
            continue
        durations.append(float(duration_s) * 1000.0)
    hold_p95 = percentile(durations, 95)
    return hold_p95, len(durations), len(rows), None


def _run_level(
    concurrency: int,
    starts: int,
    duration_s: float,
    requests_per_worker: int | None,
) -> dict[str, Any]:
    """One concurrency level: fresh temp dir, fresh server, seed, warm up,
    measure, stop, analyze. Raises SetupError on readiness/seed/warm-up
    failure (exit 2)."""
    import httpx

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"cap-probe-n{concurrency}-"))
    db_path = str(tmp_dir / "antiek.duckdb")
    wait_log_path = str(tmp_dir / "wait_log.jsonl")
    stderr_path = tmp_dir / "server.stderr.log"
    token = secrets.token_hex(24)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {token}"}

    keep_dir = False
    proc: subprocess.Popen[bytes] | None = None
    try:
        with stderr_path.open("wb") as stderr_file:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--serve",
                    "--port",
                    str(port),
                    "--db",
                    db_path,
                    "--wait-log",
                    wait_log_path,
                ],
                env=build_child_env(token),
                stdout=subprocess.DEVNULL,
                stderr=stderr_file,
            )

        with httpx.Client(
            base_url=base_url, headers=headers, timeout=10.0
        ) as control_client:
            _wait_until_ready(proc, control_client, time.monotonic() + READINESS_TIMEOUT_S,
                              stderr_path)

            # Seed once per server.
            seed_resp = control_client.post(
                "/speak/projects",
                json={"title": "cap-probe", "publish_intent": "private_never_published"},
            )
            if seed_resp.status_code not in range(200, 300):
                raise SetupError(
                    f"seed POST /speak/projects -> {seed_resp.status_code}: "
                    f"{seed_resp.text[:300]}"
                )
            project_id = str(seed_resp.json()["project_id"])
            read_urls = [tpl.format(project_id=project_id) for tpl in _READ_PATH_TEMPLATES]

            # Warm-up: every read path must answer 2xx with the bearer.
            for url in read_urls:
                resp = control_client.get(url)
                if resp.status_code not in range(200, 300):
                    raise SetupError(
                        f"warm-up GET {url} -> {resp.status_code} "
                        f"(body: {resp.text[:200]})"
                    )
        # Control client closed: no keep-alive connections outlive the run.

        baseline_wait_lines = len(parse_wait_log_file(wait_log_path))
        run_start_mono = time.monotonic()
        run_start_wall = time.time()
        deadline = run_start_mono + duration_s

        sampler = _ServerSampler(proc.pid)
        sampler.start()

        counter = _QuestionCounter()
        worker_count = max(1, concurrency) + starts
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            read_futures = [
                pool.submit(
                    _reader_worker, base_url, headers, read_urls, deadline,
                    requests_per_worker,
                )
                for _ in range(concurrency)
            ]
            start_futures = [
                pool.submit(
                    _start_worker, base_url, headers, deadline,
                    requests_per_worker, counter,
                )
                for _ in range(starts)
            ]
            read_results = [fut.result() for fut in read_futures]
            start_results = [fut.result() for fut in start_futures]

        run_end_mono = time.monotonic()
        run_end_wall = time.time()
        sampler.stop()

        server_exit = _stop_server(proc)
        proc = None

        reads = [obs for worker in read_results for obs in worker]
        starts_obs = [obs for worker in start_results for obs in worker]

        read_summary = read_latency_summary(reads)
        health_latencies = [
            obs["ms"] for obs in reads
            if obs["path"] == "/health" and isinstance(obs["status"], int)
        ]
        start_latencies = [
            obs["ms"] for obs in starts_obs
            if isinstance(obs["status"], int) and 200 <= obs["status"] < 300
        ]

        def status_counts(observations: list[dict[str, Any]]) -> dict[str, int]:
            counts: dict[str, int] = {}
            for obs in observations:
                key = str(obs["status"])
                counts[key] = counts.get(key, 0) + 1
            return dict(sorted(counts.items()))

        starts_completed = len(start_latencies)

        wait_rows = parse_wait_log_file(wait_log_path)[baseline_wait_lines:]
        wait_p95 = percentile([float(r["wait_s"]) * 1000.0 for r in wait_rows], 95)
        hold_p95, write_log_rows, write_log_rows_total, wl_error = _analyze_write_log(
            db_path, run_start_wall, run_end_wall
        )

        run: dict[str, Any] = {
            "concurrency": concurrency,
            "starts_workers": starts,
            **read_summary,
            "status_counts": {"reads": status_counts(reads),
                              "starts": status_counts(starts_obs)},
            "health_p95_ms": percentile(health_latencies, 95),
            "starts_completed": starts_completed,
            "start_p95_ms": percentile(start_latencies, 95),
            "server_cpu_percent": sampler.cpu_mean(),
            "server_rss_mb_max": sampler.rss_max_mb(),
            "write_lock_wait_p95_ms": wait_p95,
            "write_lock_hold_p95_ms": hold_p95,
            "write_log_rows": write_log_rows,
            "duration_s": run_end_mono - run_start_mono,
            # provenance / debugging extras
            "port": port,
            "project_id": project_id,
            "wait_entries": len(wait_rows),
            "wait_entries_ok": sum(1 for r in wait_rows if r.get("ok")),
            "wait_entries_failed": sum(1 for r in wait_rows if not r.get("ok")),
            "write_log_rows_total": write_log_rows_total,
            "write_log_read_error": wl_error,
            "server_exit": server_exit,
        }
        _print_summary(run)
        return run
    except Exception:
        keep_dir = True
        raise
    finally:
        if proc is not None:
            _stop_server(proc)
        if not keep_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _print_summary(run: dict[str, Any]) -> None:
    print(
        "[cap-probe] N={concurrency} reads={requests_completed}ok/"
        "{requests_failed}fail p50/p95/p99={p50_ms}/{p95_ms}/{p99_ms}ms "
        "failed_p95={failed_p95_ms}ms "
        "health_p95={health_p95_ms}ms starts={starts_completed} "
        "start_p95={start_p95_ms}ms wait_p95={write_lock_wait_p95_ms}ms "
        "hold_p95={write_lock_hold_p95_ms}ms write_log_rows={write_log_rows} "
        "cpu={server_cpu_percent}% rss_max={server_rss_mb_max}MB "
        "dur={duration_s}s".format(**{k: _fmt(v) for k, v in run.items()}),
        flush=True,
    )


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return "unknown"


def _build_report(params: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "git_sha": _git_sha(),
        "generated_at": datetime.now(UTC).isoformat(),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "server": {
            "workers": 1,
            "register_providers": False,
            "register_wrestling": False,
            "bind": "127.0.0.1",
        },
        "write_lock_wait_source": WRITE_LOCK_WAIT_SOURCE,
        "write_lock_hold_source": WRITE_LOCK_HOLD_SOURCE,
        "params": params,
        "runs": runs,
    }


def _concurrency_arg(spec: str) -> list[int]:
    try:
        return parse_concurrency_spec(spec)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capacity_probe",
        description="Local-only capacity harness (see module docstring).",
    )
    parser.add_argument("--concurrency", type=_concurrency_arg, required=False,
                        default="1,5,25",
                        help="comma-separated concurrency levels (default 1,5,25)")
    parser.add_argument("--starts", type=int, default=DEFAULT_START_WORKERS,
                        help="concurrent investigation-start workers (default 2)")
    parser.add_argument("--duration-s", type=float, default=DEFAULT_DURATION_S,
                        help="wall-clock window per level in seconds (default 10)")
    parser.add_argument("--requests-per-worker", type=int, default=None,
                        help="optional per-worker request cap (default: none)")
    parser.add_argument("--out", default="benchmarks/results/cap.json",
                        help="output JSON path (parents created)")
    # Hidden child sub-mode.
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--db", default="", help=argparse.SUPPRESS)
    parser.add_argument("--wait-log", default="", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.serve:
        if not args.db or not args.wait_log or args.port <= 0:
            parser.error("--serve requires --port, --db and --wait-log")
        _serve(args.port, args.db, args.wait_log)
        return 0

    if args.starts < 0:
        parser.error("--starts must be >= 0")
    if args.duration_s <= 0:
        parser.error("--duration-s must be > 0")
    if args.requests_per_worker is not None and args.requests_per_worker < 1:
        parser.error("--requests-per-worker must be >= 1")

    params: dict[str, Any] = {
        "concurrency": args.concurrency,
        "starts": args.starts,
        "duration_s": args.duration_s,
        "requests_per_worker": args.requests_per_worker,
        "request_timeout_s": REQUEST_TIMEOUT_S,
        "out": args.out,
    }

    try:
        runs = [
            _run_level(level, args.starts, args.duration_s, args.requests_per_worker)
            for level in args.concurrency
        ]
    except SetupError as exc:
        print(f"capacity_probe: setup failure: {exc}", file=sys.stderr, flush=True)
        return 2

    report = _build_report(params, runs)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[cap-probe] wrote {out_path}", flush=True)
    return exit_code_for_runs(runs)


if __name__ == "__main__":
    sys.exit(main())
