# karpathy-deep-lens-engineering — substrate reconciliation beneath the four-workflow flywheel

**Sharpened 2026-05-25** against the unified product vision
(`specs/antiek-unified/` + the four product specs: `deep-research-workspace/`,
`read/`, `write/`, `speak/`), the canonical tech-stack owners, and the sibling
`karpathy-engineering` spec.

> **Provenance note.** An in-session 10-sprint execution draft (generated from
> the Karpathy *Deep Dive into LLMs* lens at `~/specs/antiek-karpathy-deep-lens/`)
> was **swept** — it lived untracked in `specs/karpathy-execution/` and was lost
> during a parallel-stream branch operation, the exact collision `CLAUDE.md`
> warns about. The philosophy lens survives (outside the repo at
> `~/specs/antiek-karpathy-deep-lens/`); this engineering reconciliation is
> re-created and **committed this time**.

## What this spec is now

The deep-dive lens (post-training, RL, cognition) produced six truths and a
10-sprint draft. Reconciled against (a) the four-product unified vision, (b)
the `antiek-unified` ledger's "one owner per layer, enforced mechanically"
invariant, and (c) the canonical owners in the live codebase, **nine of ten
collapse**:

- **1 KEEP (ungated):** uniform role-parser ID/provenance validation —
  generalize the grounder's chunk-id check to every parser. Ungated,
  unowned, serves the four-workflow provenance moat, W4-consistent.
- **1 GATED package:** the RL payload (7 verifiable rewards → `verifiers_env`,
  per-step shaping → `trajectory_harvest`, interrogation data) re-homed
  *inside* `substrate/loop_3/`, inert behind G8.
- **8 reconciled:** rewards/trajectory/verifier owned by `substrate/loop_3/`
  (gated G8); prompt lint forks `tools/lint/`; docs manifest has no consumer;
  prompt_version + versioned-prompts fold into `karpathy-engineering` SPR-01's
  `program.md` frontmatter; the three LLM judges are **rejected** because
  temporal/source_tier/supersession are already deterministic middleware and an
  LLM judge contradicts the lens's own W4.

**Open `index.html` first** — the reconciliation matrix, the surviving sprint,
the gated package, the tech-stack alignment, and the four-workflow service map.

## The hard-to-vary thesis

Where the lens and the four-product reality disagree about who owns a layer,
reality wins. Executing ten substrate sprints against an essentially-complete
codebase with named owners is the opposite of genius — it forks owned layers
and generates divergence bugs. The 9:1 collapse ratio is the deliverable as
much as the survivor is.
