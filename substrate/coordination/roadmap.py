"""Cross-spec roadmap — ingests the five sprint rosters + SPR-01's DAG (SPR-05 M2).

The five live specs hold **45 sprints**: DRW 10 + Read 9 + Write 9 + Speak 9 +
unified 8. The portfolio-shell spec's 6 sprints are *superseded* by this unified
spec's 8 (per the master spec's "supersedes the five-surface portfolio-shell
prototype" decision) — counted as superseded, not added.

This module reconciles that count from the **real roster files on disk** rather
than trusting any number written in prose (rigor #1 — "don't propagate a number
you didn't add up"). The roster source is the spec sprint filenames
(``specs/<spec>/sprint-NN-*.html``); the roadmap reads them, it does not author
them.

It then consumes SPR-01's :mod:`substrate.contracts.dependency_map` DAG for the
dependency edges, surfaces the DRW critical path (``drw:1 → drw:3 → drw:10``)
explicitly, and computes **what's unblocked now** from the dependency state —
derived, not hand-maintained: a sprint is unblocked when every cross-spec
dependency edge it has points at a node whose owning sprint is already ``live``/
``provisional`` (built), per the frozen DRW sprint-lock's status column.

The substrate-execution layer (db_lock hardening, dispatch idempotency, CRDT
scaffold, multi-cloud, vector reconstruction, structural-integrity lints) is
ingested too, from the unified master spec's tech-stack ledger, so "what's the
real foundation" is visible beside the product sprints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from substrate.contracts import dependency_map, drw_sprint_lock

# ── Where the rosters live ───────────────────────────────────────────────────
#
# The spec rosters are UNTRACKED in the Antiek repo (they're documentation
# inputs at ~/Desktop/Antiek/specs/). The roadmap reads them from there. Each
# entry: (spec key used in the DAG, directory name under specs/, display label).

_SPEC_DIRS: tuple[tuple[str, str, str], ...] = (
    ("drw", "deep-research-workspace", "Research (DRW)"),
    ("read", "read", "Read"),
    ("write", "write", "Write"),
    ("speak", "speak", "Speak"),
    ("unified", "antiek-unified", "Antiek-Unified"),
)

# The superseded prototype — counted as superseded, never added to the 45.
_SUPERSEDED_DIR = "shell"


def _specs_root() -> Path:
    """The specs directory. Resolved relative to the home dir so it works from
    any worktree (the rosters live in the main tree's specs/, untracked).

    Honesty: if the env var ``ANTIEK_SPECS_ROOT`` is set we honor it (lets the
    no-fork/roster tests point at a fixture); otherwise the canonical
    ``~/Desktop/Antiek/specs``."""
    import os
    env = os.environ.get("ANTIEK_SPECS_ROOT")
    if env:
        return Path(env)
    return Path.home() / "Desktop" / "Antiek" / "specs"


_SPRINT_FILE_RE = re.compile(r"^sprint-(\d{2})-(.+)\.html$")


class SprintStatus(str, Enum):
    """Coarse build state of a sprint, derived from the DRW sprint-lock where
    the sprint is a DRW sprint, else ``UNKNOWN`` (the products own their own
    internal status; this roadmap does not invent one)."""

    LIVE = "live"
    PROVISIONAL = "provisional"
    PLANNED = "planned"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SprintRow:
    """One sprint in the roadmap. ``node_id`` is the DAG node id
    (``"<spec>:<n>"``); ``on_critical_path`` flags the DRW spine
    (drw:1/3/10); ``unblocked`` is derived from dependency state."""

    spec: str            # "drw" | "read" | "write" | "speak" | "unified"
    spec_label: str
    sprint: int
    slug: str
    node_id: str
    status: SprintStatus
    on_critical_path: bool
    blocked_on: tuple[str, ...]   # node ids this sprint waits on (not yet built)
    unblocked: bool               # derived: all cross-spec deps built


@dataclass(frozen=True)
class SpecRoster:
    """A single spec's roster of sprints, read from its filenames."""

    spec: str
    label: str
    directory: str
    sprints: tuple[SprintRow, ...]

    @property
    def count(self) -> int:
        return len(self.sprints)


@dataclass(frozen=True)
class SubstrateLayer:
    """One row of the substrate-execution layer (from the tech-stack ledger)."""

    name: str
    owner: str
    status: str  # verbatim ledger status, e.g. "Hardened (substrate-execution SPR-01)"


@dataclass(frozen=True)
class Roadmap:
    """The reconciled cross-spec roadmap. A VIEW — derived on read from the
    roster files + SPR-01's DAG; it authors nothing."""

    rosters: tuple[SpecRoster, ...]
    critical_path: tuple[str, ...]
    superseded_count: int
    superseded_note: str
    substrate_layers: tuple[SubstrateLayer, ...] = ()

    @property
    def total_sprints(self) -> int:
        return sum(r.count for r in self.rosters)

    def all_sprints(self) -> tuple[SprintRow, ...]:
        out: list[SprintRow] = []
        for r in self.rosters:
            out.extend(r.sprints)
        return tuple(out)

    def unblocked_now(self) -> tuple[SprintRow, ...]:
        return tuple(s for s in self.all_sprints() if s.unblocked)

    def blocked(self) -> tuple[SprintRow, ...]:
        return tuple(s for s in self.all_sprints() if not s.unblocked)

    def critical_path_rows(self) -> tuple[SprintRow, ...]:
        by_id = {s.node_id: s for s in self.all_sprints()}
        return tuple(by_id[n] for n in self.critical_path if n in by_id)

    def count_reconciliation(self) -> str:
        """The reconciled-out-loud count string (rigor #1)."""
        parts = " + ".join(f"{r.label.split(' ')[0]} {r.count}" for r in self.rosters)
        return (
            f"{parts} = {self.total_sprints}; "
            f"shell's {self.superseded_count} superseded ({self.superseded_note})"
        )


# ── Reading the rosters ──────────────────────────────────────────────────────

def _read_roster_files(spec_dir: Path) -> list[tuple[int, str]]:
    """Return [(sprint_number, slug)] for a spec dir, read from its
    ``sprint-NN-<slug>.html`` filenames. Sorted by number."""
    found: list[tuple[int, str]] = []
    sprint_numbers: set[int] = set()
    if not spec_dir.is_dir():
        return found
    for p in spec_dir.iterdir():
        m = _SPRINT_FILE_RE.match(p.name)
        if m:
            sprint = int(m.group(1))
            if sprint in sprint_numbers:
                raise ValueError(
                    f"duplicate sprint identity {sprint:02d} in {spec_dir}"
                )
            sprint_numbers.add(sprint)
            found.append((sprint, m.group(2)))
    found.sort(key=lambda t: t[0])
    return found


def _manifest_rosters() -> dict[str, list[tuple[int, str]]]:
    """Committed fallback roster (``sprint_rosters.json``, generated from the
    specs). Used when the live ``specs/`` dirs are not on disk — i.e. on CI and
    on prod, where the untracked planning specs are absent. The live filesystem
    (the operator's ``~/Desktop/Antiek/specs``) takes precedence when present so
    the operator always sees current state; this manifest keeps the roadmap
    portable and the coordination dashboard non-empty everywhere else. Regenerate
    it when the rosters change."""
    import json

    path = Path(__file__).with_name("sprint_rosters.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        key: [(int(n), str(slug)) for n, slug in rows]
        for key, rows in data.get("rosters", {}).items()
    }


def _drw_status(sprint: int) -> SprintStatus:
    """DRW sprint status from the frozen sprint-lock (single source — we don't
    re-derive it)."""
    try:
        d = drw_sprint_lock.resolve_drw_sprint(sprint)
    except KeyError:
        return SprintStatus.UNKNOWN
    return {
        "live": SprintStatus.LIVE,
        "provisional": SprintStatus.PROVISIONAL,
        "planned": SprintStatus.PLANNED,
    }.get(d.status, SprintStatus.UNKNOWN)


def _built(status: SprintStatus) -> bool:
    """A node counts as 'built' (can unblock consumers) when its owning sprint is
    live or provisional. Planned/unknown does not unblock."""
    return status in (SprintStatus.LIVE, SprintStatus.PROVISIONAL)


def _node_status(node_id: str) -> SprintStatus:
    """Status of an arbitrary DAG node. DRW nodes resolve via the sprint-lock;
    whole-spec nodes (no ':') and non-DRW sprint nodes are UNKNOWN (the products
    own their internal status — we do not fabricate one)."""
    if node_id.startswith("drw:"):
        try:
            return _drw_status(int(node_id.split(":")[1]))
        except (ValueError, IndexError):
            return SprintStatus.UNKNOWN
    return SprintStatus.UNKNOWN


def _dependencies_for(node_id: str) -> tuple[str, ...]:
    """Providers a node depends on, from SPR-01's DAG (consumer → provider).
    Also matches the whole-spec node (e.g. ``read``) since the product DAG edges
    use spec-level consumers."""
    spec = node_id.split(":")[0]
    deps: set[str] = set()
    for e in dependency_map.EDGES:
        if e.consumer == node_id or e.consumer == spec:
            deps.add(e.provider)
    return tuple(sorted(deps))


def build_roadmap(specs_root: Path | None = None) -> Roadmap:
    """Ingest the five rosters + SPR-01's DAG; reconcile the count; compute the
    unblocked set from dependency state. Reads only — authors nothing."""
    explicit_root = specs_root is not None
    root = specs_root or _specs_root()
    crit = set(dependency_map.critical_path())

    rosters: list[SpecRoster] = []
    # A live per-spec directory takes precedence over the committed manifest.
    # The operator's broader specs root may legitimately exist while containing
    # none of these five historical rosters; in that case each absent canonical
    # roster falls back independently instead of collapsing the atlas to zero.
    # An explicitly supplied root is different: it is an exact fixture/view, so
    # absent directories honestly contribute zero and are never backfilled.
    root_present = root.is_dir()
    manifest = {} if explicit_root else _manifest_rosters()
    for spec, dirname, label in _SPEC_DIRS:
        spec_dir = root / dirname
        files = (
            _read_roster_files(spec_dir)
            if root_present and spec_dir.is_dir()
            else manifest.get(spec, [])
        )
        rows: list[SprintRow] = []
        for sprint, slug in files:
            node_id = f"{spec}:{sprint}"
            status = _drw_status(sprint) if spec == "drw" else SprintStatus.UNKNOWN
            deps = _dependencies_for(node_id)
            # Cross-spec deps not yet built block this sprint. Self-spec /
            # unknown-status providers are ignored for the unblocked calc — we
            # only assert against the load-bearing DRW spine whose status we know.
            blocked_on = tuple(
                d for d in deps
                if d.startswith("drw:") and not _built(_node_status(d))
            )
            rows.append(
                SprintRow(
                    spec=spec,
                    spec_label=label,
                    sprint=sprint,
                    slug=slug,
                    node_id=node_id,
                    status=status,
                    on_critical_path=node_id in crit,
                    blocked_on=blocked_on,
                    unblocked=(len(blocked_on) == 0),
                )
            )
        rosters.append(
            SpecRoster(spec=spec, label=label, directory=dirname, sprints=tuple(rows))
        )

    superseded_dir = root / _SUPERSEDED_DIR
    superseded_files = (
        _read_roster_files(superseded_dir)
        if root_present and superseded_dir.is_dir()
        else manifest.get(_SUPERSEDED_DIR, [])
    )

    return Roadmap(
        rosters=tuple(rosters),
        critical_path=tuple(dependency_map.critical_path()),
        superseded_count=len(superseded_files),
        superseded_note="five-surface portfolio-shell prototype, superseded by unified's 8",
        substrate_layers=_SUBSTRATE_LAYERS,
    )


# ── Substrate-execution layer (from the unified master spec's tech-stack ledger)
#
# The infrastructure layer beneath the four workflows. Verbatim owner + status
# from the unified spec's "full tech-stack ledger" table — the rows tagged
# "substrate-execution SPR-NN". Pinned here (the ledger is HTML, not parsed at
# runtime); the source of truth for these statuses is the master spec table.

_SUBSTRATE_LAYERS: tuple[SubstrateLayer, ...] = (
    SubstrateLayer("Write coordination (db_lock)", "runtime/db_lock.py", "Hardened (substrate-execution SPR-01)"),
    SubstrateLayer("Dispatch router + idempotency", "substrate/dispatch/", "Hardened (substrate-execution SPR-02/03)"),
    SubstrateLayer("Multi-cloud failover", "substrate/dispatch/multi_cloud.py", "Landed off-by-default (substrate-execution SPR-10)"),
    SubstrateLayer("Vector / embeddings reconstruction", "scripts/reconstruct_vector_index.py", "Live (DuckDB-native); turbopuffer gated (substrate-execution SPR-06)"),
    SubstrateLayer("Multi-user / CRDT scaffold", "substrate/multi_user/crdt_scaffold/", "Scaffolded off (substrate-execution SPR-09)"),
    SubstrateLayer("Structural-integrity lints", "tools/lint/", "Landed (substrate-execution SPR-03/05/08)"),
)
