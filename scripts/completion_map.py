#!/usr/bin/env python3
"""Generate docs/COMPLETION-MAP.md - a dated, honest snapshot of what is DONE.

WHY THIS EXISTS
    Nothing in this repository said what was finished. Every status-bearing document was
    either stale or planning-time, so a returning agent could not tell measured work from
    intended work. This script derives the map from live state (git, the API, the PR queue)
    and from the frozen rubric's per-dimension scores, so the map can be regenerated rather
    than remembered.

THE RULE THIS FILE OBEYS
    A status claim without an evidence class is a vibe. Every row carries one of the frozen
    rubric's own classes: PLANNED / BUILT / MERGED / DEPLOYED / VERIFIED LIVE / REPORTED.
    "A session reporting shipped is REPORTED, never DEPLOYED." MERGED is only ever claimed
    after `git merge-base --is-ancestor` proves the commit is on main.

Usage:  .venv/bin/python scripts/completion_map.py [--check]
        --check  exit 1 if the committed map is older than 7 days (CI guard, optional)
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "COMPLETION-MAP.md"
# The scoring standard is inlined below rather than cited: this repository does not carry
# review/RUBRIC.md, and a status document that points at a file the reader does not have is
# the exact stale-pointer defect this map's D10 row exists to catch. Publish what you cite.
DIMENSION_WEIGHTS = {12: "R1, R2", 14: "R6", 10: "R3, R4, R5, D7, D8", 6: "D9, D10"}

# The per-dimension locators live in the forensics workspace, which is OUTSIDE this repository.
# Saying so is the point: an agent that clones this repo cannot read those files, and a citation
# it cannot follow is worse than no citation, because it looks like one. Name the dependency.
EVIDENCE_ROOT = "~/research/antiek-v1-forensics-20260930"
SCORING_RULE = (
    "Each dimension is scored out of 100 against a fixed 100-condition. The operational "
    "partial-credit rule, adopted so every round's number is comparable: **five checkpoints "
    "per dimension, 20 points each, credited only when reproduced at the stated evidence level. "
    "Partial reproduction earns zero, not ten.** A score is only comparable to another score "
    "taken under the same conditions - which is why this file records the conditions, not just "
    "the number."
)

# ---------------------------------------------------------------------------------------
# The scores below are MEASURED, not inherited. Each was re-derived from a live
# measurement and carries the report that holds its locators. When a dimension's inputs
# change (a fix merges, a defect is found), its row must be re-measured rather than
# carried forward - a carried-forward score is a statement about the diff, not the
# dimension, and this repository has measured that practice inflating two dimensions.
#
# (id, rubric ref, name, weight, score, evidence class, measured on, source report, note)
# ---------------------------------------------------------------------------------------
DIMENSIONS = [
        (1, "R1", "One cockpit, one core asset", 12, 80, "VERIFIED LIVE", "2026-10-04",
     "review/ROUND-18-REGRADE-20261004.md",
     "Up from 60. D1.4 closes: the cockpit is the default layout, confirmed in a fresh standalone profile "
     "AFTER A LOCAL SESSION LOGIN rather than only in Storybook - the question round 16 left open. #3668 "
     "changed LAYOUT_PRESET_DEFAULT to omarchy-inset and persists it on startup, so a fresh profile writes "
     "an explicit preset instead of null. An explicit stored choice, including docked, still wins."),
    (2, "R2", "Keyboard-first operation", 12, 40, "VERIFIED LIVE", "2026-10-03",
     "review/D1-D2-INDEPENDENT-VERIFICATION-20261003.md",
     "Refuted from an inherited 60. An advertised binding (prefix+c) disarms without a picker; "
     "account-project selection exists in neither the table nor the UI. Fix blocked by the islands flake."),
    (3, "R3", "Omarchy insets", 10, 80, "VERIFIED LIVE", "2026-10-03",
     "review/D3-D4-D5-INDEPENDENT-VERIFICATION-20261003.md",
     "Upheld with measured pane rectangles at a stated viewport."),
    (4, "R4", "Pane semantics", 10, 80, "VERIFIED LIVE", "2026-10-03",
     "review/D3-D4-D5-INDEPENDENT-VERIFICATION-20261003.md",
     "Upheld; the agent-opens-into-left-document-space seam was driven live."),
    (5, "R5", "Writing shape", 10, 60, "VERIFIED LIVE", "2026-10-03",
     "review/D3-D4-D5-INDEPENDENT-VERIFICATION-20261003.md",
     "Refuted from an inherited 80. Drag-and-drop of a real source into an outline block IS reproduced and "
     "measured; the sentence-edit loop could not be reached because production answers 503 on the generate path."),
        (6, "R6", "Execution", 14, 80, "VERIFIED LIVE", "2026-10-04",
     "review/ROUND-18-REGRADE-20261004.md",
     "Up from 60. D6.5 closes: a claim with no stored core span now downgrades through the existing "
     "llm_expanded fallback (#3675), with the positive-span case still retained - both directions "
     "reproduced. The fork-merge authorization chain (#3674) is merged and DEPLOYED. D6.4 still fails: the "
     "reader's merge client is PRESENT-AND-WRONG - ReformatReview.tsx:82 sends generation_id as forkId and "
     "reformat.ts:173-190 posts to /forks/{id}/merge (404), while the registered routes want fork_id plus "
     "selected node items."),
    (7, "D7", "Craft standard", 10, 80, "VERIFIED LIVE", "2026-10-03",
     "review/D7-D10-INDEPENDENT-VERIFICATION-20261003.md",
     "Upheld on re-measurement, with the known gate holes tested against current main rather than restated."),
    (8, "D8", "Delivery", 10, 40, "DEPLOYED", "2026-10-03",
     "review/ROUND-16-REGRADE-20261003.md",
     "Fell from 80 on independent re-measurement. Two of five checkpoints reproduce: the reading code is on "
     "main, and the served API identity resolves to a commit that is an ancestor of main. Three do not, and "
     "the reason is EVIDENCE ACCESS rather than a regression: the production pane journey needs an "
     "authenticated browser, the served sha is 10 commits behind the measured main, and the production R6 "
     "journey answers 401. The scoring rule is explicit that an unverified live journey earns no credit, so "
     "this is unverified rather than proven absent."),
    (9, "D9", "Evidence", 6, 40, "REPORTED", "2026-10-02",
     "review/ANATOMY-REGRADE-20261002.md",
     "Partial. The lesson-noted record is strong; the underlying scorecard's own rubric substitution was the defect."),
    (10, "D10", "Spec quality and re-entry value", 6, 60, "VERIFIED LIVE", "2026-10-03",
     "review/D7-D10-INDEPENDENT-VERIFICATION-20261003.md",
     "Upheld. The canon publication closed the round-15 blocker; no current completion map existed - this file is it."),
]


def sh(cmd: str, timeout: int = 30) -> str:
    try:
        return subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception:
        return ""


def merged_into_main(sha: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/main"],
                          cwd=ROOT, capture_output=True).returncode == 0


def main() -> int:
    now = _dt.datetime.now(_dt.timezone.utc)
    main_sha = sh("git rev-parse origin/main") or sh("git rev-parse HEAD")
    main_subject = sh("git log -1 --format=%s " + (main_sha or "HEAD"))
    behind = sh(f"git rev-list --count {main_sha}..origin/main") if main_sha else "?"

    # The API is behind a proxy that refuses the default urllib agent, so use curl and fall
    # back to urllib only if curl is unavailable. A failed read is reported as unreachable
    # rather than silently omitted - the map must never imply parity it did not verify.
    health = {}
    for getter in (lambda: json.loads(sh("curl -s --max-time 15 https://api.antiek.ai/health")),
                   lambda: json.load(__import__("urllib.request").request.urlopen(
                       "https://api.antiek.ai/health", timeout=15))):
        try:
            health = getter()
            if health:
                break
        except Exception:
            health = {}
    prod_sha = str(health.get("build_sha", ""))[:12]

    prod_note = "unknown"
    if prod_sha and main_sha:
        if str(health.get("build_sha", "")) == main_sha or merged_into_main(prod_sha):
            ahead = sh(f"git rev-list --count {prod_sha}..{main_sha}")
            n = int(ahead or 0)
            prod_note = ("same commit as main" if n == 0 else
                         f"**{n} commit{'s' if n != 1 else ''} behind main** - "
                         "the backend deploys automatically once a gating workflow finishes, "
                         "so this gap is merge latency, not a missing deploy step")

    open_prs = sh("gh pr list --state open --limit 200 --json number --jq length") or "?"

    total = sum(w * s for _, _, _, w, s, *_ in DIMENSIONS) / 100.0

    L: list[str] = []
    L.append("# Completion map")
    L.append("")
    L.append(f"**Generated {now:%Y-%m-%d %H:%M} UTC from live state.** Regenerate with "
             f"`python scripts/completion_map.py` - do not hand-edit.")
    L.append("")
    L.append(f"- `origin/main` = `{main_sha}` - *{main_subject}*")
    L.append(f"- production API `build_sha` = `{prod_sha or 'unreachable'}` - {prod_note}")
    L.append(f"- open pull requests: **{open_prs}**")
    L.append(f"- measured grade against the frozen rubric: **{total:.1f} / 100**")
    L.append("")
    L.append("This file answers one question: **what is actually done, as of the sha above?** "
             "It exists because nothing in this repository previously said so, and a returning "
             "agent could not tell measured work from intended work.")
    L.append("")
    L.append("Every claim below carries one of the frozen rubric's evidence classes. "
             "`REPORTED` never becomes `DEPLOYED`. `MERGED` is only claimed when "
             "`git merge-base --is-ancestor` proves the commit is on main.")
    L.append("")
    L.append("## How the score is computed")
    L.append("")
    L.append(SCORING_RULE)
    L.append("")
    L.append("Weights sum to 100: R1 and R2 carry 12 each; R6 carries 14 (the heaviest, "
             "because execution is where intention and reality diverge); R3, R4, R5, D7 and D8 "
             "carry 10 each; D9 and D10 carry 6 each.")
    L.append("")
    L.append("## Score by dimension")
    L.append("")
    L.append("| # | Ref | Dimension | Weight | Score | Weighted | Evidence class | Measured |")
    L.append("|---|---|---|---:|---:|---:|---|---|")
    for i, ref, name, w, s, cls, day, _src, _note in DIMENSIONS:
        L.append(f"| {i} | {ref} | {name} | {w} | {s} | {w * s / 100:.1f} | {cls} | {day} |")
    L.append(f"| | | **Total** | **100** | | **{total:.1f}** | | |")
    L.append("")
    L.append("## What moves each dimension")
    L.append("")
    for i, ref, name, w, s, cls, _day, src, note in DIMENSIONS:
        flag = " **[STALE]**" if cls == "RE-MEASURING" else ""
        L.append(f"**{ref} - {name} ({s}/100, weight {w}){flag}** - {note} "
                 f"*(locators: `{EVIDENCE_ROOT}/{src}`, outside this repository)*")
        L.append("")
    L.append("## How a reader should use this")
    L.append("")
    L.append("1. **Do not trust a score whose inputs have changed.** When a fix merges or a defect "
             "is found for a dimension, re-measure that dimension and edit its row above. A score "
             "carried forward because 'the tree is unchanged' is a statement about the diff, not "
             "the dimension. The one time this repository tested that practice, it was inflating "
             "two of seven dimensions.")
    L.append("2. **Partial reproduction earns zero, not ten.** Five checkpoints per dimension, "
             "20 points each, credited only when reproduced at the stated evidence level.")
    L.append("3. **Prefer a command to a claim.** Every verdict needs an absolute locator: a file "
             "and line, a command with its output, or a URL with the computed value.")
    L.append("")
    L.append("## What is deliberately not built")
    L.append("")
    L.append("See the *What we deliberately have NOT built* section of `README.md`. "
             "An unbuilt thing that was never promised is not a defect; a promised thing that "
             "does not behave is.")
    L.append("")

    text = "\n".join(L)
    if "--check" in sys.argv:
        if not OUT.exists():
            print("completion map missing", file=sys.stderr)
            return 1
        age = (_dt.datetime.now().timestamp() - OUT.stat().st_mtime) / 86400
        if age > 7:
            print(f"completion map is {age:.1f} days old - regenerate it", file=sys.stderr)
            return 1
        print(f"completion map is {age:.1f} days old")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text)} bytes)")
    print(f"  main={main_sha[:9] if main_sha else '?'} prod={prod_sha or '?'} open_prs={open_prs} grade={total:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
