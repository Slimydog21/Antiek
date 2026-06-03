"""Budget governor — measure the box's real ceiling, then PACE or HALT (SPR-09 M5).

This module is HOW "§16 box-bounded" is enforced as code rather than hope. The
continuous engine (``tools/run_corpus_ingest.py --continuous``) consults this
governor before each scheduling round and before each merge. The governor reads
the live box state — NVMe free space, the live ``antiek.duckdb`` size, and the
ingest process's resident memory — and returns one of three states:

    OK    — below the soft threshold: run normally.
    PACE  — between soft and hard: slow down (smaller batch, longer interval)
            so headroom is preserved without stopping.
    HALT  — at/over the hard ceiling: stop scheduling new work, let any
            in-flight merge finish (or refuse to start one), and persist the
            checkpoint cleanly. The box is never endangered; the live API never
            starves for disk.

----------------------------------------------------------------------------
THE MEASURED CEILING — derivation, reported honestly (rigor card #1)
----------------------------------------------------------------------------

The box is a Hetzner CCX23: 4 vCPU / 16 GB RAM / ~160 GB NVMe (the
``docs/operator_gate_actions.md`` + sprint-spec parent context). The ceiling is
expressed as a MINIMUM-FREE-DISK headroom (not a max-DB-size), because the thing
that actually endangers the box is the NVMe filling while the live API needs to
write its WAL / event log / temp spill — DuckDB and uvicorn both fail badly at
0 bytes free, and a full disk is what a runaway continuous ingest would cause.

Honest-extrapolation disclosure: the operator could only characterize
DB-size-per-1k-docs on the SMALL first prod batch (2026-05-29 was hand-fed,
tens of docs). So the per-doc growth figure below is an EXTRAPOLATION from a
small sample, not a measured steady-state, and the governor is deliberately
conservative about it. The defense is the disk-headroom floor, which is a
direct reading of a real number (``shutil.disk_usage``) and does not depend on
the extrapolation at all — the DB-size and per-doc figures only TIGHTEN the
estimate, they never loosen the disk floor.

Default ceiling values + their derivation:

  * ``hard_min_free_disk_bytes = 8 GiB``. At 0 free the box dies; we stop well
    before. 8 GiB leaves comfortable room for DuckDB checkpoint/WAL, the event
    log JSONL, OS temp, and a backup snapshot the operator may take before a
    merge — none of which the ingest should be allowed to crowd out.
  * ``soft_min_free_disk_bytes = 16 GiB``. ~10% of a 160 GB NVMe. Between 16
    and 8 GiB free we PACE so the approach to the hard floor is gradual and
    observable in the event log, not a cliff.
  * ``hard_db_size_bytes = 100 GiB`` / ``soft_db_size_bytes = 80 GiB``. A
    secondary guard: even on a hypothetically larger disk, a single-file DuckDB
    that large is operationally unwise on a 16 GB-RAM box (checkpoint + index
    rebuild memory). These are intentionally generous (the disk floor bites
    first on the real box); they exist so the ceiling is also expressed against
    the DB artifact, per the spec's "antiek.duckdb size" requirement.
  * ``hard_rss_bytes = 12 GiB`` / ``soft_rss_bytes = 9 GiB``. Of 16 GB total,
    leave ~4 GiB for the OS + the live ``antiek.service`` worker + the
    embedding index. The ingest process (download/extract/chunk/embed into
    staging) must not be the thing that OOM-kills the live API. RSS is the
    process+children resident size; on the box the embedding index is the
    dominant term, so this is the memory-vs-ceiling check the spec names.

Per-doc growth extrapolation (used only to TIGHTEN, never to loosen):
  ``EST_BYTES_PER_DOC = 250_000`` (~250 KB/doc: a chunked+embedded book/paper
  with 16-dim..1k-dim vectors and markdown body — extrapolated from the small
  first-batch sample; flagged as such). ``project_*`` helpers use it to answer
  "would ingesting N more docs cross the hard floor?" so a round that WOULD
  cross halts BEFORE it starts, rather than discovering it after the write.

All thresholds are constructor arguments with the derivation above; a test
seeds fake readings (no real disk/DB/RSS dependency) to exercise OK/PACE/HALT.
Time/readings are injectable so CI is deterministic and never touches the real
box. This module reaches NO network, opens NO DuckDB write lock, and starts NO
second runtime (§16): it is pure measurement + comparison.
"""

from __future__ import annotations

import enum
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Empirical ceiling defaults (see the module docstring for the full derivation).
# ---------------------------------------------------------------------------

_GIB = 1024 ** 3

# Disk headroom — the PRIMARY guard, a direct reading independent of any
# extrapolation. Stop well before the NVMe fills under the live API.
DEFAULT_HARD_MIN_FREE_DISK_BYTES = 8 * _GIB
DEFAULT_SOFT_MIN_FREE_DISK_BYTES = 16 * _GIB

# DuckDB single-file artifact size — a secondary guard (generous; the disk
# floor bites first on the real 160 GB box).
DEFAULT_HARD_DB_SIZE_BYTES = 100 * _GIB
DEFAULT_SOFT_DB_SIZE_BYTES = 80 * _GIB

# Ingest-process resident memory — leave headroom for the OS + live API + the
# embedding index on the 16 GB box.
DEFAULT_HARD_RSS_BYTES = 12 * _GIB
DEFAULT_SOFT_RSS_BYTES = 9 * _GIB

# Per-doc growth EXTRAPOLATION from the small first-batch sample (flagged in the
# docstring). Used only to forecast whether N more docs would cross the hard
# disk floor — it can tighten the answer (halt earlier) but never loosen it.
EST_BYTES_PER_DOC = 250_000


class BudgetState(str, enum.Enum):
    """The governor verdict. ``str``-valued so it serializes straight into the
    event-log payload + the status snapshot."""

    OK = "OK"
    PACE = "PACE"
    HALT = "HALT"


@dataclass(frozen=True)
class BudgetReading:
    """A point-in-time reading of the box, taken by :func:`read_box` (or seeded
    by a test). All bytes; -1 means "could not read this dimension" (the
    governor treats an unreadable dimension as unconstrained for THAT dimension
    only — it never fabricates a passing or failing number)."""

    free_disk_bytes: int
    db_size_bytes: int
    rss_bytes: int


@dataclass(frozen=True)
class BudgetVerdict:
    """The governor's decision + the honest reason it reached it. ``state`` is
    the worst (most-restrictive) dimension; ``reasons`` names every dimension
    that contributed so the event log / status is auditable rather than a bare
    'HALT'."""

    state: BudgetState
    reading: BudgetReading
    reasons: tuple[str, ...]

    @property
    def should_schedule(self) -> bool:
        """True iff the engine may schedule new work this round."""
        return self.state is not BudgetState.HALT

    def render(self) -> str:
        return f"{self.state.value}: " + ("; ".join(self.reasons) or "all dimensions OK")


def _read_free_disk_bytes(path: str) -> int:
    """Free bytes on the filesystem holding ``path`` (its parent dir if the
    file does not exist yet). -1 if it cannot be read."""
    probe = path
    if not os.path.exists(probe):
        probe = os.path.dirname(os.path.abspath(probe)) or "."
    try:
        return int(shutil.disk_usage(probe).free)
    except (OSError, ValueError):
        return -1


def _read_db_size_bytes(db_path: str) -> int:
    """Size of the live DuckDB file in bytes, 0 if it does not exist yet, -1 on
    error. Read-only ``os.stat`` — never opens the DB, never takes the write
    lock (the §16 / read-only-where-required constraint)."""
    try:
        return int(os.path.getsize(db_path))
    except FileNotFoundError:
        return 0
    except OSError:
        return -1


def _read_rss_bytes() -> int:
    """Resident memory of THIS process + its children, in bytes; -1 if it
    cannot be read.

    ``psutil`` is not installed on the box, so we use ``resource.getrusage``
    (SELF + CHILDREN), whose ``ru_maxrss`` is the peak RSS — on Linux in KiB,
    on macOS in bytes. This is a conservative reading (peak, not current),
    which is the safe direction for a ceiling guard: it only ever over-reports,
    so the governor errs toward PACE/HALT, never toward running past the real
    ceiling."""
    try:
        import resource
        import sys

        usage_self = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        try:
            usage_children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except (ValueError, OSError):
            usage_children = 0
        maxrss = int(usage_self) + int(usage_children)
        # Linux reports ru_maxrss in KiB; macOS in bytes.
        if sys.platform == "darwin":
            return maxrss
        return maxrss * 1024
    except Exception:
        return -1


def read_box(db_path: str, *, staging_dir: str | None = None) -> BudgetReading:
    """Read the live box state for the governor.

    ``db_path`` is the LIVE DuckDB whose size + filesystem free space we read.
    ``staging_dir`` (when given) is where staged work lands; if it is on a
    DIFFERENT filesystem than the live DB, free disk is read for the staging
    filesystem too and the SMALLER of the two is reported — the round is bounded
    by whichever filesystem is tightest. Read-only throughout."""
    free_live = _read_free_disk_bytes(db_path)
    free = free_live
    if staging_dir:
        free_staging = _read_free_disk_bytes(staging_dir)
        if free_staging >= 0 and (free < 0 or free_staging < free):
            free = free_staging
    return BudgetReading(
        free_disk_bytes=free,
        db_size_bytes=_read_db_size_bytes(db_path),
        rss_bytes=_read_rss_bytes(),
    )


class BudgetGovernor:
    """Compares a :class:`BudgetReading` against the empirical ceiling and
    returns OK / PACE / HALT. The reader is injectable so a test seeds a
    near-ceiling reading with no real disk/DB/RSS dependency, and so the live
    engine passes a real ``read_box`` closure.
    """

    def __init__(
        self,
        *,
        db_path: str = "",
        staging_dir: str | None = None,
        hard_min_free_disk_bytes: int = DEFAULT_HARD_MIN_FREE_DISK_BYTES,
        soft_min_free_disk_bytes: int = DEFAULT_SOFT_MIN_FREE_DISK_BYTES,
        hard_db_size_bytes: int = DEFAULT_HARD_DB_SIZE_BYTES,
        soft_db_size_bytes: int = DEFAULT_SOFT_DB_SIZE_BYTES,
        hard_rss_bytes: int = DEFAULT_HARD_RSS_BYTES,
        soft_rss_bytes: int = DEFAULT_SOFT_RSS_BYTES,
        est_bytes_per_doc: int = EST_BYTES_PER_DOC,
        reader: Callable[[], BudgetReading] | None = None,
    ) -> None:
        self._db_path = db_path
        self._staging_dir = staging_dir
        self.hard_min_free_disk_bytes = int(hard_min_free_disk_bytes)
        self.soft_min_free_disk_bytes = int(soft_min_free_disk_bytes)
        self.hard_db_size_bytes = int(hard_db_size_bytes)
        self.soft_db_size_bytes = int(soft_db_size_bytes)
        self.hard_rss_bytes = int(hard_rss_bytes)
        self.soft_rss_bytes = int(soft_rss_bytes)
        self.est_bytes_per_doc = int(est_bytes_per_doc)
        # The reader is the seam tests fake. Default reads the real box.
        self._reader = reader or (
            lambda: read_box(self._db_path, staging_dir=self._staging_dir)
        )

    # -- the check -----------------------------------------------------------

    def check(self, reading: BudgetReading | None = None) -> BudgetVerdict:
        """Return the governor verdict. Each dimension votes independently; the
        verdict is the MOST RESTRICTIVE vote (HALT > PACE > OK) so any single
        endangered dimension halts the run, and every contributing dimension is
        named in ``reasons`` (honest reporting — a HALT says WHY)."""
        r = reading if reading is not None else self._reader()
        votes: list[tuple[BudgetState, str]] = []

        # Disk free — the primary guard. LOWER free is worse, so the HARD floor
        # is the SMALLER number.
        if r.free_disk_bytes >= 0:
            if r.free_disk_bytes <= self.hard_min_free_disk_bytes:
                votes.append((BudgetState.HALT, (
                    f"free disk {_h(r.free_disk_bytes)} <= hard floor "
                    f"{_h(self.hard_min_free_disk_bytes)}"
                )))
            elif r.free_disk_bytes <= self.soft_min_free_disk_bytes:
                votes.append((BudgetState.PACE, (
                    f"free disk {_h(r.free_disk_bytes)} <= soft floor "
                    f"{_h(self.soft_min_free_disk_bytes)}"
                )))

        # DB artifact size — secondary guard. HIGHER is worse.
        if r.db_size_bytes >= 0:
            if r.db_size_bytes >= self.hard_db_size_bytes:
                votes.append((BudgetState.HALT, (
                    f"antiek.duckdb {_h(r.db_size_bytes)} >= hard ceiling "
                    f"{_h(self.hard_db_size_bytes)}"
                )))
            elif r.db_size_bytes >= self.soft_db_size_bytes:
                votes.append((BudgetState.PACE, (
                    f"antiek.duckdb {_h(r.db_size_bytes)} >= soft ceiling "
                    f"{_h(self.soft_db_size_bytes)}"
                )))

        # Process/embedding-index RSS — HIGHER is worse.
        if r.rss_bytes >= 0:
            if r.rss_bytes >= self.hard_rss_bytes:
                votes.append((BudgetState.HALT, (
                    f"ingest RSS {_h(r.rss_bytes)} >= hard ceiling "
                    f"{_h(self.hard_rss_bytes)}"
                )))
            elif r.rss_bytes >= self.soft_rss_bytes:
                votes.append((BudgetState.PACE, (
                    f"ingest RSS {_h(r.rss_bytes)} >= soft ceiling "
                    f"{_h(self.soft_rss_bytes)}"
                )))

        state = BudgetState.OK
        if any(v[0] is BudgetState.HALT for v in votes):
            state = BudgetState.HALT
        elif any(v[0] is BudgetState.PACE for v in votes):
            state = BudgetState.PACE
        return BudgetVerdict(
            state=state, reading=r, reasons=tuple(reason for _, reason in votes)
        )

    def would_cross_hard_floor(
        self, n_docs: int, reading: BudgetReading | None = None
    ) -> bool:
        """Forecast whether ingesting ``n_docs`` more would push free disk at or
        below the hard floor, using the EST_BYTES_PER_DOC extrapolation. Used to
        refuse a round that would cross the floor BEFORE it writes (rigor: HALT
        never starts an endangering merge). The extrapolation only tightens —
        a forecast crossing halts early; it never permits running past the
        already-measured floor (which :func:`check` enforces independently)."""
        r = reading if reading is not None else self._reader()
        if r.free_disk_bytes < 0:
            return False  # cannot read disk -> do not forecast a cross
        projected_free = r.free_disk_bytes - max(0, n_docs) * self.est_bytes_per_doc
        return projected_free <= self.hard_min_free_disk_bytes


def _h(n: int) -> str:
    """Human-readable bytes for log lines / reasons. Pure formatting."""
    if n < 0:
        return "unknown"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    val = float(n)
    for u in units:
        if val < 1024 or u == units[-1]:
            return f"{val:.1f}{u}" if u != "B" else f"{int(val)}B"
        val /= 1024
    return f"{n}B"
