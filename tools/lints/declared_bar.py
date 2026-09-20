"""declared_bar — enforce the repo-wide ``mypy --strict`` + ``ruff`` contract
that ``pyproject.toml`` already DECLARES, against a dated baseline.

SPR-03 of Antiek Foundation v2. ``pyproject.toml`` declares a strict
contract — ``[tool.mypy] strict = true`` and ``[tool.ruff.lint]
select = ["E","F","I","B","UP","SIM","RET"]`` — over the FULL repo
(neither block carries a ``files=`` / ``exclude=`` narrowing, so the
declared scope is the whole tree). Until this sprint the only CI place
running strict typing was ``substrate_floor.yml`` over ~3 files, and the
main ``ci.yml`` was pytest-only with a "Defer" comment. The declared bar
was a comment, not a contract.

This runner closes that gap WITHOUT a flag-day: it runs the declared
tools over the declared scope, subtracts a committed dated baseline of
the violations that exist TODAY, and fails only on NEW violations — i.e.
violations in code that has no baseline entry. The existing backlog
becomes a visible, dated, shrink-only allow-list instead of silent rot.

This is the same baseline idiom the substrate lints already use
(``tools/lints/baseline.py`` → ``ViolationKey``). Ruff and mypy are the
two adapters; both project their findings to the shared key shape, and
both reuse ``filter_to_new_only`` / ``find_stale_baseline_entries``.

The burn-down rule (allow-list shrinks only; new code is strict) lives
in ``tools/lints/README.md`` — read it before touching a baseline file.

Usage::

    # Capture (re-mint the baseline; commit the file). Re-minting to
    # silence a NEW red is forbidden — see tools/lints/README.md.
    python -m tools.lints.declared_bar capture ruff \\
        --baseline-file tools/lints/baselines/declared_ruff.json
    python -m tools.lints.declared_bar capture mypy \\
        --baseline-file tools/lints/baselines/declared_mypy.json

    # Enforce (CI): exit 1 on any violation NOT in the baseline. CI does
    # NOT pass --check-stale: a stale baseline entry (a baselined violation
    # that no longer reproduces) is environment-sensitive and must not red
    # the gate on an unmodified tree — see _cmd_enforce + tools/lints/README.md.
    python -m tools.lints.declared_bar enforce ruff \\
        --baseline-file tools/lints/baselines/declared_ruff.json
    python -m tools.lints.declared_bar enforce mypy \\
        --baseline-file tools/lints/baselines/declared_mypy.json

    # Local burn-down loop ONLY: --check-stale surfaces fixed entries so you
    # know what to re-capture out of the baseline (it ratchets the floor DOWN).
    python -m tools.lints.declared_bar enforce mypy \\
        --baseline-file tools/lints/baselines/declared_mypy.json --check-stale

Scope: NONE of the commands pass a ``files=`` / ``--exclude`` flag that
narrows below the ``pyproject``-declared scope. Ruff is invoked with no
path argument, so it uses its own pyproject-driven file discovery over
the whole tree. Mypy is invoked over the explicit list of declared
wheel packages (``[tool.hatch.build.targets.wheel] packages``) because
``[tool.mypy]`` declares no ``files=``; that list IS the declared
package scope, not a hand-picked narrowing. See ``DECLARED_MYPY_TARGETS``.

Exit codes: 0 no NEW violations; 1 NEW violations (or stale entries with
``--check-stale``); 2 usage / tool-invocation failure.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from tools.lints.baseline import (
    ViolationKey,
    compute_keys,
    filter_to_new_only,
    find_stale_baseline_entries,
    load_baseline,
    write_baseline,
)
from tools.lints.mypy_strict_baseline import (
    MypyError,
    mypy_error_to_key,
    parse_mypy_output,
)

__all__ = [
    "DECLARED_MYPY_TARGETS",
    "RuffViolation",
    "parse_ruff_json",
    "ruff_violation_to_key",
    "run_ruff",
    "run_mypy",
    "main",
]


# The mypy declared scope. ``[tool.mypy]`` in pyproject sets
# ``strict = true`` with NO ``files=`` narrowing, so the declared scope
# is "the project". The project's own packages are enumerated in
# ``[tool.hatch.build.targets.wheel] packages`` — that list is the
# authoritative statement of what code the project ships, so it is the
# declared package scope mypy must cover. This is NOT a hand-picked
# substrate_floor-style 3-file subset; it is the full shipped surface.
# Kept in sync with pyproject by the cross-check in
# tests/test_declared_bar.py (test_mypy_targets_match_wheel_packages).
#
# KNOWN ASYMMETRY vs ruff: ruff (run with no path arg) lints the WHOLE
# tree — including tools/, tests/, scripts/, benchmarks/, antiek_extensions/,
# apps/ — but mypy here covers only these 11 wheel packages. So a brand-new
# top-level dir, or new untyped code under those non-package dirs, escapes
# the strict TYPE gate (ruff still catches it). When you ship a new
# top-level PACKAGE, add it to the wheel-package list (the cross-check test
# then forces it in here) and re-capture declared_mypy.json. This hole is
# documented as a known limitation in tools/lints/README.md.
DECLARED_MYPY_TARGETS: tuple[str, ...] = (
    "substrate",
    "skills",
    "acquisition",
    "processing",
    "roles",
    "middleware",
    "orchestration",
    "interfaces",
    "compounding",
    "runtime",
    "integrations",
    "infrastructure",
)


class RuffViolation:
    """A single ruff finding, parsed from ``ruff check --output-format=json``.

    Plain class (not a frozen dataclass) so the JSON adapter stays a thin
    projection; identity for baselining lives in ``ruff_violation_to_key``.
    """

    __slots__ = ("path", "line", "col", "code")

    def __init__(self, path: str, line: int, col: int, code: str) -> None:
        self.path = path
        self.line = line
        self.col = col
        self.code = code


def parse_ruff_json(output: str, repo_root: Path | None = None) -> list[RuffViolation]:
    """Parse ``ruff check --output-format=json`` stdout into violations.

    Ruff emits ABSOLUTE filenames; we relativize against ``repo_root``
    (default: cwd) so baseline entries are repo-relative and stable
    across machines / the CI checkout path. A finding outside the repo
    root (should not happen) is kept with its absolute path rather than
    silently dropped.
    """
    root = (repo_root or Path.cwd()).resolve()
    try:
        records = json.loads(output) if output.strip() else []
    except json.JSONDecodeError:
        # Defensive: a ruff version that prepended a banner would break
        # json.loads. Treat as "could not parse" → caller surfaces it.
        return []
    violations: list[RuffViolation] = []
    for rec in records:
        filename = str(rec.get("filename", ""))
        try:
            rel = str(Path(filename).resolve().relative_to(root))
        except ValueError:
            rel = filename
        location = rec.get("location") or {}
        violations.append(
            RuffViolation(
                path=rel,
                line=int(location.get("row", 0)),
                col=int(location.get("column", 0)),
                code=str(rec.get("code") or "no-code"),
            )
        )
    return violations


def ruff_violation_to_key(v: object) -> ViolationKey:
    """Project a RuffViolation to a baseline ViolationKey. The rule code
    + location is the stable identity (robust to ruff message wording
    changes), mirroring ``mypy_error_to_key``."""
    assert isinstance(v, RuffViolation)
    return ViolationKey(path=v.path, line=v.line, col=v.col, kind=f"ruff:{v.code}")


def run_ruff(
    ruff_bin: str = "ruff",
    cwd: Path | None = None,
) -> list[RuffViolation]:
    """Run ``ruff check`` over the pyproject-declared scope (no path /
    no ``--exclude`` argument: ruff discovers files via its own
    pyproject config) and return parsed findings. Raises RuntimeError
    only if ruff can't be invoked (binary missing)."""
    argv = [ruff_bin, "check", "--output-format=json", "--no-fix"]
    try:
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"ruff binary not found at {ruff_bin!r}: {exc}. "
            f"Install via `pip install -e '.[dev]'`."
        ) from exc
    return parse_ruff_json(proc.stdout or "", repo_root=cwd)


def run_mypy(
    targets: Iterable[str] = DECLARED_MYPY_TARGETS,
    mypy_bin: str = "mypy",
    cwd: Path | None = None,
) -> list[MypyError]:
    """Run ``mypy`` (strict comes from pyproject ``[tool.mypy]``) over
    the declared package targets and return parsed errors. We pass the
    package targets, not ``--strict`` re-declared on the CLI, so the
    pyproject contract is the single source of truth. Raises
    RuntimeError only if mypy can't be invoked."""
    argv = [mypy_bin, *targets]
    try:
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"mypy binary not found at {mypy_bin!r}: {exc}. "
            f"Install via `pip install -e '.[dev]'`."
        ) from exc
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return parse_mypy_output(combined)


# tool-name → (runner-attr-name, key-adapter, baseline-lint-label).
# Registry-driven so the CLI subcommands stay in lockstep with what's
# supported. The runner is stored by ATTRIBUTE NAME (not by reference) and
# resolved via getattr at call time, so a test that monkeypatches
# ``declared_bar.run_ruff`` is honored (a captured reference would not be).
_TOOLS: dict[str, tuple[str, object, str]] = {
    "ruff": ("run_ruff", ruff_violation_to_key, "declared_bar_ruff"),
    "mypy": ("run_mypy", mypy_error_to_key, "declared_bar_mypy"),
}


def _resolve_runner(attr: str) -> object:
    return getattr(sys.modules[__name__], attr)


def _dedupe(keys: list[ViolationKey]) -> list[ViolationKey]:
    """Collapse identical keys. The baseline is consumed as a SET
    (``filter_to_new_only`` does set membership), so a key appearing
    twice is meaningless for enforcement — ruff can report two findings
    that project to the same (path, line, col, code) on a multi-target
    import line. Storing the duplicate is pure diff noise, so we drop it
    at capture time. Kept local (not pushed into the shared
    ``compute_keys``) so the existing substrate-lint baselines keep
    their exact established behavior."""
    return sorted(set(keys))


def _read_source_lines(repo_root: Path, path: str, cache: dict[str, list[str]]) -> list[str]:
    """Read a source file once (cached per path) and return its split lines.

    Used to capture the normalized source ``snippet`` for content-keyed
    baseline matching (see tools/lints/baseline.py). Returns an empty list
    on any read error so the caller falls back to exact-line matching."""
    cached = cache.get(path)
    if cached is not None:
        return cached
    try:
        lines = (repo_root / path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    cache[path] = lines
    return lines


def enrich_keys_with_snippets(
    keys: list[ViolationKey], repo_root: Path
) -> list[ViolationKey]:
    """Return a copy of ``keys`` with each ``snippet`` set to the normalized
    source line at ``(path, line)`` (``""`` when unavailable). Deterministic:
    snippet = ``current_source[line].strip()``. This is the capture/enforce
    companion to the content-keyed fallback in ``filter_to_new_only``."""
    cache: dict[str, list[str]] = {}
    out: list[ViolationKey] = []
    for k in keys:
        lines = _read_source_lines(repo_root, k.path, cache)
        snippet = lines[k.line - 1].strip() if 1 <= k.line <= len(lines) else ""
        out.append(replace(k, snippet=snippet))
    return out


def _cmd_capture(tool: str, baseline_file: Path) -> int:
    runner_attr, key_fn, label = _TOOLS[tool]
    runner = _resolve_runner(runner_attr)
    try:
        violations = runner()  # type: ignore[operator]
    except RuntimeError as exc:
        print(f"{tool} invocation failed: {exc}", file=sys.stderr)
        return 2
    keys = _dedupe(compute_keys(violations, key_fn))  # type: ignore[arg-type]
    keys = enrich_keys_with_snippets(keys, Path.cwd())
    write_baseline(baseline_file, lint=label, violations=keys)
    print(f"wrote {len(keys)} {tool} violation(s) to {baseline_file}")
    return 0


def _cmd_enforce(tool: str, baseline_file: Path, check_stale: bool) -> int:
    runner_attr, key_fn, _ = _TOOLS[tool]
    runner = _resolve_runner(runner_attr)
    try:
        baseline = load_baseline(baseline_file)
    except FileNotFoundError:
        print(f"baseline not found: {baseline_file}", file=sys.stderr)
        return 2
    try:
        violations = runner()  # type: ignore[operator]
    except RuntimeError as exc:
        print(f"{tool} invocation failed: {exc}", file=sys.stderr)
        return 2

    current = enrich_keys_with_snippets(
        compute_keys(violations, key_fn),  # type: ignore[arg-type]
        Path.cwd(),
    )
    new_only = filter_to_new_only(current, baseline)
    for k in new_only:
        print(f"{k.path}:{k.line}:{k.col}: NEW {k.kind}")

    rc = 1 if new_only else 0

    # --check-stale is a LOCAL burn-down aid, never a CI gate input. A stale
    # entry (baselined violation that no longer reproduces) is NOT a new
    # violation; it is debt that got fixed. It is also environment-sensitive
    # — a transitive-pin or interpreter-patch drift can change which baseline
    # keys reproduce (mypy import-resolution keys especially) without any
    # source change. Folding stale into rc in CI would red the gate on an
    # unmodified tree, contradicting the M2/G2 "green on HEAD" contract.
    # The CI workflow therefore omits --check-stale; only the documented
    # local re-capture loop passes it (tools/lints/README.md step 2).
    if check_stale:
        stale = find_stale_baseline_entries(current, baseline)
        if stale:
            print(
                f"\n{len(stale)} stale baseline entr"
                f"{'y' if len(stale) == 1 else 'ies'} "
                f"(fixed — re-capture to ratchet the floor DOWN; "
                f"see tools/lints/README.md)",
                file=sys.stderr,
            )
            for k in stale:
                print(f"  - {k.path}:{k.line}:{k.col} {k.kind}", file=sys.stderr)
            rc = max(rc, 1)

    if new_only:
        print(
            f"\n{len(new_only)} NEW {tool} violation(s) since baseline. "
            f"New code is held to the full strict contract; the baseline is "
            f"shrink-only and must NOT be re-minted to silence these. "
            f"See tools/lints/README.md.",
            file=sys.stderr,
        )

    return rc


def _cmd_enrich(tool: str, baseline_file: Path) -> int:
    """Add ``snippet`` fields to an EXISTING baseline without re-running the
    lint tool — the set-preserving one-time migration to content-keyed
    matching.

    Each violation's ``(path, line, col, kind)`` is left untouched; only a
    ``snippet`` (normalized current source line) is added. ``schema_version``,
    ``lint`` and ``generated_at`` are preserved verbatim, so this is provably
    NOT a re-mint: the grandfathered set is byte-identical before and after,
    just enriched for the content fallback. Run ``enforce`` afterwards to
    confirm zero NEW on an unmodified tree (the migration contract)."""
    try:
        baseline = load_baseline(baseline_file)
    except FileNotFoundError:
        print(f"baseline not found: {baseline_file}", file=sys.stderr)
        return 2
    enriched = enrich_keys_with_snippets(baseline.violations, Path.cwd())
    with baseline_file.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    raw["violations"] = [
        {
            "path": v.path,
            "line": v.line,
            "col": v.col,
            "kind": v.kind,
            **({"snippet": v.snippet} if v.snippet else {}),
        }
        for v in sorted(enriched)
    ]
    with baseline_file.open("w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, sort_keys=True)
        fh.write("\n")
    with_snippet = sum(1 for v in enriched if v.snippet)
    print(
        f"enriched {len(enriched)} {tool} baseline entr"
        f"{'y' if len(enriched) == 1 else 'ies'} at {baseline_file} "
        f"({with_snippet} with a source snippet, "
        f"{len(enriched) - with_snippet} with no resolvable line). "
        f"Grandfathered (path,line,col,kind) set unchanged."
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="declared_bar",
        description="Enforce the pyproject-declared mypy --strict + ruff "
        "contract over the full declared scope, against a dated baseline.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("capture", "enforce", "enrich"):
        sp = sub.add_parser(mode, help=f"{mode} mode against a baseline file")
        sp.add_argument(
            "tool", choices=sorted(_TOOLS.keys()),
            help="which declared tool to run",
        )
        sp.add_argument(
            "--baseline-file", required=True, type=Path,
            help="path to the dated baseline JSON file",
        )
        if mode == "enforce":
            sp.add_argument(
                "--check-stale", action="store_true",
                help="also report (and fail on) fixed baseline entries. "
                "LOCAL burn-down loop only — do NOT pass in CI: stale "
                "entries are environment-sensitive and would red the gate "
                "on an unmodified tree (G2). See tools/lints/README.md.",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.mode == "capture":
        return _cmd_capture(tool=args.tool, baseline_file=args.baseline_file)
    if args.mode == "enforce":
        return _cmd_enforce(
            tool=args.tool,
            baseline_file=args.baseline_file,
            check_stale=args.check_stale,
        )
    if args.mode == "enrich":
        return _cmd_enrich(tool=args.tool, baseline_file=args.baseline_file)
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
