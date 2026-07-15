"""Rendered-template EXECUTION tests for the deployed nightly backup script.

The PR #714 adversarial review found the load-bearing gap: nothing ever RAN
``infrastructure/ansible/templates/backup.sh.j2`` — a broken step meant zero
backups landing, silently. These tests render the template (jinja2, pinned in
the repo venv) and execute the rendered bash end-to-end against a scratch
state dir holding a REAL Antiek-schema DuckDB (built with the repo's own
``init_database_at_path``), with ``sudo``/``chown``/``rclone`` stubbed on PATH
(``rclone`` records every invocation and preserves the uploaded archive for
inspection; ``sudo -u X cmd`` just execs ``cmd`` — the privilege dance is the
host's concern, not the pipeline logic under test here).

Four mechanically-asserted behaviors:

  a. Happy path — exit 0, rclone upload invoked, archive payload sane,
     freshness marker written with the real row counts and readable by
     ``tools/backup_freshness.py``.
  b. Red-proof R1 — a sabotaged normalizer corrupts ``schema.sql`` between
     normalize and verify; the IMPORT-verify gate must exit non-zero and
     rclone must NEVER be invoked (upload blocked).
  c. Red-proof R2 — while a competing process holds the ``runtime/db_lock.py``
     flock (``<db>.write.lock``), the script must time out non-zero with a
     clear message and no upload; after release the same script succeeds.
  d. ``tools/backup_freshness.py`` — fresh marker → 0; stale/missing/invalid/
     future → non-zero one-line reason; ``--json`` shape; threshold override.
  e. Red-proof (logical truncation) — an all-empty (schema-only) source must
     be refused BEFORE export/upload unless ANTIEK_BACKUP_ALLOW_EMPTY=1 is
     set deliberately; with the override it succeeds with zero counts.
  f. ``--max-age-hours`` fail-closed — nan/inf/negative thresholds are
     rejected at parse time (NaN would silently disable the gate: every
     comparison against NaN is False, so any stale marker would read FRESH).

Nothing here is skip-gated: jinja2 and duckdb are hard imports (a missing
dep fails collection loudly), and every case asserts exit codes + artifacts.
"""

from __future__ import annotations

import fcntl
import getpass
import json
import os
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb  # noqa: F401 — hard requirement: the backup pipeline is DuckDB; fail loudly if absent
import jinja2
import jinja2.meta
import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO / "infrastructure" / "ansible" / "templates" / "backup.sh.j2"
FRESHNESS_TOOL = REPO / "tools" / "backup_freshness.py"

# Every {{ var }} the template consumes, enumerated. The render helper uses
# StrictUndefined AND cross-checks this set against jinja2.meta, so a new
# template variable fails these tests loudly instead of rendering empty.
TEMPLATE_VARS = frozenset(
    {
        "ansible_managed",
        "backup_cron_hour",
        "backup_cron_minute",
        "antiek_state_dir",
        "backup_bucket_name",
        "backup_retention_days",
        "antiek_user",
        "antiek_install_dir",
    }
)

_SEED_COUNTS = {"documents": 1, "chunks": 1, "nodes": 2}


@dataclass(frozen=True)
class Harness:
    """One fully-wired scratch deployment of the rendered backup script."""

    script: Path
    state_dir: Path
    staging_root: Path
    lock_file: Path
    marker: Path
    rclone_log: Path
    rclone_keep: Path
    env: dict[str, str]


def _render_template(state_dir: Path, install_dir: Path) -> str:
    source = TEMPLATE_PATH.read_text()
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    declared = jinja2.meta.find_undeclared_variables(env.parse(source))
    assert declared == set(TEMPLATE_VARS), (
        f"backup.sh.j2 variable set changed: template uses {sorted(declared)}, "
        f"tests supply {sorted(TEMPLATE_VARS)} — update TEMPLATE_VARS deliberately"
    )
    return env.from_string(source).render(
        ansible_managed="rendered by tests/test_backup_deployed_script.py",
        backup_cron_hour="3",
        backup_cron_minute="0",
        antiek_state_dir=str(state_dir),
        backup_bucket_name="test-bucket",
        backup_retention_days="14",
        antiek_user=getpass.getuser(),
        antiek_install_dir=str(install_dir),
    )


def _seed_state_dir(state_dir: Path, *, seed_rows: bool = True) -> None:
    """A real small Antiek-schema DB + an event-log file, via the repo's own helpers.

    ``seed_rows=False`` leaves the schema intact but every table at zero rows —
    the logical-truncation shape the all-empty refusal (case e) fails closed on.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    db = str(state_dir / "antiek.duckdb")
    init_database_at_path(db)
    events = state_dir / "research_events"
    events.mkdir(exist_ok=True)
    (events / "events-0001.jsonl").write_text('{"event": "seed"}\n')
    if not seed_rows:
        return
    with connect_write(db, purpose="backup_script_test_seed") as con:
        con.execute(
            "INSERT INTO documents(document_id, source_tier, document_type, title) "
            "VALUES ('doc-1', 3, 'paper', 'On the Calculus of Variations')"
        )
        con.execute(
            "INSERT INTO chunks(chunk_id, document_id, chunk_index, text) "
            "VALUES ('chk-1', 'doc-1', 0, 'body')"
        )
        con.execute(
            "INSERT INTO nodes(node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n-1', 'Euler', 'person', 'depth'), "
            "('n-2', 'Lagrange', 'person', 'depth')"
        )


_SABOTAGED_NORMALIZER = '''\
"""Test sabotage (R1 red-proof): corrupts schema.sql between normalize and verify."""


def normalize_exported_schema_sql(sql: str) -> str:
    return "CORRUPTED BY TEST SABOTAGE -- deliberately not importable SQL;"
'''


def _build_install_dir(install_dir: Path, *, sabotage_normalizer: bool) -> None:
    """Mimic the deployed /opt/antiek layout the script depends on: the venv
    python (a wrapper exec-ing the interpreter running these tests — the repo
    venv, which provably has duckdb; a bare symlink would lose the venv's
    site-packages because no pyvenv.cfg sits next to it) and
    tools/backup_normalize_schema.py."""
    (install_dir / ".venv" / "bin").mkdir(parents=True)
    _write_stub(
        install_dir / ".venv" / "bin" / "python3",
        f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n',
    )
    tools = install_dir / "tools"
    tools.mkdir()
    target = tools / "backup_normalize_schema.py"
    if sabotage_normalizer:
        target.write_text(_SABOTAGED_NORMALIZER)
    else:
        target.symlink_to(REPO / "tools" / "backup_normalize_schema.py")


def _build_stub_bin(stub_bin: Path) -> None:
    """PATH-front stubs. sudo strips its `-u user` and execs the command
    (stdin — the python heredocs — passes through); chown is a no-op (the
    antiek user does not exist on the test host); rclone records every
    invocation to $RCLONE_STUB_LOG and preserves any copyto payload at
    $RCLONE_STUB_KEEP so the test can inspect exactly what would upload."""
    stub_bin.mkdir(parents=True)
    _write_stub(
        stub_bin / "sudo",
        '#!/usr/bin/env bash\nset -euo pipefail\nif [[ "${1:-}" == "-u" ]]; then shift 2; fi\nexec "$@"\n',
    )
    _write_stub(stub_bin / "chown", "#!/usr/bin/env bash\nexit 0\n")
    _write_stub(
        stub_bin / "rclone",
        '#!/usr/bin/env bash\nset -euo pipefail\necho "$@" >> "${RCLONE_STUB_LOG}"\n'
        'if [[ "$1" == "copyto" ]]; then cp "$2" "${RCLONE_STUB_KEEP}"; fi\nexit 0\n',
    )


def _write_stub(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _make_harness(
    tmp_path: Path,
    *,
    sabotage_normalizer: bool = False,
    lock_timeout_s: str = "60",
    seed_rows: bool = True,
    allow_empty: bool = False,
) -> Harness:
    state_dir = tmp_path / "state"
    install_dir = tmp_path / "install"
    staging_root = tmp_path / "staging"
    stub_bin = tmp_path / "stub-bin"

    _seed_state_dir(state_dir, seed_rows=seed_rows)
    _build_install_dir(install_dir, sabotage_normalizer=sabotage_normalizer)
    _build_stub_bin(stub_bin)
    staging_root.mkdir()

    script = tmp_path / "backup.sh"
    script.write_text(_render_template(state_dir, install_dir))
    script.chmod(0o755)

    rclone_log = tmp_path / "rclone-invocations.log"
    rclone_keep = tmp_path / "uploaded-archive.tar.gz"
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{stub_bin}:{env['PATH']}",
            "RCLONE_STUB_LOG": str(rclone_log),
            "RCLONE_STUB_KEEP": str(rclone_keep),
            "ANTIEK_BACKUP_STAGING_ROOT": str(staging_root),
            "ANTIEK_BACKUP_LOCK_TIMEOUT_S": lock_timeout_s,
        }
    )
    if allow_empty:
        env["ANTIEK_BACKUP_ALLOW_EMPTY"] = "1"
    else:
        env.pop("ANTIEK_BACKUP_ALLOW_EMPTY", None)
    return Harness(
        script=script,
        state_dir=state_dir,
        staging_root=staging_root,
        lock_file=state_dir / "antiek.duckdb.write.lock",
        marker=state_dir / "backup_freshness.json",
        rclone_log=rclone_log,
        rclone_keep=rclone_keep,
        env=env,
    )


def _run_script(harness: Harness) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(harness.script)],
        env=harness.env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def _run_freshness_tool(
    args: list[str], env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    # Isolate from any ambient marker configuration on the dev host.
    env.pop("ANTIEK_BACKUP_MARKER", None)
    env.pop("ANTIEK_STATE_DIR", None)
    env.update(env_overrides or {})
    return subprocess.run(
        [sys.executable, str(FRESHNESS_TOOL), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _iso_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# a. Happy path: exit 0, upload happened, marker written with sane counts
# ---------------------------------------------------------------------------
def test_happy_path_uploads_and_writes_marker(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    proc = _run_script(harness)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"

    # rclone WAS invoked: one copyto (the upload) + one delete (retention).
    invocations = harness.rclone_log.read_text().splitlines()
    assert len(invocations) == 2, invocations
    assert invocations[0].startswith("copyto ")
    assert "test-bucket/nightly/antiek-" in invocations[0]
    assert invocations[1].startswith("delete ")

    # The preserved upload payload is a real archive with the expected members
    # (verify scratch DB must NOT ship; counts manifest + export + events must).
    with tarfile.open(harness.rclone_keep) as tar:
        names = tar.getnames()
    assert any(n.endswith("/duckdb/schema.sql") for n in names), names
    assert any(n.endswith("/source_counts.json") for n in names), names
    assert any("/research_events/" in n for n in names), names
    assert not any("verify-scratch" in n for n in names), names

    # Freshness marker written with the real row counts.
    marker = json.loads(harness.marker.read_text())
    assert marker["counts"] == _SEED_COUNTS
    completed = datetime.fromisoformat(marker["completed_at"])
    assert abs((datetime.now(UTC) - completed).total_seconds()) < 600
    assert marker["script_version"].startswith("backup.sh/")
    assert marker["archive"].endswith(".tar.gz")

    # The check tool reads the marker the script actually wrote (path + shape
    # consistency between backup.sh.j2 and tools/backup_freshness.py).
    tool = _run_freshness_tool(["--marker", str(harness.marker)])
    assert tool.returncode == 0, tool.stdout + tool.stderr
    assert tool.stdout.startswith("FRESH:")

    # The cleanup trap left no staging debris behind.
    assert list(harness.staging_root.iterdir()) == []


# ---------------------------------------------------------------------------
# b. Red-proof R1: corrupted export → verify fails → NO upload
# ---------------------------------------------------------------------------
def test_sabotaged_export_blocks_upload(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path, sabotage_normalizer=True)
    proc = _run_script(harness)

    assert proc.returncode != 0, f"sabotaged run must fail; stdout:\n{proc.stdout}"
    assert "backup verify FAILED" in proc.stderr, proc.stderr
    assert "upload blocked" in proc.stderr, proc.stderr
    # rclone was NEVER invoked — the stub creates its log on first call.
    assert not harness.rclone_log.exists()
    assert not harness.rclone_keep.exists()
    assert not harness.marker.exists()


# ---------------------------------------------------------------------------
# c. Red-proof R2: held flock → bounded timeout, no upload; release → success
# ---------------------------------------------------------------------------
def test_held_write_lock_times_out_then_succeeds_after_release(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path, lock_timeout_s="2")

    # A competing "writer" holds the exact runtime/db_lock.py sidecar flock.
    fd = os.open(harness.lock_file, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proc = _run_script(harness)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    assert proc.returncode != 0, f"lock-held run must fail; stdout:\n{proc.stdout}"
    assert "could not acquire DuckDB write lock" in proc.stderr, proc.stderr
    assert "aborting backup" in proc.stderr, proc.stderr
    assert not harness.rclone_log.exists()
    assert not harness.marker.exists()

    # After release the same rendered script succeeds end-to-end.
    proc2 = _run_script(harness)
    assert proc2.returncode == 0, f"stdout:\n{proc2.stdout}\nstderr:\n{proc2.stderr}"
    assert harness.rclone_log.exists()
    assert json.loads(harness.marker.read_text())["counts"] == _SEED_COUNTS


# ---------------------------------------------------------------------------
# e. Red-proof (logical truncation): all-empty source refused unless overridden
# ---------------------------------------------------------------------------
def test_all_empty_source_refused_without_override(tmp_path: Path) -> None:
    """Schema intact, every core table zero rows — the catastrophic-emptying
    shape. An empty export count-matches its own emptiness, so without this
    refusal the pipeline would verify, upload, and stamp a fresh marker."""
    harness = _make_harness(tmp_path, seed_rows=False)
    proc = _run_script(harness)

    assert proc.returncode != 0, f"all-empty run must fail; stdout:\n{proc.stdout}"
    assert "refusing to certify an empty backup" in proc.stderr, proc.stderr
    assert "ANTIEK_BACKUP_ALLOW_EMPTY=1" in proc.stderr, proc.stderr
    # Died in step 1 BEFORE export effort: the normalize step (which follows
    # the export heredoc) never ran, and rclone was never invoked.
    assert "normalizing EXPORT schema.sql" not in proc.stdout, proc.stdout
    assert not harness.rclone_log.exists()
    assert not harness.rclone_keep.exists()
    assert not harness.marker.exists()


def test_all_empty_source_allowed_with_explicit_override(tmp_path: Path) -> None:
    """ANTIEK_BACKUP_ALLOW_EMPTY=1 (day-0 / fresh-install escape hatch) lets a
    legitimately empty store back up end-to-end, with honest zero counts."""
    harness = _make_harness(tmp_path, seed_rows=False, allow_empty=True)
    proc = _run_script(harness)

    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert harness.rclone_log.exists()
    marker = json.loads(harness.marker.read_text())
    assert marker["counts"] == {"documents": 0, "chunks": 0, "nodes": 0}


def test_hostile_allow_empty_value_is_inert_and_does_not_bypass(tmp_path: Path) -> None:
    """The shell expands ${ALLOW_EMPTY} into Python SOURCE inside the export
    heredoc. Before bash-side normalization, a quote-bearing env value could
    terminate the string literal: a bare double-quote raised SyntaxError (wrong
    exit path), and the exec-shape payload below EXECUTED arbitrary Python (its
    leading "" is falsy, so `or` evaluates the injected system() call). Post-fix,
    only the bare literal 1 or 0 can reach the Python text: any non-"1" value is
    normalized to 0, so the payload never runs AND the empty gate still refuses."""
    sentinel = tmp_path / "pwned-by-env-injection"
    payloads = [
        '"',  # SyntaxError shape
        f'" or __import__("os").system("touch {sentinel}") or "',  # exec shape
    ]
    for i, payload in enumerate(payloads):
        harness = _make_harness(tmp_path / f"h{i}", seed_rows=False)
        harness.env["ANTIEK_BACKUP_ALLOW_EMPTY"] = payload
        proc = _run_script(harness)

        # Inert: nothing executed, no interpreter crash — the value is data.
        assert not sentinel.exists(), f"injected payload EXECUTED: {payload!r}"
        assert "SyntaxError" not in proc.stderr, proc.stderr
        assert "Traceback" not in proc.stderr, proc.stderr
        # Not a bypass: treated as not-"1", so the all-empty refusal still fires.
        assert proc.returncode != 0, f"hostile value must not bypass; stdout:\n{proc.stdout}"
        assert "refusing to certify an empty backup" in proc.stderr, proc.stderr
        assert not harness.rclone_log.exists()
        assert not harness.marker.exists()


# ---------------------------------------------------------------------------
# d. tools/backup_freshness.py: fresh/stale/missing/threshold/--json/env
# ---------------------------------------------------------------------------
def _write_marker(path: Path, completed_at: str) -> None:
    path.write_text(
        json.dumps(
            {
                "completed_at": completed_at,
                "archive": "antiek-x.tar.gz",
                "counts": {"documents": 5, "chunks": 9, "nodes": 3},
                "script_version": "backup.sh/test",
            }
        )
    )


def test_freshness_tool_fresh_marker_exits_zero(tmp_path: Path) -> None:
    marker = tmp_path / "backup_freshness.json"
    _write_marker(marker, _iso_utc(datetime.now(UTC) - timedelta(hours=1)))
    proc = _run_freshness_tool(["--marker", str(marker)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.startswith("FRESH:")
    assert len(proc.stdout.strip().splitlines()) == 1


def test_freshness_tool_stale_and_missing_exit_nonzero(tmp_path: Path) -> None:
    marker = tmp_path / "backup_freshness.json"
    _write_marker(marker, _iso_utc(datetime.now(UTC) - timedelta(hours=30)))
    stale = _run_freshness_tool(["--marker", str(marker)])
    assert stale.returncode == 1
    assert stale.stdout.startswith("STALE:")
    assert "30." in stale.stdout and "26.0h" in stale.stdout

    # Same 30h marker under a 40h threshold is fresh (flag override works).
    widened = _run_freshness_tool(["--marker", str(marker), "--max-age-hours", "40"])
    assert widened.returncode == 0, widened.stdout

    missing = _run_freshness_tool(["--marker", str(tmp_path / "nope.json")])
    assert missing.returncode == 1
    assert missing.stdout.startswith("STALE:")
    assert "no marker" in missing.stdout

    garbage = tmp_path / "garbage.json"
    garbage.write_text("not json {")
    invalid = _run_freshness_tool(["--marker", str(garbage)])
    assert invalid.returncode == 1
    assert "not valid JSON" in invalid.stdout

    _write_marker(marker, _iso_utc(datetime.now(UTC) + timedelta(hours=6)))
    future = _run_freshness_tool(["--marker", str(marker)])
    assert future.returncode == 1
    assert "in the future" in future.stdout


@pytest.mark.parametrize(
    "mutation",
    [
        lambda marker: marker.pop("counts"),
        lambda marker: marker.__setitem__("counts", {"documents": 1}),
        lambda marker: marker.__setitem__(
            "counts", {"documents": -1, "chunks": 2, "nodes": 3}
        ),
        lambda marker: marker.pop("script_version"),
        lambda marker: marker.__setitem__("script_version", "unknown"),
        lambda marker: marker.pop("archive"),
        lambda marker: marker.__setitem__("archive", "../not-a-backup.tar.gz"),
        lambda marker: marker.__setitem__(
            "completed_at", datetime.now(UTC).replace(tzinfo=None).isoformat()
        ),
    ],
)
def test_freshness_tool_rejects_incomplete_or_forged_marker(tmp_path: Path, mutation) -> None:
    """A recent timestamp alone is not evidence that a verified backup landed."""
    marker = tmp_path / "backup_freshness.json"
    _write_marker(marker, _iso_utc(datetime.now(UTC) - timedelta(hours=1)))
    payload = json.loads(marker.read_text())
    mutation(payload)
    marker.write_text(json.dumps(payload))

    proc = _run_freshness_tool(["--marker", str(marker)])

    assert proc.returncode == 1
    assert proc.stdout.startswith("STALE:")


def test_freshness_tool_json_mode_and_env_resolution(tmp_path: Path) -> None:
    marker = tmp_path / "backup_freshness.json"
    _write_marker(marker, _iso_utc(datetime.now(UTC) - timedelta(hours=2)))

    # --json shape (for future dashboard/health wiring).
    proc = _run_freshness_tool(["--marker", str(marker), "--json"])
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert set(payload) == {
        "fresh",
        "reason",
        "marker_path",
        "max_age_hours",
        "age_hours",
        "completed_at",
        "counts",
        "script_version",
    }
    assert payload["fresh"] is True
    assert payload["marker_path"] == str(marker)
    assert payload["max_age_hours"] == 26.0
    assert 1.9 < payload["age_hours"] < 2.5
    assert payload["counts"] == {"documents": 5, "chunks": 9, "nodes": 3}
    assert payload["script_version"] == "backup.sh/test"

    # Marker path resolvable via env (no --marker flag), both variants.
    via_marker_env = _run_freshness_tool([], {"ANTIEK_BACKUP_MARKER": str(marker)})
    assert via_marker_env.returncode == 0, via_marker_env.stdout
    via_state_env = _run_freshness_tool([], {"ANTIEK_STATE_DIR": str(tmp_path)})
    assert via_state_env.returncode == 0, via_state_env.stdout


# ---------------------------------------------------------------------------
# f. --max-age-hours fail-closed: nan/inf/negative rejected at parse time
# ---------------------------------------------------------------------------
def test_freshness_tool_rejects_non_finite_or_negative_threshold(tmp_path: Path) -> None:
    """`float("nan")` parses, and every comparison against NaN is False — so
    `age_hours > NaN` never trips and ANY stale marker would read FRESH. The
    threshold must be validated finite and non-negative, failing closed."""
    marker = tmp_path / "backup_freshness.json"
    # A 30h-stale marker: the exact input a NaN threshold would wrongly bless.
    _write_marker(marker, _iso_utc(datetime.now(UTC) - timedelta(hours=30)))

    # `=` form so argparse can't swallow `-inf` as an unknown option before the
    # type validator runs (it special-cases plain negative numbers like -1 only).
    for bad in ("nan", "-1", "inf", "-inf", "NaN"):
        proc = _run_freshness_tool(["--marker", str(marker), f"--max-age-hours={bad}"])
        assert proc.returncode != 0, f"--max-age-hours={bad} must be rejected"
        assert "finite non-negative" in proc.stderr, (bad, proc.stderr)

    # Control: a valid finite threshold still parses and still says STALE.
    control = _run_freshness_tool(["--marker", str(marker), "--max-age-hours", "26.0"])
    assert control.returncode == 1
    assert control.stdout.startswith("STALE:")
