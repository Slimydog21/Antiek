"""Gate ledger — a typed VIEW over ``docs/operator_gate_actions.md`` (SPR-05 M1).

The binding gates (G1+) that block Antiek's activation are canonical in one
human-edited markdown file. Four product specs each re-describe the same gates
from their own angle — Read frames G2/G3 as "disbursement blocked," Speak as
"public publishing blocked," Write as "G8 blocks RL." Multiple descriptions of
the same gates drift. This module presents them **once**, parsed from the single
source, and pairs each gate with a per-product impact column.

The load-bearing invariant: **the ledger is derived on read; it never stores a
second copy of gate state and has no write path back to the markdown.** If the
operator edits a gate's status in the source file, the next ``load_gate_ledger``
reflects it. The :mod:`tests.test_coordination_no_fork` test parses the source
by an *independent* path (a regex over the quick-status table) and asserts the
two agree — catching any drift between the ledger and the human-edited file.

What is parsed (and the nuance it preserves):

* Each ``## GN — <title>`` section header → the gate id + title.
* The ``**Status:**`` line inside the section → the raw status string, kept
  verbatim ("✅ CLOSED 2026-05-23 (provisionally, with re-open trigger)") and
  normalized to a coarse :class:`GateStatus` enum. The verbatim string is the
  source of truth for nuance; the enum is for filtering/coloring only.
* The ``**Owner:**`` / ``**Blocks:**`` lines, when present.
* The ``**Closure record:**`` line (a repository-relative evidence path), when
  present.

What is NOT parsed from the doc, and why it lives here instead: the
**per-product impact map**. The source doc says what each gate blocks in product-
neutral terms ("All Stripe payouts; all external email"); mapping that to which
of Research/Read/Write/Speak it blocks is a cross-spec join the source file does
not encode. We pin it as a small reviewed constant, grounded in the product
specs' own gate references (see ``_IMPACT`` docstring), not invented at parse
time. This is the one place gate↔product data lives — it is impact metadata, not
a second copy of gate *state* (status still comes only from the markdown).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# ── The canonical source ────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Repository root, located relative to this file (``substrate/coordination``
    is two levels below the root)."""
    return Path(__file__).resolve().parents[2]


def canonical_gate_path() -> Path:
    """The one canonical gate file. Never written by this package."""
    return _repo_root() / "docs" / "operator_gate_actions.md"


# ── Coarse status enum (for filtering/coloring only; nuance lives in raw) ────

class GateStatus(str, Enum):
    """A coarse normalization of the gate's status for filtering and coloring.

    The *authoritative* status is :attr:`Gate.status_raw` (verbatim from the
    source). This enum flattens it to one of four buckets so the UI can color a
    row without re-parsing nuance — but a "provisionally closed with re-open
    trigger" gate is still ``CLOSED`` here and carries its full nuance in
    ``status_raw`` + ``status_note``. We never throw away the nuance; we add a
    coarse handle beside it."""

    CLOSED = "closed"
    OPEN = "open"
    CALENDAR = "calendar"      # open, but earliest closure is a future date
    DATA_BOUND = "data_bound"  # open, gated on accumulated data/criteria

    @property
    def is_open_family(self) -> bool:
        """OPEN, CALENDAR and DATA_BOUND are all 'not closed' — the open family.
        The CALENDAR/DATA_BOUND members are *finer-grained* open states the
        source doc's quick-status table distinguishes (⏳ + the word
        'calendar'/'data-bound'); the per-section header sometimes collapses
        them to a plain ❌ OPEN with a parenthetical date/criteria hint. The
        load-bearing equality is closed-vs-open; the bucket is reporting
        nuance."""
        return self is not GateStatus.CLOSED


class Product(str, Enum):
    """The four product workflows the unified vision ships."""

    RESEARCH = "research"
    READ = "read"
    WRITE = "write"
    SPEAK = "speak"


@dataclass(frozen=True)
class GateImpact:
    """How a gate blocks one product. ``product`` is which workflow; ``effect``
    is the one-line, product-specific consequence (grounded in that product
    spec's own gate reference, not invented)."""

    product: Product
    effect: str


@dataclass(frozen=True)
class Gate:
    """One binding gate, derived on read from the canonical markdown.

    ``status_raw`` is verbatim from the source ``**Status:**`` line and is the
    authoritative nuance carrier. ``status`` is the coarse enum. ``impacts`` is
    the per-product impact metadata (not gate state — see module docstring)."""

    gate_id: str          # "G1".."G13" (and future gates)
    title: str            # the section header title
    status: GateStatus    # coarse bucket
    status_raw: str       # verbatim status string (the nuance)
    owner: str | None     # from the **Owner:** line, if present
    blocks: str | None    # from the **Blocks:** / quick-status, if present
    closure_record: str | None  # repository-relative evidence path, if present
    impacts: tuple[GateImpact, ...] = ()

    @property
    def is_closed(self) -> bool:
        return self.status is GateStatus.CLOSED

    @property
    def is_provisional(self) -> bool:
        """True when the raw status flags a provisional / re-openable closure."""
        return "provision" in self.status_raw.lower()

    def blocks_products(self) -> tuple[Product, ...]:
        return tuple(i.product for i in self.impacts)


@dataclass(frozen=True)
class GateLedger:
    """The full set of gates, derived on read. A VIEW — never persisted."""

    gates: tuple[Gate, ...]
    source_path: str

    def by_id(self, gate_id: str) -> Gate:
        for g in self.gates:
            if g.gate_id == gate_id:
                return g
        raise KeyError(f"{gate_id} not in ledger (have: {[g.gate_id for g in self.gates]})")

    def gate_ids(self) -> tuple[str, ...]:
        return tuple(g.gate_id for g in self.gates)

    def open_gates(self) -> tuple[Gate, ...]:
        return tuple(g for g in self.gates if not g.is_closed)

    def closed_gates(self) -> tuple[Gate, ...]:
        return tuple(g for g in self.gates if g.is_closed)

    def gates_blocking(self, product: Product) -> tuple[Gate, ...]:
        """Open gates that block the given product (closed gates block nothing)."""
        return tuple(
            g for g in self.gates
            if not g.is_closed and product in g.blocks_products()
        )


# ── Per-product impact map (impact metadata, grounded in the product specs) ──
#
# This is the cross-spec join the source file does not encode. Each entry maps a
# gate to which of the four products it blocks and the product-specific effect.
# Grounded in the product specs' own gate references (verified — see
# tests/test_coordination_no_fork.py::test_impact_map_grounded):
#
#   • G2 (lawyer review) + G3 (publisher opt-in) → disbursement. Read SPR-09
#     (ad-revenue-escrow) and Speak SPR-06/07 (contributor economics / matrix)
#     both gate payout on G2+G3; Read & Speak are the two products that route
#     money. Research & Write accrue no external disbursement, so are not blocked.
#   • G7 (six-month compounding demo) → multi-user pivot (Sprint 22). The
#     single-operator invariant binds ALL four products until G7 closes; the
#     multi-user/public-ecosystem flip is cross-workflow.
#   • G8 (Loop 3 unlock) → RL training. Write (edit-trajectory → SFT) and Speak
#     (interviewer RL) are the two products with a training track gated on G8.
#   • G1 (retrieval-time gating, CLOSED) historically gated what Read/Research
#     serve full-text; recorded for completeness, blocks nothing now.
#   • G4 (Lemon UI) + G5 (dispatch tier) are infrastructure verdicts, CLOSED,
#     no per-product block.
#   • G6 (autoresearch Wedge 1) gates Phase-8 enforcing + autoresearch Wedges
#     2-4, which live in the Research workflow.
#   • G9 (arXiv researcher-payout counsel/KYC) → blocks the money-moving wave
#     of the arXiv-ingest track (SPR-07 researcher identity + SPR-08 KYC payout).
#     Research is the workflow that owns arXiv ingestion; the payout track is
#     part of the Research→Read pipeline but the gating is on Research's side.
#   • G10 (Stripe Press §9.10 opt-in) → blocks serving ANY in-copyright Stripe
#     Press title. Read is the servable-path workflow (titles must reach
#     content_class servable to appear in Read).
#   • G11 (X no-training constraint) → blocks training/RL export of BYOK X
#     content. Write (edit-trajectory SFT) and Speak (interviewer RL) are the
#     two products with training tracks that must honour the constraint.
#     Status: enforced in code + standing operator duty.
#   • G12 (Bernays per-title renewal) → blocks making additional 1927–1930
#     Bernays titles servable. Read is the servable-path workflow.
#   • G13 (Auth diagnostic matrix, CLOSED) → infra only; no per-product block.
#
# This is impact metadata only — gate STATUS comes solely from the markdown.

_IMPACT: dict[str, tuple[GateImpact, ...]] = {
    "G1": (
        GateImpact(Product.RESEARCH, "Retrieval-time legal gating on served chunks (closed — no longer blocking)"),
        GateImpact(Product.READ, "Full-text serving passes the gate (closed — no longer blocking)"),
    ),
    "G2": (
        GateImpact(Product.READ, "Ad-revenue disbursement (Read SPR-09 escrow) blocked until counsel clears the notification template"),
        GateImpact(Product.SPEAK, "Contributor disbursement (Speak SPR-06/07 economics) blocked — public publication also gated"),
    ),
    "G3": (
        GateImpact(Product.READ, "No payout until ≥1 publisher opts in (Read SPR-09 escrow stays accrual-only)"),
        GateImpact(Product.SPEAK, "Contributor payouts blocked — informant→payee map produces $0 disbursable"),
    ),
    "G4": (),  # Lemon UI verdict — infra, closed, no per-product block.
    "G5": (),  # Dispatch tier verdict — infra, closed (provisional), no per-product block.
    "G6": (
        GateImpact(Product.RESEARCH, "Phase-8 enforcing mode + autoresearch Wedges 2-4 stay shadow until the Lutke-gap verdict ratifies"),
    ),
    "G7": (
        GateImpact(Product.RESEARCH, "Multi-user pivot (Sprint 22) blocked — single-operator until the compounding curve is demonstrated"),
        GateImpact(Product.READ, "Public/multi-user reading ecosystem blocked until G7 closes"),
        GateImpact(Product.WRITE, "Multi-user authoring blocked until G7 closes"),
        GateImpact(Product.SPEAK, "Public interview ecosystem (multi-user) blocked until G7 closes"),
    ),
    "G8": (
        GateImpact(Product.WRITE, "Edit-trajectory SFT / RL training blocked until the five Loop-3 criteria pass"),
        GateImpact(Product.SPEAK, "Interviewer RL training blocked until the five Loop-3 criteria pass"),
    ),
    "G9": (
        GateImpact(Product.RESEARCH, "arXiv SPR-07 (researcher identity + ORCID opt-in) and SPR-08 (KYC + Stripe Connect payout) blocked at the caffenagent run edge"),
    ),
    "G10": (
        GateImpact(Product.READ, "No in-copyright Stripe Press title is servable until a §9.10 publisher opt-in is granted and claimed"),
    ),
    "G11": (
        GateImpact(Product.WRITE, "Edit-trajectory SFT must exclude BYOK X content — X dev terms forbid training on X data"),
        GateImpact(Product.SPEAK, "Interviewer RL training must exclude BYOK X content — X dev terms forbid training on X data"),
    ),
    "G12": (
        GateImpact(Product.READ, "No additional 1927–1930 Bernays title is servable without a per-title US copyright-renewal-records check"),
    ),
    "G13": (),  # Auth diagnostic matrix — infra, closed, no per-product block.
}


# ── The parser ──────────────────────────────────────────────────────────────

# A gate section header: "## G2 — Lawyer review of ..." (em dash or hyphen).
_SECTION_RE = re.compile(r"^##\s+(G\d+)\s+[—-]\s+(.+?)\s*$", re.MULTILINE)
_STATUS_RE = re.compile(r"^\s*\*\*Status:\*\*\s*(.+?)\s*$", re.MULTILINE)
_OWNER_RE = re.compile(r"^\s*\*\*Owner:\*\*\s*(.+?)\s*$", re.MULTILINE)
_BLOCKS_RE = re.compile(r"^\s*\*\*Blocks:\*\*\s*(.+?)\s*$", re.MULTILINE)
_CLOSURE_RE = re.compile(r"\*\*Closure record:\*\*\s*(.+?)\s*$", re.MULTILINE)
# A repository-relative docs path inside a closure-record line (strip backticks).
_DOC_PATH_RE = re.compile(r"`(docs/[^`]+)`")


_CALENDAR_HINT_RE = re.compile(r"~?\b\w+\s+20\d{2}\b|~\s*\d{4}|calendar", re.IGNORECASE)
_DATA_BOUND_HINT_RE = re.compile(
    r"data[- ]bound|none of the .* checked|after .* accumulation|≥\s*\d+ graded",
    re.IGNORECASE,
)


def _classify_status(raw: str) -> GateStatus:
    """Map a verbatim status string to a coarse bucket WITHOUT discarding nuance.

    Order matters: a "provisionally closed" gate is CLOSED (the ✅ wins); a
    "calendar" gate is open-but-future-dated; "data-bound" is open-but-criteria-
    gated. We key off the explicit markers the source file uses (✅/❌/⏳ plus the
    words 'closed'/'open'/'calendar'/'data-bound'), AND the finer hints the
    per-section header carries instead of the literal bucket word: a future-date
    parenthetical ("~Nov 2026") ⇒ CALENDAR, a criteria parenthetical ("none of
    the five checked") ⇒ DATA_BOUND. This lets the section parse and the
    quick-status table converge on the same fine bucket where the source
    supports it; where it cannot, both still agree on closed-vs-open (the
    load-bearing equality the no-fork test asserts)."""
    low = raw.lower()
    if "✅" in raw or "closed" in low:
        return GateStatus.CLOSED
    if "data-bound" in low or "data bound" in low or _DATA_BOUND_HINT_RE.search(raw):
        return GateStatus.DATA_BOUND
    if "calendar" in low or _CALENDAR_HINT_RE.search(raw):
        return GateStatus.CALENDAR
    # Remaining ⏳/❌ states are plain "open".
    return GateStatus.OPEN


def parse_gate_ledger(markdown: str, source_path: str = "(in-memory)") -> GateLedger:
    """Parse the canonical gate markdown into a typed :class:`GateLedger`.

    Pure function over the markdown string — no file IO, so the no-fork test can
    feed it a fixture copy. The per-section ``**Status:**`` line is authoritative
    for each gate; the quick-status table at the top is a *summary* we do NOT
    parse for state (it is the independent path the no-fork test uses)."""
    # Split the document into per-gate sections so a Status/Owner/Blocks line is
    # attributed to the right gate (not the next gate's).
    matches = list(_SECTION_RE.finditer(markdown))
    gates: list[Gate] = []
    for i, m in enumerate(matches):
        gate_id = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end]

        status_m = _STATUS_RE.search(body)
        if status_m is None:
            raise ValueError(
                f"{gate_id} section has no '**Status:**' line — the canonical "
                f"doc's structure changed; the parser must be updated rather "
                f"than guessing a status."
            )
        status_raw = status_m.group(1).strip()
        status = _classify_status(status_raw)

        owner_m = _OWNER_RE.search(body)
        owner = owner_m.group(1).strip() if owner_m else None

        blocks_m = _BLOCKS_RE.search(body)
        blocks = blocks_m.group(1).strip() if blocks_m else None

        closure_record: str | None = None
        closure_m = _CLOSURE_RE.search(body)
        if closure_m:
            path_m = _DOC_PATH_RE.search(closure_m.group(1))
            closure_record = path_m.group(1) if path_m else closure_m.group(1).strip()

        gates.append(
            Gate(
                gate_id=gate_id,
                title=title,
                status=status,
                status_raw=status_raw,
                owner=owner,
                blocks=blocks,
                closure_record=closure_record,
                impacts=_IMPACT.get(gate_id, ()),
            )
        )

    if not gates:
        raise ValueError(
            f"no gate sections found in {source_path} — expected '## GN — ...' "
            f"headers; the canonical doc's structure changed."
        )
    # Sort by numeric gate id so the ledger order is stable (G1, G2, ..., G13).
    gates.sort(key=lambda g: int(g.gate_id[1:]))
    return GateLedger(gates=tuple(gates), source_path=source_path)


def load_gate_ledger(path: Path | None = None) -> GateLedger:
    """Load + parse the canonical gate file. Reads only; never writes. This is
    the single entry point the API surface and the roadmap use; there is
    deliberately no ``save`` / ``write`` counterpart in this module."""
    p = path or canonical_gate_path()
    markdown = p.read_text(encoding="utf-8")
    return parse_gate_ledger(markdown, source_path=str(p))


# ── Independent second parse (for the no-fork test) ──────────────────────────
#
# A deliberately DIFFERENT extraction path: read the gate id + status from the
# top "Quick status" markdown table, not the per-section headers. The no-fork
# test asserts the two paths agree, which catches the ledger drifting from the
# human-edited source (a self-comparison could not).

_QUICK_ROW_RE = re.compile(
    r"^\|\s*(G\d+)\b[^|]*\|\s*(.+?)\s*\|", re.MULTILINE
)


def parse_quick_status_table(markdown: str) -> dict[str, GateStatus]:
    """Independently extract {gate_id: coarse status} from the top quick-status
    table. Used ONLY by the no-fork test as a second, independent path — never
    by the ledger itself."""
    out: dict[str, GateStatus] = {}
    for m in _QUICK_ROW_RE.finditer(markdown):
        gate_id = m.group(1)
        status_cell = m.group(2)
        out[gate_id] = _classify_status(status_cell)
    return out
