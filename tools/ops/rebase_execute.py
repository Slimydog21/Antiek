"""Green-between-buckets rebase *executor* for stale Antiek integration branches.

``rebase_preflight.py`` is the read-only planner: it answers "what will a rebase
have to reconcile?" and groups the ``git merge-tree`` conflicts into trees via
:func:`tools.ops.rebase_preflight._path_bucket`. This module is the missing
*executor*: it consumes the planner's ``--json`` output, drives the rebase one
conflict-bucket at a time inside a **disposable** worktree, runs a scoped test
gate after each bucket's conflicts are resolved, and advances **only** on a real
green exit code -- halting honestly (and resumably) on red.

Design invariants (each is load-bearing; the tests in
``tests/test_rebase_execute.py`` pin them):

1. **Import, do not fork the planner.** The bucket taxonomy, the
   ``RebasePreflight``/``PathBucket`` dataclasses and the text-render style are
   imported from :mod:`tools.ops.rebase_preflight`. No merge-tree parsing is
   re-implemented here.

2. **The gate exit code is authoritative, not "conflicts resolved".** Resolving
   a merge conflict makes *git* happy; it does not make the *code* correct.
   Advancement (a ``git rebase --continue`` checkpoint) happens only when the
   scoped gate returns exit code ``0``. A bucket that git-resolves cleanly but
   reds the suite is a **red** bucket and the executor halts.

3. **Never mutate the primary/operator checkout.** Every mutating entrypoint
   first calls :func:`assert_disposable`, which refuses anything that is the
   repo's *main* worktree (``--git-dir == --git-common-dir``) or the operator's
   current working directory. A halted rebase is a success; a rewritten
   operator checkout is a disaster.

4. **The ledger is the resume contract, and "green-complete" is a pure
   function of the recorded ledger.** :func:`is_green_complete` requires that
   EVERY planned bucket in ``ordered_buckets`` has a recorded green (exit-``0``)
   entry AND that the FINAL planned bucket carries a full-suite (``scope=="full"``)
   exit-``0`` gate -- the end-state pass that ran after the last bucket landed.
   A full pass on a non-final bucket, a green-but-only-scoped final bucket, or
   any missing/pending/red bucket all fail it (git surfaces conflicts in commit
   order, so a full gate can fire mid-rebase while later buckets are unresolved
   -- this predicate refuses to be fooled by that). Timestamps are *passed in*
   (never clock-read) so a replayed run is deterministic; the CLI ``status``
   path adds a runtime ``not rebase_in_progress`` check as defense-in-depth.

Bucket ordering rationale (deterministic, documented -- not dict order):
ascending blast radius. ``docs``/``tooling``/``ci``/``infrastructure`` resolve
first (prose, config and isolated ops -- a bad resolution there cannot corrupt
product runtime), then ``acquisition``/``tests``/``reading-app`` (lane- and
stack-local, each gated by its own suite), and ``backend-substrate`` last
(``substrate``/``interfaces``/``runtime``/``orchestration`` -- the DuckDB
single-writer core, highest blast radius) so it lands under the mandatory
full-suite gate; the unclassified ``other`` tree resolves just before it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

# Rigor #4 -- import the planner; do not re-derive it.
from tools.ops.rebase_preflight import (
    ROOT,
    GitError,
    PathBucket,
    RebasePreflight,
    _bucket_counts,  # noqa: F401  (re-exported for callers/tests that want it)
    _git,
    _git_text,
    _path_bucket,  # noqa: F401  (re-exported; taxonomy source of truth)
    format_text,  # noqa: F401  (style mirrored by format_ledger_text)
)

# The disposable-worktree default the planner's markdown plan already documents.
DEFAULT_DISPOSABLE_WORKTREE = ROOT.parent / "antiek-rebase-preflight"
DEFAULT_LEDGER_PATH = ROOT / ".infinite" / "rebase-ledger.json"
DEFAULT_PYTHON = ".venv/bin/python"
DEFAULT_ONTO = "origin/main"

FRONTEND_BUCKET = "reading-app"

# Deterministic, documented ordering: ascending blast radius (see module docstring).
BUCKET_RISK_ORDER: tuple[str, ...] = (
    "docs",
    "tooling",
    "ci",
    "infrastructure",
    "acquisition",
    "tests",
    "reading-app",
    "other",
    "backend-substrate",
)
BUCKET_ORDER_RATIONALE = (
    "ascending blast radius: docs/tooling/ci/infrastructure first (prose, config, "
    "isolated ops -- cannot corrupt product runtime), then acquisition/tests/"
    "reading-app (lane/stack-local, self-gated), then the unclassified 'other', "
    "and backend-substrate last (the DuckDB single-writer core; highest blast "
    "radius) so it lands under the mandatory full-suite gate."
)

LEDGER_SCHEMA_VERSION = 2


class DisposableWorktreeError(RuntimeError):
    """Raised when a mutation is attempted somewhere that is not disposable."""


# --------------------------------------------------------------------------- #
# Bucket ordering (M1)
# --------------------------------------------------------------------------- #
def _risk_index(name: str) -> int:
    try:
        return BUCKET_RISK_ORDER.index(name)
    except ValueError:
        # An unknown tree sorts after every known one -- resolved last, under scrutiny.
        return len(BUCKET_RISK_ORDER)


def order_buckets(buckets: Sequence[PathBucket]) -> tuple[PathBucket, ...]:
    """Return the buckets in the deterministic risk order (lowest blast radius first).

    Pure function of the input buckets; ties broken by name so the ordering is
    stable and reproducible across runs.
    """

    return tuple(sorted(buckets, key=lambda b: (_risk_index(b.name), b.name)))


def load_plan(path: Path) -> RebasePreflight:
    """Reconstruct a :class:`RebasePreflight` from the planner's ``--json`` dump.

    The planner emits ``asdict(RebasePreflight)``; the two bucket tuples come
    back as lists of ``{"name","count"}`` dicts. We rebuild the frozen dataclass
    rather than re-run merge-tree detection -- the executor consumes the plan, it
    does not recompute it.
    """

    data = dict(json.loads(Path(path).read_text()))
    data["overlapping_files"] = tuple(data.get("overlapping_files", []))
    data["merge_tree_conflict_files"] = tuple(data.get("merge_tree_conflict_files", []))
    data["overlapping_buckets"] = tuple(
        PathBucket(**b) for b in data.get("overlapping_buckets", [])
    )
    data["merge_tree_conflict_buckets"] = tuple(
        PathBucket(**b) for b in data.get("merge_tree_conflict_buckets", [])
    )
    return RebasePreflight(**data)


def plan_bucket_order(preflight: RebasePreflight) -> tuple[PathBucket, ...]:
    """The ordered conflict buckets an executor should drive, plan -> risk order."""

    return order_buckets(preflight.merge_tree_conflict_buckets)


# --------------------------------------------------------------------------- #
# Scoped-vs-full gate policy (M2/M3)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GateCommand:
    argv: tuple[str, ...]
    cwd_rel: str = "."


@dataclass(frozen=True)
class GateSpec:
    scope: str  # "bucket" | "full"
    label: str
    commands: tuple[GateCommand, ...]


@dataclass(frozen=True)
class GateResult:
    exit_code: int
    output: str  # combined stdout/stderr, preserved verbatim so a halt is inspectable


def _pytest_command(python_exe: str, paths: Sequence[str] = ("tests/",)) -> GateCommand:
    return GateCommand(argv=(python_exe, "-m", "pytest", *paths, "-q"), cwd_rel=".")


def _vitest_command() -> GateCommand:
    return GateCommand(argv=("npx", "vitest", "run"), cwd_rel="apps/reading")


def build_gate_spec(bucket: str, scope: str, python_exe: str = DEFAULT_PYTHON) -> GateSpec:
    """Map a bucket + scope to its gate commands.

    ``scope="bucket"`` runs only the stack the bucket's tree touches -- ``vitest``
    for the frontend ``reading-app`` tree, the backend ``pytest`` suite for every
    other tree. ``scope="full"`` runs *both* stacks (the cross-stack behaviour
    suite main's CI enforces) and is what the final bucket is forced to before
    the harness may claim ``green-complete``.
    """

    if scope == "full":
        return GateSpec(
            scope="full",
            label="full cross-stack suite (pytest + vitest)",
            commands=(_pytest_command(python_exe), _vitest_command()),
        )
    if scope != "bucket":
        raise ValueError(f"unknown scope {scope!r}; expected 'bucket' or 'full'")
    if bucket == FRONTEND_BUCKET:
        return GateSpec(
            scope="bucket",
            label="vitest (reading-app frontend suite)",
            commands=(_vitest_command(),),
        )
    return GateSpec(
        scope="bucket",
        label=f"pytest backend suite (bucket={bucket})",
        commands=(_pytest_command(python_exe),),
    )


def render_commands(commands: Sequence[GateCommand]) -> str:
    parts = []
    for cmd in commands:
        joined = " ".join(cmd.argv)
        if cmd.cwd_rel not in ("", "."):
            joined = f"(cd {cmd.cwd_rel} && {joined})"
        parts.append(joined)
    return " && ".join(parts)


# A GateRunner takes the resolved spec + the worktree and returns a real result.
GateRunner = Callable[[GateSpec, Path], GateResult]


def subprocess_gate_runner(spec: GateSpec, worktree: Path) -> GateResult:
    """Default runner: execute each command, short-circuit on the first red.

    The returned exit code is the first non-zero real subprocess exit code (or
    ``0`` if all pass); the output concatenates every command's stdout+stderr so
    a halt preserves exactly what failed.
    """

    chunks: list[str] = []
    for cmd in spec.commands:
        cwd = (worktree / cmd.cwd_rel).resolve()
        proc = subprocess.run(
            list(cmd.argv),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        chunks.append(
            f"$ {' '.join(cmd.argv)}  (cwd={cmd.cwd_rel}) -> exit {proc.returncode}\n"
            f"{proc.stdout}{proc.stderr}"
        )
        if proc.returncode != 0:
            return GateResult(exit_code=proc.returncode, output="\n".join(chunks))
    return GateResult(exit_code=0, output="\n".join(chunks))


# --------------------------------------------------------------------------- #
# Disposable-worktree guard (M2)
# --------------------------------------------------------------------------- #
def assert_disposable(
    worktree: Path,
    *,
    primary_checkout: Path | None = ROOT,
    cwd: Path | None = None,
) -> Path:
    """Refuse to proceed unless ``worktree`` is a disposable, linked worktree.

    Fires (raises :class:`DisposableWorktreeError`) when the target is the repo's
    **main** worktree (git-dir == git-common-dir), the ``primary_checkout``, or
    the operator's ``cwd``. Called before *any* mutating operation.
    """

    wt = Path(worktree).resolve()

    if primary_checkout is not None and wt == Path(primary_checkout).resolve():
        raise DisposableWorktreeError(f"refusing to mutate {wt}: it is the primary checkout")
    if cwd is not None and wt == Path(cwd).resolve():
        raise DisposableWorktreeError(
            f"refusing to mutate {wt}: it is the operator's current working directory"
        )

    try:
        git_dir = Path(_git_text(wt, "rev-parse", "--absolute-git-dir")).resolve()
        common = _git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if common.returncode != 0:
            # Older git: --path-format may be unsupported; fall back.
            common_out = _git_text(wt, "rev-parse", "--git-common-dir")
            common_dir = (wt / common_out).resolve()
        else:
            common_dir = Path(common.stdout.strip()).resolve()
    except GitError as exc:  # not a git worktree at all
        raise DisposableWorktreeError(f"{wt} is not a git worktree: {exc}") from exc

    if git_dir == common_dir:
        # The main worktree's git-dir *is* the common dir. A linked (disposable)
        # worktree has its own git-dir under <common>/worktrees/<name>.
        raise DisposableWorktreeError(
            f"refusing to mutate {wt}: it is the repository's primary worktree "
            f"(git-dir == git-common-dir == {git_dir}); create a disposable "
            f"worktree with `git worktree add` first"
        )
    return wt


# --------------------------------------------------------------------------- #
# Git driving helpers (M2) -- rebase plumbing, NOT merge-tree parsing.
# --------------------------------------------------------------------------- #
def create_disposable_worktree(primary: Path, dest: Path, base_ref: str) -> Path:
    """`git worktree add <dest> <base_ref>` from ``primary``; returns ``dest``."""

    dest = Path(dest)
    if dest.exists():
        raise DisposableWorktreeError(f"{dest} already exists; refusing to clobber")
    result = _git(primary, "worktree", "add", str(dest), base_ref)
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "git worktree add failed")
    return dest


def remove_disposable_worktree(primary: Path, dest: Path) -> None:
    """Remove a disposable linked worktree; refuses a non-disposable target.

    Caller-guard contract + defense-in-depth: ``assert_disposable`` runs here so
    this can never remove the primary/main worktree even if mis-called.
    """

    assert_disposable(dest, primary_checkout=primary)
    _git(primary, "worktree", "remove", "--force", str(dest))


def rebase_in_progress(worktree: Path) -> bool:
    git_dir = Path(_git_text(worktree, "rev-parse", "--absolute-git-dir"))
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def conflicted_paths(worktree: Path) -> tuple[str, ...]:
    text = _git_text(worktree, "diff", "--name-only", "--diff-filter=U")
    return tuple(line for line in text.splitlines() if line)


def current_conflict_buckets(worktree: Path) -> tuple[PathBucket, ...]:
    """Bucket the *live* conflicted paths at the current rebase stop.

    git surfaces conflicts in commit order, so the bucket the operator must
    resolve *now* is derived from the live index -- not from the plan's risk
    order. The plan order governs reporting + which bucket is treated as final.
    """

    return _bucket_counts(conflicted_paths(worktree))


def begin_rebase(worktree: Path, onto: str = DEFAULT_ONTO) -> tuple[int, str]:
    """Start the rebase; returns ``(exit_code, output)``. Non-zero => stopped.

    Caller-guard contract + defense-in-depth: ``assert_disposable`` runs here so
    the primary worktree can never be rebased even if this is mis-called.
    """

    assert_disposable(worktree)
    result = _git(worktree, "rebase", onto)
    return result.returncode, (result.stdout + result.stderr)


def continue_rebase(worktree: Path) -> tuple[int, str]:
    """`git rebase --continue` with a non-interactive editor (checkpoint).

    Caller-guard contract + defense-in-depth: guarded like :func:`begin_rebase`.
    """

    assert_disposable(worktree)
    result = subprocess.run(
        ["git", "-C", str(worktree), "-c", "core.editor=true", "rebase", "--continue"],
        capture_output=True,
        text=True,
        check=False,
        env={"GIT_EDITOR": "true", **_inherit_env()},
    )
    return result.returncode, (result.stdout + result.stderr)


def _inherit_env() -> dict[str, str]:
    import os

    return dict(os.environ)


def head_sha(worktree: Path) -> str:
    return _git_text(worktree, "rev-parse", "HEAD")


def stage_all(worktree: Path) -> None:
    _git(worktree, "add", "-A")


# --------------------------------------------------------------------------- #
# Ledger (M3) -- the resume contract.
# --------------------------------------------------------------------------- #
@dataclass
class BucketLedgerEntry:
    bucket: str
    order_index: int
    scope: str  # "bucket" | "full" (the effective scope actually run)
    resolved: bool  # were the bucket's conflicts staged as resolved before gating
    gate_label: str
    gate_command: str
    exit_code: int | None  # None => pending (gate not yet run)
    checkpoint_sha: str | None  # HEAD after `git rebase --continue`; None on red/pending
    timestamp_in: str  # passed in by the caller -- deterministic, never clock-read here
    status: str  # "pending" | "green" | "red"
    halt_log: str | None = None  # path to preserved failing-gate output, on red


@dataclass
class RebaseLedger:
    branch: str
    onto: str
    ordered_buckets: tuple[str, ...]
    entries: list[BucketLedgerEntry] = field(default_factory=list)
    schema_version: int = LEDGER_SCHEMA_VERSION


def upsert_entry(ledger: RebaseLedger, entry: BucketLedgerEntry) -> RebaseLedger:
    """Replace-or-append the entry for ``entry.bucket`` (idempotent per bucket)."""

    kept = [e for e in ledger.entries if e.bucket != entry.bucket]
    kept.append(entry)
    kept.sort(key=lambda e: (e.order_index, e.bucket))
    return replace(ledger, entries=kept)


def is_green_complete(ledger: RebaseLedger) -> bool:
    """PURE completion predicate -- a function of the recorded ledger only.

    ``green-complete`` iff ALL of:
      * there is at least one planned bucket (``ordered_buckets`` non-empty), AND
      * EVERY planned bucket has a recorded ``status=="green"`` entry with exit
        ``0`` -- i.e. no planned bucket is missing, pending, or red, AND
      * the FINAL planned bucket (``ordered_buckets[-1]``, the highest-blast-radius
        tree, resolved last) carries a full-scope (``scope=="full"``) exit-``0``
        gate -- the end-state full-suite pass that ran after the last bucket
        landed.

    This is deliberately stronger than "some full pass exists somewhere": a
    full-scope pass recorded on a NON-final bucket, or a green final bucket that
    was only scoped, does NOT satisfy it -- because git surfaces conflicts in
    commit order, so a full gate can fire mid-rebase while later buckets are
    still unresolved. Requiring (a) every bucket green AND (b) the full pass on
    the final bucket closes that hole. Kept a pure function of the ledger so a
    resumed/replayed run is deterministic; the CLI ``status`` path adds a
    runtime ``not rebase_in_progress`` check as defense-in-depth.
    """

    if not ledger.ordered_buckets:
        return False
    by_bucket = {e.bucket: e for e in ledger.entries}
    # (a) every planned bucket has a recorded green (exit-0) entry.
    for name in ledger.ordered_buckets:
        entry = by_bucket.get(name)
        if entry is None or entry.status != "green" or entry.exit_code != 0:
            return False
    # (b) the final planned bucket's recorded gate is a full-suite exit-0 pass.
    final = by_bucket[ledger.ordered_buckets[-1]]
    return final.scope == "full" and final.exit_code == 0


def ledger_status(ledger: RebaseLedger) -> str:
    if is_green_complete(ledger):
        return "green-complete"
    if any(e.status == "red" for e in ledger.entries):
        return "halted-red"
    return "in-progress"


def ledger_to_dict(ledger: RebaseLedger) -> dict[str, Any]:
    return {
        "schema_version": ledger.schema_version,
        "branch": ledger.branch,
        "onto": ledger.onto,
        "ordered_buckets": list(ledger.ordered_buckets),
        "status": ledger_status(ledger),
        "green_complete": is_green_complete(ledger),
        "entries": [asdict(e) for e in ledger.entries],
    }


def ledger_from_dict(data: dict[str, Any]) -> RebaseLedger:
    entries = [BucketLedgerEntry(**e) for e in data.get("entries", [])]
    return RebaseLedger(
        branch=data["branch"],
        onto=data["onto"],
        ordered_buckets=tuple(data.get("ordered_buckets", [])),
        entries=entries,
        schema_version=data.get("schema_version", LEDGER_SCHEMA_VERSION),
    )


def write_ledger(ledger: RebaseLedger, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger_to_dict(ledger), indent=2, sort_keys=True) + "\n")
    return path


def read_ledger(path: Path) -> RebaseLedger:
    return ledger_from_dict(json.loads(Path(path).read_text()))


def format_ledger_text(ledger: RebaseLedger) -> str:
    """Human render mirroring ``rebase_preflight.format_text`` (key: value lines)."""

    lines = [
        f"rebase-ledger: {ledger_status(ledger)}",
        f"branch: {ledger.branch} onto={ledger.onto}",
        f"green_complete: {'yes' if is_green_complete(ledger) else 'no'}",
        "ordered_buckets: " + ", ".join(ledger.ordered_buckets),
    ]
    if ledger.entries:
        lines.append("buckets:")
        for e in ledger.entries:
            sha = e.checkpoint_sha[:10] if e.checkpoint_sha else "-"
            exit_repr = "pending" if e.exit_code is None else str(e.exit_code)
            lines.append(
                f"- {e.bucket} [{e.scope}] status={e.status} exit={exit_repr} "
                f"resolved={'yes' if e.resolved else 'no'} checkpoint={sha} "
                f"ts_in={e.timestamp_in}"
            )
            lines.append(f"    gate: {e.gate_command}")
            if e.halt_log:
                lines.append(f"    halt_log: {e.halt_log}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The core single-bucket loop step (M2/M3)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AdvanceOutcome:
    ledger: RebaseLedger
    entry: BucketLedgerEntry
    gate: GateResult
    exit_code: int  # process exit code for the caller: 0 green, non-zero halt


def advance_bucket(
    worktree: Path,
    *,
    ledger: RebaseLedger,
    bucket: str,
    order_index: int,
    scope: str,
    is_final: bool,
    timestamp_in: str,
    python_exe: str = DEFAULT_PYTHON,
    primary_checkout: Path | None = ROOT,
    cwd: Path | None = None,
    resolved: bool = True,
    gate_runner: GateRunner = subprocess_gate_runner,
    checkpoint_fn: Callable[[Path], tuple[int, str]] = continue_rebase,
    head_fn: Callable[[Path], str] = head_sha,
    halt_log_path: Path | None = None,
) -> AdvanceOutcome:
    """Run one bucket's gate and checkpoint-or-halt.

    Order of operations (all invariants live here):

    1. **Guard first** -- ``assert_disposable`` before touching anything.
    2. The final bucket's scope is forced to ``full`` regardless of ``scope``.
    3. Run the gate; the **real exit code** decides:
         * ``0``  -> record green, ``git rebase --continue`` (checkpoint), record SHA.
         * ``!=0`` -> record red, **do not** checkpoint, preserve the failing output.

    Returns an :class:`AdvanceOutcome`; ``.exit_code`` is what the CLI exits with.
    """

    # (1) Guard -- refuse to mutate anything that is not disposable.
    assert_disposable(worktree, primary_checkout=primary_checkout, cwd=cwd)

    # (2) The final bucket forces the full cross-stack suite.
    effective_scope = "full" if is_final else scope
    spec = build_gate_spec(bucket, effective_scope, python_exe)

    # (3) The gate exit code is authoritative -- run it now.
    gate = gate_runner(spec, worktree)

    entry = BucketLedgerEntry(
        bucket=bucket,
        order_index=order_index,
        scope=effective_scope,
        resolved=resolved,
        gate_label=spec.label,
        gate_command=render_commands(spec.commands),
        exit_code=gate.exit_code,
        checkpoint_sha=None,
        timestamp_in=timestamp_in,
        status="pending",
    )

    if gate.exit_code == 0:
        entry.status = "green"
        # Advance the rebase (checkpoint) ONLY on a green real exit code.
        cont_code, cont_out = checkpoint_fn(worktree)
        if cont_code != 0:
            # git could not continue (e.g. still-unmerged paths): this is NOT a
            # green checkpoint. Record it honestly as red and preserve why.
            entry.status = "red"
            entry.exit_code = cont_code
            entry.checkpoint_sha = None
            if halt_log_path is not None:
                Path(halt_log_path).parent.mkdir(parents=True, exist_ok=True)
                Path(halt_log_path).write_text(cont_out)
                entry.halt_log = str(halt_log_path)
            ledger = upsert_entry(ledger, entry)
            return AdvanceOutcome(ledger, entry, gate, exit_code=cont_code or 1)
        entry.checkpoint_sha = head_fn(worktree)
        ledger = upsert_entry(ledger, entry)
        return AdvanceOutcome(ledger, entry, gate, exit_code=0)

    # Red gate -> HALT. No checkpoint. Preserve the failing output for resume.
    entry.status = "red"
    if halt_log_path is not None:
        Path(halt_log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(halt_log_path).write_text(gate.output)
        entry.halt_log = str(halt_log_path)
    ledger = upsert_entry(ledger, entry)
    return AdvanceOutcome(ledger, entry, gate, exit_code=gate.exit_code or 1)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_plan(args: argparse.Namespace) -> int:
    preflight = load_plan(args.plan)
    ordered = plan_bucket_order(preflight)
    if args.json:
        print(
            json.dumps(
                {
                    "branch": preflight.branch,
                    "onto": args.onto,
                    "bucket_risk_order": list(BUCKET_RISK_ORDER),
                    "ordered_buckets": [{"name": b.name, "count": b.count} for b in ordered],
                    "merge_tree_conflict_count": preflight.merge_tree_conflict_count,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(f"rebase-execute plan: {preflight.status}")
    print(f"branch: {preflight.branch} onto={args.onto}")
    print(f"merge_tree_conflicts: {preflight.merge_tree_conflict_count}")
    print(f"bucket_order_rationale: {BUCKET_ORDER_RATIONALE}")
    print("ordered_buckets (lowest blast radius first):")
    if not ordered:
        print("- none")
    for i, bucket in enumerate(ordered):
        final = " [FINAL -> forces full-suite gate]" if i == len(ordered) - 1 else ""
        print(f"- {i}. {bucket.name}={bucket.count}{final}")
    if args.dry_run:
        print("dry-run: no worktree mutated")
    return 0


def _load_or_init_ledger(args: argparse.Namespace, preflight: RebasePreflight) -> RebaseLedger:
    if Path(args.ledger).exists():
        return read_ledger(args.ledger)
    ordered = plan_bucket_order(preflight)
    return RebaseLedger(
        branch=preflight.branch,
        onto=args.onto,
        ordered_buckets=tuple(b.name for b in ordered),
    )


def _cmd_begin(args: argparse.Namespace) -> int:
    preflight = load_plan(args.plan)
    worktree = Path(args.worktree) if args.worktree else DEFAULT_DISPOSABLE_WORKTREE
    if args.create and not worktree.exists():
        create_disposable_worktree(args.primary, worktree, args.base)
    # Guard before mutating.
    assert_disposable(worktree, primary_checkout=args.primary, cwd=Path.cwd())
    ledger = _load_or_init_ledger(args, preflight)

    if rebase_in_progress(worktree):
        print(f"rebase already in progress in {worktree} (resuming)")
    else:
        code, out = begin_rebase(worktree, args.onto)
        if code == 0:
            print("rebase completed with no conflicts -- run the final full gate")
            write_ledger(ledger, args.ledger)
            return 0
        print(f"rebase stopped (exit {code}); output follows:")
        print(out)

    buckets = current_conflict_buckets(worktree)
    print("current conflict buckets (live index order):")
    for b in buckets:
        print(f"- {b.name}={b.count}")
    print("conflicted files:")
    for p in conflicted_paths(worktree):
        print(f"- {p}")
    write_ledger(ledger, args.ledger)
    print(f"ledger: {args.ledger}")
    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    preflight = load_plan(args.plan)
    worktree = Path(args.worktree) if args.worktree else DEFAULT_DISPOSABLE_WORKTREE
    # Guard FIRST -- before ANY mutation. ``stage_all`` (git add -A) below writes
    # the target's index, so the disposability check must precede it.
    assert_disposable(worktree, primary_checkout=args.primary, cwd=Path.cwd())
    ledger = _load_or_init_ledger(args, preflight)

    order_names = ledger.ordered_buckets or tuple(b.name for b in plan_bucket_order(preflight))
    try:
        order_index = order_names.index(args.bucket)
    except ValueError:
        order_index = len(order_names)
    # Auto-final ONLY when this is the last-ordered bucket AND every other planned
    # bucket already has a recorded green entry. git surfaces conflicts in commit
    # order, so the risk-order-last bucket can replay first; without the all-green
    # guard, gating it would fire the full gate mid-rebase with later buckets
    # still unresolved. ``--final`` remains an explicit operator override.
    already_green = {e.bucket for e in ledger.entries if e.status == "green" and e.exit_code == 0}
    is_final = args.final or (
        bool(order_names)
        and args.bucket == order_names[-1]
        and all(b in already_green for b in order_names if b != args.bucket)
    )

    if args.mark_resolved:
        stage_all(worktree)

    halt_log = Path(args.ledger).with_name(f"rebase-halt-{args.bucket}.log")
    outcome = advance_bucket(
        worktree,
        ledger=ledger,
        bucket=args.bucket,
        order_index=order_index,
        scope=args.scope,
        is_final=is_final,
        timestamp_in=args.timestamp_in,
        python_exe=args.python,
        primary_checkout=args.primary,
        cwd=Path.cwd(),
        halt_log_path=halt_log,
    )
    write_ledger(outcome.ledger, args.ledger)

    print(format_ledger_text(outcome.ledger))
    if outcome.exit_code != 0:
        print("--- HALT: failing gate output (preserved) ---")
        print(outcome.gate.output)
        print(f"halt log: {outcome.entry.halt_log}")
    return outcome.exit_code


def _cmd_status(args: argparse.Namespace) -> int:
    ledger = read_ledger(args.ledger)
    complete = is_green_complete(ledger)
    # Defense-in-depth (deliberately NOT inside the pure predicate): never report
    # "done" while a rebase is still mid-flight in the worktree, even if the
    # ledger reads green-complete. Only checked when --worktree is supplied.
    wt = Path(args.worktree) if args.worktree is not None else None
    rebase_live = False
    if wt is not None and wt.exists():
        try:
            rebase_live = rebase_in_progress(wt)
        except GitError:
            rebase_live = False

    if args.json:
        payload = ledger_to_dict(ledger)
        payload["rebase_in_progress"] = rebase_live
        payload["reported_done"] = complete and not rebase_live
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_ledger_text(ledger))
        if complete and rebase_live:
            print(
                "WARNING: ledger reads green-complete but a rebase is still in "
                f"progress in {wt}; refusing to report done"
            )
    # Exit non-zero unless honestly green-complete AND no rebase mid-flight, so a
    # CI/loop step gates on the process exit code, not a scraped string.
    return 0 if (complete and not rebase_live) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Green-between-buckets rebase executor built on tools.ops.rebase_preflight.")
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["plan", "begin", "gate", "status"],
        default="plan",
        help="plan (default): show ordered buckets; begin/gate/status drive the rebase.",
    )
    parser.add_argument("--plan", type=Path, help="path to `rebase_preflight --json` output")
    parser.add_argument(
        "--dry-run", action="store_true", help="plan mode: print only, mutate nothing"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--worktree",
        type=Path,
        default=None,
        help=(
            "disposable worktree for begin/gate (defaults to "
            f"{DEFAULT_DISPOSABLE_WORKTREE}); for status, enables the runtime "
            "rebase-in-progress check when supplied."
        ),
    )
    parser.add_argument(
        "--primary", type=Path, default=ROOT, help="the primary checkout to protect"
    )
    parser.add_argument("--base", default="HEAD", help="base ref for a created worktree")
    parser.add_argument("--onto", default=DEFAULT_ONTO, help="ref to rebase onto")
    parser.add_argument(
        "--create", action="store_true", help="create the disposable worktree if absent"
    )
    parser.add_argument("--bucket", help="bucket name for `gate`")
    parser.add_argument("--scope", choices=["bucket", "full"], default="bucket")
    parser.add_argument(
        "--final", action="store_true", help="treat this bucket as final (forces --scope full)"
    )
    parser.add_argument("--no-mark-resolved", dest="mark_resolved", action="store_false")
    parser.add_argument(
        "--timestamp-in",
        default=None,
        help=(
            "REQUIRED for `gate`: caller-supplied ISO timestamp recorded in the "
            "ledger. Passed in (never clock-read) so a replayed run is deterministic."
        ),
    )
    parser.add_argument("--python", default=DEFAULT_PYTHON)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.set_defaults(mark_resolved=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "plan":
        if args.plan is None:
            parser.error("plan mode requires --plan <path>")
        return _cmd_plan(args)
    if args.command == "begin":
        if args.plan is None:
            parser.error("begin requires --plan <path>")
        return _cmd_begin(args)
    if args.command == "gate":
        if args.plan is None or args.bucket is None or not args.timestamp_in:
            parser.error(
                "gate requires --plan <path>, --bucket <name>, and --timestamp-in "
                "<iso> (the timestamp is passed in for a deterministic/replayable "
                "ledger; the tool never reads the clock)"
            )
        return _cmd_gate(args)
    if args.command == "status":
        return _cmd_status(args)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
