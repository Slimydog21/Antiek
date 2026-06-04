"""The reality-contact EVIDENCE report — ``python -m tools.reality_contact.report``.

SPR-02's scoreboard prints the RCR *number*; this module prints the EVIDENCE
behind it. It renders ``reports/reality_contact_evidence.md``: a deterministic,
diffable, fully-cited forensic list of every test the classifier called
``theater`` (or theater-for-a-subsystem via ``mixed``) and every test it could
not decide (``indeterminate``), each with a ``file:line`` a skeptic can open in
ten seconds and confirm the mock with their own eyes. The report is what turns
"RCR is 97.62%" from a claim into something a stranger can falsify line by line.

WHAT THIS REPORT IS HONEST ABOUT (the hard-to-vary point)
---------------------------------------------------------
Under the current contract ``theater == 0`` across the whole suite, so the
theater section is EMPTY. This report refuses to dress that up as a clean bill of
health. Two honest facts carry the report's value instead:

  * The INDETERMINATE forensics: exactly one file
    (``tests/test_book_qa_meta_reading.py``) is indeterminate — across four
    subsystems — via ``monkeypatch.setattr`` calls whose target the static
    classifier could not resolve. Each is cited with ``file:line`` + the
    unresolved target, straight from the ledger's ``unresolved_on_core`` entries.
  * The BLIND-SPOT caveat, carried VERBATIM from the ledger's
    ``known_blind_spots``: theater=0 does NOT mean the suite is real. Provider/LLM
    mocks are BOUNDARY by design, and the dominant fake-the-LLM pattern here is
    dependency injection, which is invisible to the static classifier (~56 files).
    So a reader can never read "0 theater" as "all good".

DETERMINISM (defensibility)
---------------------------
Same ledger -> byte-identical markdown. There is NO wall-clock timestamp; the
report stamps the ledger's ``boundaries_hash`` instead, so a reviewer can confirm
the evidence was generated against the current contract (not a stale boundary
list) and a PR that adds one theater test shows exactly one new line in the diff.
Every collection is sorted (subsystem, then path, then line) before rendering.

FAIRNESS (theater is a fact, not an accusation)
-----------------------------------------------
The report states the structural fact — this test patches this core symbol at
this line — and explicitly does NOT read intent. Some theater is correct
engineering (a legitimate error-path mock); that is precisely why SPR-04 adds a
recorded-exemption path rather than a blanket condemnation. The report names the
line so the author can make their own case.

The summary's RCR + per-subsystem table come from SPR-02's PURE ``compute_metric``
(MERGED in this worktree) so the report and the scoreboard can NEVER disagree —
they read the same ledger through the same arithmetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.reality_contact import LEDGER_PATH, REPO_ROOT
from tools.reality_contact.metric import RealityContactMetric, compute_metric

# Where the generated evidence report lands. Sibling of ``reports/arxiv_census.md``
# (the format reference); committed so it is reviewable in the PR and diffable
# thereafter.
REPORT_PATH: Path = REPO_ROOT / "reports" / "reality_contact_evidence.md"


def _fmt_rcr(rcr: float | None) -> str:
    """A ratio as a percentage to two decimals, or ``n/a`` when undefined
    (claiming == 0). Mirrors the scoreboard's ``_fmt_rcr`` contract: an undefined
    ratio is never coerced to 0% or 100%."""
    if rcr is None:
        return "n/a"
    return f"{rcr * 100:.2f}%"


def _theater_entries(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Every ``theater`` (subsystem, file, line) claim in the ledger, flattened
    into one row per cited mock and sorted deterministically.

    The ledger records theater under each file's ``core_mock_evidence`` — a list
    of ``{subsystem, target, form, lineno, raw}`` for every statically-resolved
    mock of a CORE symbol. A file that mocks K cores yields K rows here; each is
    grouped under the subsystem it is theater FOR. EMPTY under the current
    contract (theater == 0); the structure renders the empty case honestly.

    Sort key: (subsystem, path, lineno, target) — stable, diffable, and the order
    a reader scans the report in.
    """
    rows: list[dict[str, Any]] = []
    for entry in ledger.get("files", []):
        path = str(entry.get("path", ""))
        for ev in entry.get("core_mock_evidence") or []:
            rows.append(
                {
                    "subsystem": str(ev.get("subsystem", "")),
                    "path": path,
                    "lineno": int(ev.get("lineno", 0)),
                    "target": str(ev.get("target", "")),
                    "form": str(ev.get("form", "")),
                    "raw": str(ev.get("raw", "")),
                }
            )
    rows.sort(key=lambda r: (r["subsystem"], r["path"], r["lineno"], r["target"]))
    return rows


def _indeterminate_entries(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Every file the classifier could not decide, with its unresolved-on-core
    mock sites and the subsystems it claims.

    An ``indeterminate`` file claims one or more cores (``subsystem_labels`` all
    == "indeterminate") via mock sites whose TARGET the static analyzer could not
    resolve (e.g. ``monkeypatch.setattr(sys.modules["..."], ...)`` where the
    object is computed at runtime). The per-site evidence lives in
    ``unresolved_on_core`` as ``{form, lineno, raw}`` — note it carries NO
    subsystem (the unresolved target is exactly why no subsystem could be pinned),
    so the entry surfaces the file's claimed subsystems alongside its mock sites.

    Honesty (rigor #1): these are never silently dropped to make the theater list
    look more decisive. An honest instrument shows where it is unsure.

    Sort: files by path; within a file, sites by (lineno, form, raw).
    """
    rows: list[dict[str, Any]] = []
    for entry in ledger.get("files", []):
        if entry.get("verdict") != "indeterminate":
            continue
        path = str(entry.get("path", ""))
        labels = entry.get("subsystem_labels") or {}
        subsystems = sorted(str(s) for s in labels)
        sites = sorted(
            (
                {
                    "lineno": int(t.get("lineno", 0)),
                    "form": str(t.get("form", "")),
                    "raw": str(t.get("raw", "")),
                }
                for t in (entry.get("unresolved_on_core") or [])
            ),
            key=lambda d: (d["lineno"], d["form"], d["raw"]),
        )
        rows.append({"path": path, "subsystems": subsystems, "sites": sites})
    rows.sort(key=lambda r: r["path"])
    return rows


def _summary_lines(
    metric: RealityContactMetric,
    ledger: dict[str, Any],
    theater_count: int,
    indet_files: list[dict[str, Any]],
) -> list[str]:
    """The stranger-legible summary header: headline RCR, per-subsystem table,
    theater count, indeterminate roll-up, the framing note, and the blind-spot
    caveat carried verbatim from the ledger."""
    boundaries_hash = str(ledger.get("boundaries_hash", "(unknown)"))
    lines: list[str] = []

    lines.append("# Reality-contact evidence report")
    lines.append("")
    lines.append(
        "Generated by `python -m tools.reality_contact.report` from "
        "`tools/reality_contact/ledger.json`. Do not hand-edit — re-run the tool "
        "to regenerate. This report lists the EVIDENCE behind the reality-contact "
        "ratio (RCR): every test the classifier called *theater* and every test it "
        "could not decide (*indeterminate*), each with a `file:line` you can open "
        "and confirm yourself — no tooling, no trust required."
    )
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append("| field | value |")
    lines.append("| --- | --- |")
    lines.append(f"| boundaries hash (the contract this evidence was built against) | `{boundaries_hash}` |")
    lines.append(f"| ledger file count | {ledger.get('file_count', 'n/a')} |")
    lines.append(
        "| RCR source | `tools.reality_contact.metric.compute_metric` (same arithmetic the scoreboard uses) |"
    )
    lines.append("")
    lines.append(
        "The report stamps the boundaries hash instead of a wall-clock timestamp, "
        "so two runs over the same ledger are byte-identical and a reviewer can "
        "confirm the evidence matches the current contract rather than a stale "
        "boundary list."
    )
    lines.append("")

    # Headline + per-subsystem table — straight from compute_metric so the report
    # and the scoreboard can never disagree.
    lines.append("## Headline reality-contact ratio")
    lines.append("")
    headline = _fmt_rcr(metric.headline_rcr)
    lines.append(
        f"**RCR (claiming-weighted) = {headline}** = {metric.total_reality} reality "
        f"/ {metric.total_claiming} core-claiming (file, subsystem) claims, pooled "
        "across subsystems."
    )
    lines.append("")
    lines.append("| subsystem | claiming | reality | theater | indeterminate | RCR |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in metric.per_subsystem:
        lines.append(
            f"| `{row.subsystem}` | {row.claiming} | {row.reality} | "
            f"{row.theater} | {row.indeterminate} | {_fmt_rcr(row.rcr)} |"
        )
    lines.append(
        f"| **TOTAL** | **{metric.total_claiming}** | **{metric.total_reality}** | "
        f"**{metric.total_theater}** | **{metric.total_indeterminate}** | "
        f"**{headline}** |"
    )
    lines.append("")
    if metric.total_other:
        lines.append(
            f"> **{metric.total_other} core claim(s) carry a label this report does "
            "not recognize** (not reality/theater/indeterminate). They sit in the RCR "
            "denominator but in no column — investigate the classifier/contract "
            "before trusting the number."
        )
        lines.append("")

    # Theater / indeterminate counts.
    lines.append("## What this report contains")
    lines.append("")
    lines.append(
        f"- **Theater claims cited below: {theater_count}** "
        "(each is one mock of a CORE symbol at a `file:line`)."
    )
    lines.append(
        f"- **Indeterminate files cited below: {len(indet_files)}** "
        "(the classifier could not decide; surfaced rather than dropped)."
    )
    lines.append("")

    # The honesty framing for theater == 0 — NEVER presented as a clean bill.
    if theater_count == 0:
        lines.append(
            "> **`theater` is 0 under the current contract — this is NOT a clean "
            "bill of health.** It means no test *statically resolves* to a mock of a "
            "CORE symbol of the subsystem it covers. It does NOT mean the suite is "
            "real: provider/LLM mocks are BOUNDARY by design and the dominant "
            "fake-the-LLM pattern in this codebase is dependency injection, which is "
            "invisible to the static classifier (~56 files counted `reality` despite "
            "a stubbed synthesis). Read the **Known blind spots** section below "
            "before reading 0 theater as \"all good.\" The honest evidence in this "
            "report is the indeterminate forensics and the blind-spot caveat, not a "
            "victory lap."
        )
        lines.append("")

    # Framing note — theater is a structural fact, not an accusation.
    lines.append("## How to read the evidence below (framing)")
    lines.append("")
    lines.append(
        "Theater is a **structural fact, not an accusation of intent.** An entry "
        "means: *this test patches this CORE symbol at this line, so the assertion "
        "can be satisfied by the mock's own return value rather than by the real "
        "code path.* It does NOT mean the test is bad — some theater is correct "
        "engineering (a legitimate error-path unit test that mocks the orchestrator "
        "to force a failure). The report deliberately does not read intent; it gives "
        "you the exact `file:line` so you can open it and judge for yourself. That "
        "is why SPR-04 adds a recorded-exemption path rather than a blanket "
        "condemnation: legitimacy is recorded there, not asserted here."
    )
    lines.append("")

    # Known blind spots — carried VERBATIM from the ledger.
    lines.append("## Known blind spots (read before trusting the headline)")
    lines.append("")
    lines.append(
        "A HIGH RCR here is NOT \"the suite is real.\" These caveats are carried "
        "verbatim from the ledger's `known_blind_spots` block — the number is honest "
        "only WITH them attached."
    )
    lines.append("")
    blind_spots = ledger.get("known_blind_spots") or {}
    if not blind_spots:
        lines.append(
            "> **(none recorded in the ledger — TREAT THE NUMBER WITH SUSPICION.)**"
        )
        lines.append("")
    else:
        for key in sorted(blind_spots):
            value = blind_spots[key]
            lines.append(f"- **`{key}`:** {value}")
        lines.append("")

    return lines


def _theater_section(theater_rows: list[dict[str, Any]]) -> list[str]:
    """Render the theater evidence, grouped by subsystem. EMPTY under the current
    contract — rendered honestly, never as a clean bill of health."""
    lines: list[str] = []
    lines.append("## Theater evidence (by subsystem)")
    lines.append("")
    if not theater_rows:
        lines.append(
            "**0 theater claims under the current contract.** No test statically "
            "resolves to a mock of a CORE symbol of the subsystem it covers, so this "
            "section is empty. This is NOT a clean bill of health — see **Known "
            "blind spots** above: provider/LLM mocks are BOUNDARY by design and "
            "DI-stubbed-LLM fakes (~56 files) are invisible to the classifier and "
            "counted `reality`. An empty theater list means the *static* detector "
            "found nothing, not that the suite makes real contact everywhere."
        )
        lines.append("")
        return lines

    # Group by subsystem (rows are already sorted by subsystem, path, line).
    current_subsystem: str | None = None
    for row in theater_rows:
        if row["subsystem"] != current_subsystem:
            current_subsystem = row["subsystem"]
            lines.append(f"### `{current_subsystem}`")
            lines.append("")
            lines.append("| file:line | mocked core symbol | form | raw |")
            lines.append("| --- | --- | --- | --- |")
        lines.append(
            f"| `{row['path']}:{row['lineno']}` | `{row['target']}` | "
            f"`{row['form']}` | `{row['raw']}` |"
        )
    lines.append("")
    return lines


def _indeterminate_section(indet_files: list[dict[str, Any]]) -> list[str]:
    """Render the indeterminate evidence: each file the classifier abstained on,
    with the subsystems it claims and every unresolved-on-core mock site cited by
    `file:line` + the unresolved target. Never silently dropped (rigor #1)."""
    lines: list[str] = []
    lines.append("## Indeterminate evidence (the classifier abstained here)")
    lines.append("")
    if not indet_files:
        lines.append(
            "**0 indeterminate files.** The classifier reached a verdict on every "
            "core-claiming test."
        )
        lines.append("")
        return lines

    lines.append(
        "These files claim one or more CORE subsystems but mock them via a target "
        "the static analyzer could not resolve (e.g. `monkeypatch.setattr` on a "
        "runtime-computed object), so the classifier conservatively abstained — it "
        "counts toward the RCR denominator but never the numerator, so it can only "
        "ever hold the number DOWN. They are listed so a reader sees exactly where "
        "the instrument itself could not tell reality from theater."
    )
    lines.append("")
    for f in indet_files:
        subsystems = ", ".join(f"`{s}`" for s in f["subsystems"])
        lines.append(f"### `{f['path']}`")
        lines.append("")
        lines.append(f"Claims (all `indeterminate`): {subsystems}")
        lines.append("")
        lines.append("| file:line | form | unresolved target |")
        lines.append("| --- | --- | --- |")
        for site in f["sites"]:
            lines.append(
                f"| `{f['path']}:{site['lineno']}` | `{site['form']}` | "
                f"`{site['raw']}` |"
            )
        lines.append("")
    return lines


def render_report(ledger: dict[str, Any]) -> str:
    """Render the full evidence report markdown from a parsed ledger dict. PURE —
    no I/O — so a test can assert determinism and committed-equals-render without
    touching the file system. Trailing newline for POSIX-friendly diffs."""
    metric = compute_metric(ledger)
    theater_rows = _theater_entries(ledger)
    indet_files = _indeterminate_entries(ledger)

    lines: list[str] = []
    lines.extend(_summary_lines(metric, ledger, len(theater_rows), indet_files))
    lines.extend(_theater_section(theater_rows))
    lines.extend(_indeterminate_section(indet_files))

    # Single trailing newline; no internal trailing whitespace.
    return "\n".join(lines).rstrip("\n") + "\n"


def load_ledger(ledger_path: Path = LEDGER_PATH) -> dict[str, Any]:
    """Parse the ledger JSON. Kept tiny + separate so tests can feed a fixture
    ledger straight to ``render_report`` without going through the file system."""
    parsed: dict[str, Any] = json.loads(ledger_path.read_text(encoding="utf-8"))
    return parsed


def write_report(
    ledger_path: Path = LEDGER_PATH, out_path: Path = REPORT_PATH
) -> str:
    """Load the ledger, render the report, write it. Returns the rendered text."""
    ledger = load_ledger(ledger_path)
    text = render_report(ledger)
    out_path.write_text(text, encoding="utf-8")
    return text


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    text = write_report()
    theater = text.count("\n")  # cheap line count for the operator line below
    print(f"Reality-contact evidence report written to {_rel(REPORT_PATH)}")
    print(f"  source ledger: {_rel(LEDGER_PATH)}")
    print(f"  rendered lines: {theater}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
