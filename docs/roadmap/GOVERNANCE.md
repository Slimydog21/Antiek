# Living Roadmap — governance

**Created:** 2026-05-27 (SPR-00, Living-Roadmap run)
**Scope:** how `docs/roadmap/ROADMAP.html` is allowed to change, and by whom.

The roadmap has two registers. They are governed differently, on purpose.

## The two registers

| Register | What it holds | Who may change it |
|---|---|---|
| **STABLE** | The thesis, the mechanism, and the 5 invariants. | **Operator only, by explicit ratification.** memento never touches it. |
| **FLUID** | The four surfaces, the interaction model, per-surface status, and the open questions. | **memento PROPOSES a diff; the operator RATIFIES before any write.** |

## The propose → ratify flow (FLUID register)

1. At the **end of a run**, memento MAY draft a proposed diff to the **FLUID register only** — surface status updates, interaction-model refinements, new or closed open questions.
2. memento surfaces that diff to the operator (the same "diff-then-approve" discipline memento already uses for the companion docs: show the change, get approval, then — and only then — write). See the memento skill's Core invariant #7 ("Diff-then-commit-then-push … Never push edits the operator hasn't seen") and Workflow step 5 ("Show the operator the diff + get approval"), at `/Users/slimydog/.claude/skills/memento/SKILL.md`.
3. The **operator ratifies** (or rejects, or amends) the proposed diff.
4. Only after ratification does the FLUID-register text change.

## Hard rules

- **memento never auto-writes the roadmap.** This is a HARD RULE. memento may *propose* a FLUID-register diff; it may *never* apply one without operator ratification. There is no path by which a memento run mutates `ROADMAP.html` on its own.
- **memento never touches the STABLE register.** Not the thesis, not the mechanism, not the 5 invariants, not their source citations.
- **memento never touches the supersession banners** on the prior specs (e.g. the `docs/master-product-spec.md` banner line). Banners are operator-bound.
- **memento never touches the invariants** under any register. Changing an invariant is an operator ratification event, not a memento proposal.

## How these rules are enforced

**These rules are convention-enforced, not hook-enforced.** As of 2026-05-27 the memento skill (`/Users/slimydog/.claude/skills/memento/`) is a prompt/skill with workflow prose — there is **no executable hook** (no entry in `~/.claude/settings.json` `hooks`, no hook script) that programmatically blocks memento from writing the roadmap, and its "Companion docs Memento maintains" table does **not** list `docs/roadmap/ROADMAP.html` at all. So there is nothing today that *mechanically* prevents a future agent from editing the roadmap; the protection is this document plus the memento skill's own propose→ratify discipline. No false claim of an enforced hook is made here.

**What memento's design already gives us (a seam, not a guarantee):** memento's existing discipline aligns with the propose→ratify gate — it shows a diff and waits for operator approval before writing, refuses to operate on vibes, and does not unilaterally commit. The roadmap simply is not in its maintained-docs set, so the safest correct behavior for memento today is: **do not write `ROADMAP.html`; at most, surface a proposed FLUID-register diff to the operator as an end-of-run open item.**

**Operator-bound follow-up (recorded, not auto-wired — out of scope for SPR-00):** if the operator wants this rule mechanically guaranteed rather than convention-enforced, the place to put a one-line pointer is the memento skill's hand-back step (SKILL.md step 7) or its companion-docs table — adding "ROADMAP.html is FLUID-register, propose-only; never auto-write (see docs/roadmap/GOVERNANCE.md)." That edit is to a file outside this worktree (`~/.claude/skills/memento/`) and is therefore operator-bound; SPR-00 documents the gate, it does not wire it.

## Prior-spec banners (status on this branch)

- `docs/master-product-spec.md` — **banner prepended** (SPR-00). It is the only prior-spec committed on this canonical branch (origin/main 76c2002).
- `specs/antiek-unified/` and `specs/{read,write,speak,deep-research-workspace}/` — **not present on this canonical branch** (neither committed nor in the working tree; the only `specs/` dir here is `karpathy-deep-lens-engineering`). Their bannering is **operator-bound**: the operator prepends the same supersession line in whatever working tree holds those untracked artifacts. SPR-00 does **not** fabricate those files or fake their banners.
