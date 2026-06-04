"""The reality-contact scoreboard — ``python -m tools.reality_contact``.

A read-only, exit-coded, mock-free CLI (sibling to the First-Light status board):
it loads the SPR-01 ledger, verifies the ledger is FRESH (its embedded
``boundaries.yaml`` hash still matches a re-hash of the current contract), computes
the RCR via the pure ``metric`` module, and prints — adjacent, never separable —
the headline RCR, the per-subsystem table, the totals, AND the ledger's
``known_blind_spots`` caveat. This module imports ZERO core/product module (and
not even the classifier/ledger builders): it reads JSON, re-hashes one file, and
does arithmetic. It can therefore neither exercise nor mock the thing it measures.

WHY THE CAVEAT IS PRINTED INLINE (the hard-to-vary point of this sprint)
-----------------------------------------------------------------------
theater == 0, so the headline RCR is HIGH (~near 100%). That is EXACTLY when the
caveat matters most: a "99% reality contact" headline is dangerously reassuring
while the motivating disease — mock the LLM via dependency injection, assert a
synthesis — is INVISIBLE to this metric by design (the provider is a BOUNDARY
seam; the DI fakes are uncounted). So the scoreboard refuses to print the number
without the ``known_blind_spots`` block beside it. A glowing number with no caveat
is the false confidence this whole spec exists to break.

EXIT-CODE SEMANTICS (defensibility)
-----------------------------------
  * 0  — ledger present, parseable, and FRESH (boundaries hash matches). The RCR
         table is printed. This is NOT a pass/fail-vs-baseline verdict.
  * 2  — ledger missing, unreadable, or STALE (its boundaries hash no longer
         matches the current ``boundaries.yaml``). Nothing is computed; a clear
         message tells the operator to regenerate via
         ``python -m tools.reality_contact.ledger``. We refuse to print a number
         computed against a contract that has since moved.

There is DELIBERATELY no baseline / ratchet / pass-fail-vs-threshold here. The
exit code reflects only ledger freshness, not "is the number good enough." The
baseline gate is SPR-04 (``tools/reality_contact`` baseline) and CI is SPR-05.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.reality_contact import BOUNDARIES_PATH, LEDGER_PATH, REPO_ROOT
from tools.reality_contact.metric import RealityContactMetric, compute_metric

EXIT_OK = 0
EXIT_STALE_OR_MISSING = 2


def _current_boundaries_hash(boundaries_path: Path = BOUNDARIES_PATH) -> str:
    """Re-hash the live ``boundaries.yaml`` with the SAME scheme the ledger used
    (``sha256:<hexdigest>`` of the verbatim file text). Matching this against the
    ledger's stored ``boundaries_hash`` is the freshness check: if the contract
    moved since the ledger was built, the number is computed against a stale
    boundary and must not be trusted."""
    text = boundaries_path.read_text(encoding="utf-8")
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fmt_rcr(rcr: float | None) -> str:
    """A ratio as a percentage to two decimals, or ``n/a`` when undefined
    (claiming == 0). Never coerces an undefined ratio to 0% or 100%."""
    if rcr is None:
        return "  n/a "
    return f"{rcr * 100:6.2f}%"


def render(metric: RealityContactMetric, known_blind_spots: dict[str, Any]) -> str:
    """Render the full scoreboard as text. PURE — no I/O — so a test can assert
    the caveat travels with the number without touching the file system.

    The ``known_blind_spots`` block is rendered AS PART OF the same output, by
    design: the number and its caveat are one artifact, not two."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("  REALITY-CONTACT RATIO (RCR) — Antiek test suite")
    lines.append("=" * 78)
    lines.append("")

    headline = _fmt_rcr(metric.headline_rcr).strip()
    lines.append(f"  HEADLINE RCR (claiming-weighted):  {headline}")
    lines.append(
        f"    = {metric.total_reality} reality / {metric.total_claiming} core-claiming "
        f"(file, subsystem) claims, pooled across subsystems"
    )
    lines.append("")

    # Per-subsystem table.
    header = (
        f"  {'subsystem':40s} {'claim':>6s} {'real':>6s} "
        f"{'theatr':>6s} {'indet':>6s} {'RCR':>8s}"
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for row in metric.per_subsystem:
        lines.append(
            f"  {row.subsystem:40s} {row.claiming:>6d} {row.reality:>6d} "
            f"{row.theater:>6d} {row.indeterminate:>6d} {_fmt_rcr(row.rcr):>8s}"
        )
    lines.append("  " + "-" * (len(header) - 2))
    lines.append(
        f"  {'TOTAL':40s} {metric.total_claiming:>6d} {metric.total_reality:>6d} "
        f"{metric.total_theater:>6d} {metric.total_indeterminate:>6d} "
        f"{_fmt_rcr(metric.headline_rcr):>8s}"
    )
    lines.append("")

    # Unrecognized labels: surfaced loudly rather than left to lower RCR silently
    # from inside the denominator. Zero under SPR-01's current contract, so this
    # block is absent today and the output is unchanged; it appears only if the
    # classifier ever emits a label the metric does not name.
    if metric.total_other:
        lines.append(
            f"  !! {metric.total_other} core claim(s) carry a label this scoreboard "
            "does not recognize"
        )
        lines.append(
            "     (not reality/theater/indeterminate). They sit in the RCR "
            "denominator but in no column —"
        )
        lines.append(
            "     investigate the classifier/contract before trusting the number."
        )
        lines.append("")

    # The caveat travels WITH the number — non-negotiable for this sprint.
    lines.append("-" * 78)
    lines.append("  KNOWN BLIND SPOTS (read before trusting the number above)")
    lines.append("-" * 78)
    if not known_blind_spots:
        lines.append("  (none recorded in ledger — TREAT WITH SUSPICION)")
    else:
        for key in sorted(known_blind_spots):
            value = known_blind_spots[key]
            lines.append(f"  * {key}:")
            lines.extend(_wrap(str(value), indent="      "))
    lines.append("")
    lines.append(
        "  A HIGH RCR here is NOT 'the suite is real': provider/LLM mocks are "
        "BOUNDARY by"
    )
    lines.append(
        "  design and DI-stubbed-LLM fakes are counted 'reality'. Read the blind "
        "spots."
    )
    lines.append("=" * 78)
    return "\n".join(lines)


def _wrap(text: str, indent: str = "", width: int = 78) -> list[str]:
    """Word-wrap a paragraph to ``width`` columns with a fixed left ``indent``.
    Kept here (instead of textwrap) so the caveat renders identically regardless
    of host wrapping behaviour."""
    out: list[str] = []
    cur = ""
    for word in text.split():
        candidate = indent + word if not cur else cur + " " + word
        if len(candidate) > width and cur:
            out.append(cur)
            cur = indent + word
        else:
            cur = candidate
    if cur:
        out.append(cur)
    return out


def _stale_message(ledger_path: Path, reason: str) -> str:
    rel = _rel(ledger_path)
    return (
        f"reality-contact: {reason}\n"
        f"  ledger: {rel}\n"
        f"  Regenerate it with:  python -m tools.reality_contact.ledger\n"
        f"  (refusing to print an RCR computed against a stale or missing contract)"
    )


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def run(
    ledger_path: Path = LEDGER_PATH,
    boundaries_path: Path = BOUNDARIES_PATH,
) -> int:
    """Load → verify freshness → compute → print. Returns the process exit code.

    Separated from ``main`` so tests can drive it with alternate paths (e.g. a
    missing ledger) without spawning a subprocess."""
    if not ledger_path.exists():
        print(_stale_message(ledger_path, "ledger not found"))
        return EXIT_STALE_OR_MISSING

    try:
        ledger: dict[str, Any] = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(_stale_message(ledger_path, f"ledger could not be read/parsed: {exc}"))
        return EXIT_STALE_OR_MISSING

    stored_hash = ledger.get("boundaries_hash")
    try:
        current_hash = _current_boundaries_hash(boundaries_path)
    except OSError as exc:
        print(_stale_message(ledger_path, f"boundaries.yaml could not be read: {exc}"))
        return EXIT_STALE_OR_MISSING

    if stored_hash != current_hash:
        print(
            _stale_message(
                ledger_path,
                "ledger is STALE — its boundaries hash no longer matches "
                f"boundaries.yaml\n  ledger hash:  {stored_hash}\n  current hash: "
                f"{current_hash}",
            )
        )
        return EXIT_STALE_OR_MISSING

    metric = compute_metric(ledger)
    known_blind_spots: dict[str, Any] = ledger.get("known_blind_spots") or {}
    print(render(metric, known_blind_spots))

    # NOTE: this is NOT a pass/fail-vs-baseline gate. A fresh, computable ledger
    # exits 0 regardless of how high or low the number is. The baseline/ratchet
    # gate is SPR-04; CI wiring is SPR-05. Do not add a threshold here.
    return EXIT_OK


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
