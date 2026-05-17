# substrate/context_pack/

Per-role context assembly with hierarchical memory. The bundle the
dispatch router actually sees.

## What a context pack contains

- **Hierarchical memory** — recent session context, relevant long-term
  skill content (domain/process/verification), retrieved graph evidence.
- **Active phase metadata** — which phase the investigation is in,
  which role is being invoked, any phase-specific constraints.
- **Parameter version stamp** — `ANTIEK_PARAM_VERSION` plus the
  versions of every skill referenced in the pack.

## Why this exists

Context isn't whatever fits in the window. It's deliberately layered
information assembled with awareness of what each layer contributes —
Luo's "精细编排的context", meticulously orchestrated context. This is
the architectural pattern that makes the Agent paradigm shift
substantive rather than ornamental. See architecture_notes §2.5 and
§3.1.

## Auditability

Every assembled pack is itself a typed event in the log
(`action_type: assemble_context_pack`). The question "what did the
model actually see when it made this decision" is answerable by
query, not by guessing.

## Budget discipline

Most invocations run on 32K–128K context with a curated pack. The 1M
context window is reserved for synthesis steps that genuinely require
it, and even then the pack is curated rather than dumped. See
architecture_notes §2.6.
