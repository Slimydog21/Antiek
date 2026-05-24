# ADRB dogfood — per-project entry template

Copy this block into `operator-log.md` for each of the 5 projects.
Fill in same-day while details are fresh. The substrate captures
mechanical signals (block counts, prompts, signals, costs); this
file captures what the substrate cannot: surprise, judgment, whether
the operator would open the bridge tomorrow.

---

## Project N — <topic>

**Goal.** One sentence.

**Provider mix.** Which external LLMs you used. Note any provider
ADDED mid-project versus the planned mix and why.

**Counts.** block_count_start: ___ → block_count_end: ___.
extractions_run: ___. gap_runs: ___. cascade_prompts_run: ___.

**Mode A — outline writing.**
- Used? yes / no.
- Drafts exported? ___.
- Would you send / publish it? yes / no / with-edits — 2 sentences why.
- If "no": dominant failure (LLM prose thin / drag awkward / outline
  didn't match the structure you wanted / ...).

**Mode B — gap-finder + cascaded prompts.**
- Used? yes / no.
- Cascade depth: how many find→run→paste-back→re-find iterations.
- Per-prompt signals: 👍 vs 👎 (substrate has the count; note the
  qualitative judgment here).
- Did the cascade cause you to run prompts you wouldn't have run
  otherwise? yes / no / partially.

**What failed.** Free text. Include zero-engagement sessions: any
time you opened the bridge, stared, and switched to your status-quo
workflow. This is the most useful data; do not omit it.

**What surprised me.** Free text — positive or negative.

**Would I open this again tomorrow?** yes / no / only-if-X.

**One-sentence verdict for this project.** SHIP / ITERATE / KILL.

---
