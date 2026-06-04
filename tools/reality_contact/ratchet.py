"""The one-way reality-contact ratchet — ``python -m tools.reality_contact.ratchet``.

SPR-04. SPR-01 emits the ledger; SPR-02 prints the RCR; THIS installs the teeth.
It compares the *current* ledger against a committed ``baseline.json`` and fails
CI iff reality contact has *regressed* — a new core-mock (theater) test appeared
that nobody recorded, or a previously-real claim turned into a mock. It never
edits a test and never removes a mock: it only refuses to let the number slide.

WHY THE THEATER SET — AND NOT RAW RCR — IS THE LOAD-BEARING GATE
---------------------------------------------------------------
The disease this whole instrument exists to kill is "mock a CORE symbol, then
assert against the mock's own return value." That act has a precise, observable
signature in the ledger: a ``theater`` label backed by ``core_mock_evidence`` (a
mock target that statically resolved onto a CORE symbol). The ratchet's PRIMARY
one-way signal is therefore the SET of theater tests, keyed stably:

    TheaterKey(path, subsystem, target)

A current theater key that is in NEITHER the baseline ``theater`` set NOR the
recorded ``exemptions`` is a NEW, un-recorded core-mock → FAIL, naming the exact
``path:line:symbol``. Today the baseline theater set is empty, so ANY new
core-mock fails unless it is exempted with a written reason. That is the strong,
unforgeable guard: you cannot satisfy this gate silently.

WHY NOT A NAIVE RCR FLOOR (the false-alarm this module deliberately avoids)
--------------------------------------------------------------------------
A tempting secondary gate is "current RCR(S) < baseline RCR(S) → fail." It has a
FALSE ALARM. RCR(S) = reality(S) / claiming(S). Adding an *indeterminate* test
(an unresolvable mock the classifier conservatively excludes from ``reality``)
raises ``claiming(S)`` while leaving ``reality(S)`` flat — so RCR(S) DROPS even
though nobody mocked a core. Per ``metric.py``'s contract an indeterminate label
"can only ever HOLD RCR DOWN or LEAVE IT FLAT." A raw-RCR floor would red-flag an
honestly-added indeterminate test as a regression — punishing correct, cautious
engineering (writing a test the classifier can't fully resolve) and creating
pressure to delete the gate. That is exactly backwards.

So the SECONDARY floor is expressed on the REALITY-COUNT / THEATER-COUNT
DIRECTION, never on raw RCR:

    A subsystem REGRESSES iff a (file, subsystem) claim that was ``reality`` at
    baseline is now ``theater`` — i.e. a real test was hollowed into a mock.

This is the only RCR-lowering event that is actually a "mocked the core"
regression. It is detected structurally: a baseline reality claim
(path, subsystem) that now carries a ``theater`` label. By construction:

  * Adding an INDETERMINATE test raises claiming + indeterminate only — it is
    NOT a baseline-reality claim flipping to theater, so it CANNOT trip this
    floor. (This is the mandatory false-alarm-avoidance case; see the M5 test.)
  * Adding a new CLAIMING (reality) test only adds reality — never trips it.
  * A brand-new theater test on a NEW (path, subsystem) is caught by the
    PRIMARY theater-set gate above, not double-counted here.

The two checks compose: the theater-set growth check catches *new* core-mocks;
the reality-flip check catches *existing real* tests being hollowed out. Both
are one-way (the floor only ratchets UP) and both have a recorded-exemption
escape hatch so a legitimate error-path core-mock is permitted — but never
silent.

ARE RECONCILIATION (rigor #4 — quoted by SPR-06)
------------------------------------------------
The repo's baseline philosophy is ``tools/lints/baseline.py``: a versioned JSON
envelope (``schema_version``) holding a SET of grandfathered offenses keyed by a
frozen, sortable tuple, with a "flag only NEW relative to baseline" predicate
(``filter_to_new_only``) and a "shrink-only" spirit (``find_stale_baseline_entries``
surfaces fixed entries). The reality-contact theater set is the SAME shape — a
JSON set of keyed offenses that may only SHRINK silently and may only GROW with a
recorded entry. We REUSE that philosophy and its conventions (JSON, ``schema_version``,
provenance, sorted-deterministic, append-an-exemption-to-grow) rather than fork a
parallel scheme. We do NOT import ``baseline.py`` directly: its ``ViolationKey`` is a
4-field (path, line, col, kind) lint tuple and its ``BaselineSchema`` carries a
single flat ``violations`` list; the reality-contact baseline additionally needs
per-subsystem reality/theater/claiming floors and a separate exemptions list with
rationales, which is a richer envelope than the lint shape. So the new
``baseline.json`` FOLLOWS ARE's conventions (same JSON/provenance/shrink-only
spirit) in a baseline file of its own, exactly as the ARE Wave-4 ADR anticipated
("a third lint joins with one entry" — here a third *baseline shape* joins by
matching the conventions, not the dataclass).

EXIT-CODE SEMANTICS (defensibility — mirrors the repo gate convention)
----------------------------------------------------------------------
  * 0 — current contact is >= baseline on every axis (no new un-exempted core-mock,
        no reality claim hollowed to theater). Improvements pass and are reported.
  * 1 — a REGRESSION: a new un-exempted theater test, or a baseline reality claim
        now theater. The diff names the exact offender(s).
  * 2 — a USAGE / INPUT error (missing or unreadable baseline/ledger, ``--accept``
        without ``--reason``). Distinct from a regression so CI can tell "the gate
        found a problem" from "the gate could not run."

The CI INVOCATION (wiring ratchet.py into a workflow) is SPR-05's job; this
module delivers the comparison logic + the exemption CLI + its unit tests only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.reality_contact import REPO_ROOT
from tools.reality_contact.ledger import build_ledger
from tools.reality_contact.metric import THEATER_LABEL, compute_metric

# The committed baseline lives beside the ledger it was frozen from.
BASELINE_PATH: Path = Path(__file__).resolve().parent / "baseline.json"

BASELINE_SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_USAGE = 2


# --------------------------------------------------------------------------- #
# Stable theater key — robust to file MOVES within a path and line SHIFTS.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, order=True)
class TheaterKey:
    """Identity of "this test file mocks this CORE symbol."

    Sortable (path-major) for deterministic baseline/exemption files. The key is
    ``(path, subsystem, target)`` and DELIBERATELY excludes ``lineno``: a mock
    moving up or down within the same file is the SAME offense, not a new one, so
    line churn must not spuriously create or clear a theater entry. ``target`` is
    the dotted CORE symbol that was mocked (the load-bearing identity — *what*
    core was faked), ``subsystem`` is the CORE module it resolved under. ``lineno``
    is carried alongside (in ``TheaterHit``) for the human-readable diff, but it is
    not part of identity.

    Granularity consequence: two distinct mock SITES of the SAME ``target`` in the
    SAME ``path`` collapse to one key, so once a file is exempted for faking a
    symbol a second mock of that same symbol in that file is not a new offense. A
    mock of a DIFFERENT core symbol (or in a different file) is still caught — the
    secondary count floor is per-``(path, subsystem)``, not per-call-site. This is
    intentional (an exemption justified "this file may fake this symbol"), not a
    hole; widen the key to include ``lineno`` only if per-site accounting is ever
    needed.
    """

    path: str
    subsystem: str
    target: str


@dataclass(frozen=True)
class TheaterHit:
    """A theater key plus the line + form, for the offender diff message."""

    key: TheaterKey
    lineno: int
    form: str


def _theater_hits(ledger: dict[str, Any]) -> list[TheaterHit]:
    """Every (file mocks core symbol) hit in a ledger, from ``core_mock_evidence``.

    Each ``core_mock_evidence`` entry is a statically-resolved mock target that
    landed on a CORE symbol — the exact, auditable signature of theater. We read
    it straight from the ledger (no re-classification) so the ratchet measures the
    same artifact SPR-02 scores. Sorted for determinism.
    """
    hits: list[TheaterHit] = []
    for entry in ledger.get("files", []):
        path = str(entry.get("path", ""))
        for ev in entry.get("core_mock_evidence") or []:
            hits.append(
                TheaterHit(
                    key=TheaterKey(
                        path=path,
                        subsystem=str(ev["subsystem"]),
                        target=str(ev["target"]),
                    ),
                    lineno=int(ev.get("lineno", 0)),
                    form=str(ev.get("form", "")),
                )
            )
    return sorted(hits, key=lambda h: (h.key, h.lineno, h.form))


def _theater_claims(ledger: dict[str, Any]) -> set[tuple[str, str]]:
    """The set of (path, subsystem) claims labelled ``theater`` in a ledger."""
    claims: set[tuple[str, str]] = set()
    for entry in ledger.get("files", []):
        path = str(entry.get("path", ""))
        for subsystem, label in (entry.get("subsystem_labels") or {}).items():
            if label == THEATER_LABEL:
                claims.add((path, str(subsystem)))
    return claims


# --------------------------------------------------------------------------- #
# Baseline model.
# --------------------------------------------------------------------------- #
@dataclass
class Exemption:
    """A recorded, justified core-mock. The fairness escape hatch: a legitimate
    error-path mock (force the orchestrator to raise) is permitted — but never
    silent. Carries the rationale + provenance of when it was accepted."""

    path: str
    subsystem: str
    target: str
    reason: str
    accepted_at: str

    @property
    def key(self) -> TheaterKey:
        return TheaterKey(self.path, self.subsystem, self.target)


@dataclass
class Baseline:
    schema_version: int
    theater: list[TheaterKey]
    exemptions: list[Exemption]
    # The per-subsystem floor counts + provenance are preserved verbatim on
    # round-trip (we never lower them; the exemption path appends only).
    raw: dict[str, Any]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Baseline:
        ver = data.get("schema_version")
        if ver != BASELINE_SCHEMA_VERSION:
            raise ValueError(
                f"baseline schema_version is {ver!r}; expected "
                f"{BASELINE_SCHEMA_VERSION}. Re-freeze or migrate the baseline."
            )
        theater = [
            TheaterKey(
                path=str(t["path"]),
                subsystem=str(t["subsystem"]),
                target=str(t["target"]),
            )
            for t in data.get("theater", [])
        ]
        exemptions = [
            Exemption(
                path=str(e["path"]),
                subsystem=str(e["subsystem"]),
                target=str(e["target"]),
                reason=str(e["reason"]),
                accepted_at=str(e.get("accepted_at", "")),
            )
            for e in data.get("exemptions", [])
        ]
        return cls(
            schema_version=int(ver),
            theater=theater,
            exemptions=exemptions,
            raw=data,
        )

    def to_json(self) -> dict[str, Any]:
        out = dict(self.raw)
        out["schema_version"] = self.schema_version
        out["theater"] = [
            {"path": t.path, "subsystem": t.subsystem, "target": t.target}
            for t in sorted(self.theater)
        ]
        out["exemptions"] = [
            {
                "path": e.path,
                "subsystem": e.subsystem,
                "target": e.target,
                "reason": e.reason,
                "accepted_at": e.accepted_at,
            }
            for e in sorted(
                self.exemptions, key=lambda e: (e.path, e.subsystem, e.target)
            )
        ]
        return out

    def allowed_keys(self) -> set[TheaterKey]:
        """Theater keys that are NOT a regression: the frozen baseline set plus
        every recorded exemption. A current theater key outside this set is a
        new, un-recorded core-mock."""
        return set(self.theater) | {e.key for e in self.exemptions}

    def theater_floor(self) -> dict[str, int]:
        """Per-subsystem frozen theater COUNT (the secondary-floor input). A
        subsystem's current theater count may not exceed this floor plus the
        exemptions recorded for it. All zero today. Read from the committed
        per-subsystem block so the floor is exactly the frozen number, not
        re-derived from the live ledger."""
        out: dict[str, int] = {}
        for subsystem, counts in (self.raw.get("subsystems") or {}).items():
            out[str(subsystem)] = int(counts.get("theater", 0))
        return out

    def exemptions_per_subsystem(self) -> dict[str, int]:
        """How many exemptions are recorded per subsystem — the permitted headroom
        above the frozen theater floor for that subsystem."""
        out: dict[str, int] = {}
        for e in self.exemptions:
            out[e.subsystem] = out.get(e.subsystem, 0) + 1
        return out


def load_baseline(path: Path = BASELINE_PATH) -> Baseline:
    with path.open("r", encoding="utf-8") as fh:
        return Baseline.from_json(json.load(fh))


def write_baseline(baseline: Baseline, path: Path = BASELINE_PATH) -> None:
    """Deterministic write (sorted sets, trailing newline) — diffs cleanly,
    matching the ARE baseline convention."""
    with path.open("w", encoding="utf-8") as fh:
        json.dump(baseline.to_json(), fh, indent=2, sort_keys=True)
        fh.write("\n")


# --------------------------------------------------------------------------- #
# Provenance — recomputable so an exemption records the contract it was added
# against, exactly as the frozen baseline records the contract it was frozen
# against.
# --------------------------------------------------------------------------- #
def ledger_content_hash(ledger: dict[str, Any]) -> str:
    """A stable SHA-256 over the METRIC-RELEVANT slice of the ledger only:
    ``core_modules`` + each file's ``path`` / ``subsystem_labels`` /
    ``core_mock_evidence``. A cosmetic ledger change (reordered blind-spot prose)
    leaves this hash unchanged; any change to the measured contact does not."""
    relevant = {
        "core_modules": list(ledger.get("core_modules") or []),
        "files": [
            {
                "path": str(f.get("path", "")),
                "subsystem_labels": f.get("subsystem_labels") or {},
                "core_mock_evidence": f.get("core_mock_evidence") or [],
            }
            for f in ledger.get("files", [])
        ],
    }
    blob = json.dumps(relevant, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# The comparison.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FloorBreach:
    """A subsystem whose CURRENT theater count exceeds its frozen floor + the
    exemptions recorded for it. The secondary, aggregate guarantee."""

    subsystem: str
    floor: int
    exempted: int
    current: int


@dataclass(frozen=True)
class RatchetResult:
    exit_code: int
    # New, un-exempted theater hits (the PRIMARY gate). Names the exact mock.
    new_theater: tuple[TheaterHit, ...]
    # Per-subsystem theater-count floor breaches (the SECONDARY, aggregate gate).
    floor_breaches: tuple[FloorBreach, ...]
    # Improvements, reported as progress (not a failure).
    cleared_theater: tuple[TheaterKey, ...]
    new_reality: int
    report: str


def evaluate(
    current_ledger: dict[str, Any],
    baseline: Baseline,
) -> RatchetResult:
    """Pure comparison: current ledger vs committed baseline. No I/O.

    FAIL (exit 1) iff EITHER:
      (a) PRIMARY — a current theater KEY is in neither the baseline theater set
          nor the exemptions: a NEW, un-recorded core-mock (named to file:line:symbol); OR
      (b) SECONDARY — a subsystem's current theater COUNT exceeds its frozen floor
          plus the exemptions recorded for it: the aggregate per-subsystem ceiling
          was breached.
    Otherwise exit 0, reporting improvements (theater keys that cleared, reality
    gained) as progress.

    WHY (b) IS A THEATER-COUNT FLOOR, NOT AN RCR FLOOR — and why an INDETERMINATE
    add can never trip it: RCR(S) = reality(S)/claiming(S), and adding an
    indeterminate test raises claiming(S) + indeterminate(S) only, leaving
    reality(S) AND theater(S) untouched — so an RCR floor would (wrongly) fire,
    but this theater-COUNT floor cannot, because theater(S) did not move. The only
    way to breach (b) is to actually add theater for that subsystem, which is a
    real "mocked the core" event — never an honestly-added indeterminate test.
    (a) and (b) are complementary, not redundant: (a) pinpoints WHICH mock is new
    (so the diff names the offender); (b) is the per-subsystem aggregate ceiling
    that holds even if a key were re-pathed, and reads the FROZEN counts straight
    from the committed baseline rather than re-deriving them.
    """
    allowed = baseline.allowed_keys()
    current_hits = _theater_hits(current_ledger)
    current_theater_keys = {h.key for h in current_hits}

    # (a) PRIMARY: new un-exempted theater, named to the exact mock.
    new_theater = tuple(h for h in current_hits if h.key not in allowed)

    # (b) SECONDARY: per-subsystem theater-COUNT floor (indeterminate-safe; see
    # docstring). current theater count per subsystem must not exceed the frozen
    # floor + recorded exemptions for that subsystem.
    floor = baseline.theater_floor()
    exempted = baseline.exemptions_per_subsystem()
    current_theater_count: dict[str, int] = {}
    for _path, subsystem in _theater_claims(current_ledger):
        current_theater_count[subsystem] = current_theater_count.get(subsystem, 0) + 1
    breaches: list[FloorBreach] = []
    for subsystem in sorted(set(floor) | set(current_theater_count)):
        cur = current_theater_count.get(subsystem, 0)
        ceiling = floor.get(subsystem, 0) + exempted.get(subsystem, 0)
        if cur > ceiling:
            breaches.append(
                FloorBreach(
                    subsystem=subsystem,
                    floor=floor.get(subsystem, 0),
                    exempted=exempted.get(subsystem, 0),
                    current=cur,
                )
            )
    floor_breaches = tuple(breaches)

    # Improvements — reported, never failing. The reality-claim total comes from
    # the SHARED metric module (compute_metric), never a re-implementation of RCR:
    # the ratchet measures the same numerator the SPR-02 scoreboard prints.
    cleared_theater = tuple(sorted(set(baseline.theater) - current_theater_keys))
    new_reality = compute_metric(current_ledger).total_reality

    regressed = bool(new_theater) or bool(floor_breaches)
    exit_code = EXIT_REGRESSION if regressed else EXIT_OK

    report = _render_report(
        new_theater=new_theater,
        floor_breaches=floor_breaches,
        cleared_theater=cleared_theater,
        exit_code=exit_code,
    )
    return RatchetResult(
        exit_code=exit_code,
        new_theater=new_theater,
        floor_breaches=floor_breaches,
        cleared_theater=cleared_theater,
        new_reality=new_reality,
        report=report,
    )


def _render_report(
    new_theater: Iterable[TheaterHit],
    floor_breaches: Iterable[FloorBreach],
    cleared_theater: Iterable[TheaterKey],
    exit_code: int,
) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("  REALITY-CONTACT RATCHET — one-way gate vs committed baseline")
    lines.append("=" * 78)

    new_theater = list(new_theater)
    floor_breaches = list(floor_breaches)
    cleared_theater = list(cleared_theater)

    if exit_code == EXIT_OK:
        lines.append("  PASS — no regression. Reality contact is >= the frozen floor.")
        if cleared_theater:
            lines.append("")
            lines.append("  Progress (theater cleared since baseline):")
            for k in cleared_theater:
                lines.append(f"    + {k.path} :: {k.subsystem} :: {k.target}")
        return "\n".join(lines)

    lines.append("  FAIL — reality contact REGRESSED below the frozen floor.")
    lines.append("")
    if new_theater:
        lines.append(
            "  NEW un-recorded core-mock(s) — a test mocks a CORE symbol that is in"
        )
        lines.append(
            "  neither the baseline theater set nor exemptions. Each is the exact"
        )
        lines.append("  file:line:symbol that regressed:")
        for h in new_theater:
            lines.append(
                f"    ! {h.key.path}:{h.lineno}:{h.key.target}  "
                f"(subsystem {h.key.subsystem}, form {h.form})"
            )
        lines.append("")
        lines.append(
            "  To allow a LEGITIMATE error-path core-mock, record it with a reason:"
        )
        lines.append(
            '    python -m tools.reality_contact.ratchet --accept '
            '--reason "<why this core-mock is correct>"'
        )
        lines.append("")
    if floor_breaches:
        lines.append(
            "  Subsystem theater-count FLOOR breached (current theater exceeds the"
        )
        lines.append("  frozen floor + recorded exemptions):")
        for b in floor_breaches:
            lines.append(
                f"    ! {b.subsystem}: current theater {b.current} > "
                f"floor {b.floor} + {b.exempted} exemption(s)"
            )
        lines.append("")
    lines.append("  The ratchet is one-way: it does not remove a mock or edit a")
    lines.append("  test — it refuses to let the number slide. Fix the test or record")
    lines.append("  the exemption with a written reason.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _load_ledger(ledger_path: Path) -> dict[str, Any] | None:
    if not ledger_path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(ledger_path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _resolve_ledger(ledger_path: Path | None) -> dict[str, Any] | None:
    """Source the ledger the verdict is computed against.

    Default (``ledger_path is None``) — REGENERATE in-memory from the LIVE tree
    via ``build_ledger()`` (no disk write). This is what makes the gate correct
    BY DEFAULT: a new core-mock test in the working tree is seen immediately. The
    committed ``ledger.json`` is a point-in-time snapshot that drifts as test
    files are added; trusting it would let a real theater regression slip past a
    local ``ratchet`` run that prints "PASS" against a stale picture — the one
    thing a one-way gate must never do.

    An explicit ``ledger_path`` overrides this for audit/replay against a frozen
    ledger, and is how the unit tests inject hand-built fixtures. Returns
    ``None`` when an explicit path is unreadable/unparseable (the caller maps
    that to a usage error)."""
    if ledger_path is None:
        return build_ledger()
    return _load_ledger(ledger_path)


def run_check(
    baseline_path: Path = BASELINE_PATH,
    ledger_path: Path | None = None,
) -> int:
    """Default mode: regenerate the ledger from the LIVE tree, compare to the
    committed baseline, print, return the exit code. Correct by default — it
    cannot be fooled by a stale committed ledger (see ``_resolve_ledger``)."""
    ledger = _resolve_ledger(ledger_path)
    if ledger is None:
        loc = _rel(ledger_path) if ledger_path is not None else "the live tree"
        print(
            f"reality-contact ratchet: ledger not found / unreadable at {loc}\n"
            f"  Regenerate it with:  python -m tools.reality_contact.ledger"
        )
        return EXIT_USAGE
    try:
        baseline = load_baseline(baseline_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"reality-contact ratchet: baseline unusable: {exc}")
        return EXIT_USAGE

    result = evaluate(ledger, baseline)
    print(result.report)
    return result.exit_code


def run_accept(
    reason: str | None,
    baseline_path: Path = BASELINE_PATH,
    ledger_path: Path | None = None,
) -> int:
    """``--accept --reason "..."``: append the current NEW un-exempted theater
    test(s) to the baseline's ``exemptions`` with the rationale + provenance.

    A bare ``--accept`` (no reason) is REJECTED — no baseline change. One-way: this
    path only APPENDS exemptions; it never lowers a per-subsystem floor. Like the
    check, it regenerates the ledger from the LIVE tree by default so the exempted
    set is exactly the tree's current un-recorded core-mocks (``_resolve_ledger``).
    """
    if reason is None or not reason.strip():
        print(
            "reality-contact ratchet: --accept requires --reason \"<why this "
            "core-mock is correct>\".\n"
            "  Refusing to record an exemption with no rationale — the gate is "
            "one-way but never silent."
        )
        return EXIT_USAGE

    ledger = _resolve_ledger(ledger_path)
    if ledger is None:
        loc = _rel(ledger_path) if ledger_path is not None else "the live tree"
        print(
            f"reality-contact ratchet: ledger not found / unreadable at {loc}\n"
            f"  Regenerate it with:  python -m tools.reality_contact.ledger"
        )
        return EXIT_USAGE
    try:
        baseline = load_baseline(baseline_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"reality-contact ratchet: baseline unusable: {exc}")
        return EXIT_USAGE

    result = evaluate(ledger, baseline)
    to_record = [h for h in result.new_theater]
    if not to_record:
        print(
            "reality-contact ratchet: nothing to exempt — there is no NEW "
            "un-recorded core-mock in the current ledger. No baseline change."
        )
        # Not an error; the tree is already clean. Exit OK.
        return EXIT_OK

    accepted_at = datetime.now(UTC).isoformat()
    prov = ledger_content_hash(ledger)
    existing = baseline.allowed_keys()
    added = 0
    for hit in to_record:
        if hit.key in existing:
            continue
        baseline.exemptions.append(
            Exemption(
                path=hit.key.path,
                subsystem=hit.key.subsystem,
                target=hit.key.target,
                reason=f"{reason.strip()} [ledger {prov}]",
                accepted_at=accepted_at,
            )
        )
        existing.add(hit.key)
        added += 1

    write_baseline(baseline, baseline_path)
    print(
        f"reality-contact ratchet: recorded {added} exemption(s) with reason "
        f"into {_rel(baseline_path)}.\n"
        f"  Each carries the rationale + ledger provenance {prov}.\n"
        f"  The ratchet now PASSES those specific core-mock(s); they can never "
        f"again be added silently."
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.reality_contact.ratchet",
        description=(
            "One-way reality-contact ratchet: fail CI on a new un-recorded "
            "core-mock or a real test hollowed to theater; pass improvements and "
            "recorded exemptions."
        ),
    )
    parser.add_argument(
        "--accept",
        action="store_true",
        help=(
            "Record the current NEW un-exempted core-mock(s) as exemptions. "
            "REQUIRES --reason."
        ),
    )
    parser.add_argument(
        "--reason",
        type=str,
        default=None,
        help="The written rationale for an --accept exemption. Mandatory with --accept.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.accept:
        return run_accept(args.reason)
    return run_check()


if __name__ == "__main__":
    raise SystemExit(main())
