# Amendment: the `.antiek` self-render shell (`projection.html`)

**Status: AWAITING-RATIFICATION** — DRAFT. Engineering is complete and proven;
ratification is the operator's act (see *Operator actions* below). Do not treat
the shell as a ratified format feature until this doc is renamed and merged.

> Note: SPR-01 was specified to leave a DRAFT here; no draft existed at this
> path at SPR-04 time, so this document is authored complete rather than
> finished-from-a-stub. The lineage and proofs below stand on the shipped code.

## Lineage

1. **2026-05-23** — operator ratifies the native `.antiek` container format: a
   deterministic ZIP (`ZIP_STORED`, fixed 1980 timestamps, fixed entry order,
   byte-identical writes), Ed25519-signed, markdown-projection fallback, with a
   `_FORBIDDEN_SUBSTRATE_FIELDS` invariant keeping substrate-derived artifacts
   (chunks, embeddings, auto-edges, attribution, reward proxies) **out** of the
   file.
2. **HPRJ SPR-01** — `services/antiek_format/` lands the implementation
   (`feat(HPRJ SPR-01): land .antiek native container format`, commit
   `24eed084` on `html-projection/land-antiek`).
3. **HPRJ SPR-02 / SPR-03** — a pure, deterministic, script-free HTML renderer
   (doc-model → HTML with an inert `<template data-antiek="doc-model">` island)
   and its widget library land.
4. **This amendment (HPRJ SPR-04)** — the container becomes self-rendering:
   `projection.html` + the single-file `name.antiek.html` variant. Code:
   `feat(HPRJ SPR-04 M2-M4): …` (`9d60ed9f`) + M5/M6.

## What the shell IS

`projection.html` is a **derived projection**: the container's canonical
doc-model (`content.tiptap.json`) rendered through the SPR-02 renderer **at
write time** and stored as a ZIP entry. It lets a `.antiek` open and read as a
self-contained, offline, script-free web page without a separate viewer.

- Rendered deterministically: the renderer is pure and its write-time context
  carries no wall-clock (`rendered_at` is the substrate `created_at`, DATA not
  clock); two writes of the same input produce byte-identical shells.
- Substrate refs resolve to honest "not available offline" tombstones
  (`resolver=None`) — the shell never invents content the file does not carry.

## What the shell is NOT

- **Not canonical.** `content.tiptap.json` remains the single source of truth.
  The shell is derived and disposable; regenerating it from the payload yields
  the same bytes.
- **Not parsed back.** The reader never re-ingests the shell as truth (the
  embedded island is a render aid, not an authority). `ReadResult.projection_html`
  is surfaced for display only and is documented "never parse this back."
- **Not executable.** Zero-script, forever (see below).
- **Not a new payload type.** One amendment, one change: a derived entry whose
  integrity rides existing mechanisms.

## Version bump rationale — `1.0.0` → `1.1.0`

Additive MINOR per the writer's versioning policy ("bump MINOR on additive
changes a reader can fall back from"):

- **Pre-shell containers still read** — `projection.html` and the manifest's
  `projection_sha256` are optional; a `1.0.0` container reads unchanged
  (proven: `test_pre_shell_container_still_reads`).
- **Old readers ignore** the unknown entry (same-major warn-and-ignore path).
- **New readers verify** the shell hash when present.

`manifest.schema.json` already declares `additionalProperties: true`, so the new
`projection_sha256` field needs no schema change.

## Signature coverage — without widening the Ed25519 scope

The Ed25519 signing input stays `(manifest ⨾ content ⨾ edges)`. The shell binds
to the signature the **same way audio does**: its `sha256` lives in the SIGNED
manifest (`projection_sha256`). Therefore:

- A mutated shell byte → recomputed hash ≠ manifest hash → `signature_valid = False`
  (`test_mutated_shell_byte_fails_verification`).
- A shell removed while its hash is still claimed → missing entry →
  `signature_valid = False` (`test_removed_shell_with_claimed_hash_fails`) — an
  attacker cannot swap the shell out of the signed set.
- A mutated `projection_sha256` → changed signed manifest bytes → top-level
  Ed25519 verify fails (`test_mutated_manifest_hash_fails`).

Deterministic entry position: `manifest → content → projection.html → edges →
blocks/* → signature`. The shell sits right after the content it derives from;
the signature stays last so a streaming reader verifies after collecting
everything before it.

## Forbidden-substrate enforcement over HTML

The `_FORBIDDEN_SUBSTRATE_FIELDS` invariant must hold over **every** entry,
including the opaque HTML shell. The JSON-key walk does not see HTML, so a
write-time **byte-grep** runs over the rendered shell (raises before bytes hit
disk). Two prongs, designed NOT to false-positive on prose that merely
*mentions* the terms:

1. A forbidden field NAME used **structurally** — a JSON key (`"chunk_id":`),
   an HTML attribute (`data-embedding=`), or a labeled identifier in a comment
   (`chunk_id:`). Prose ("word embeddings are useful") has no `:`/`=` after the
   token and passes.
2. An **embedding-vector-shaped float array** (16+ inline floats), which has no
   field name to grep — the `data-x="[0.0123, …]"` leak. Threshold 16 is far
   below any real embedding (384–1536 dims) yet above any plausible inline
   decimal list a notebook legitimately carries.

Proven on attribute/comment/array placements and a clean-prose negative
(`test_byte_grep_catches_each_placement`, `test_byte_grep_no_false_positive_on_prose`,
`test_poisoned_doc_model_raises_at_write_via_shell`).

## Single-file `name.antiek.html` variant — signature scheme

`services/antiek_format/single_file.py`. Scheme id
**`ed25519-over-rendered-html-excised-sig-v1`** (one paragraph a future
implementer can follow):

> The single file is the rendered projection (which already carries the
> doc-model island) plus a second inert `<template data-antiek="signature">`
> island holding `{scheme, pubkey, sig}` (canonical JSON, base64). The signature
> is a detached Ed25519 over the **whole rendered projection with the signature
> island excised** — i.e. exactly the bytes the renderer produced before the
> island was injected, at the fixed injection point (before `</body>`). To
> verify: strip the one signature island, check the signature over the
> remaining bytes.

**Decision + trade-off (rigor #5).** We sign the rendered file (sig excised),
**not** only the doc-model island, because the sprint requires BOTH a tampered
island AND tampered rendered markup to fail. Signing only the island would miss
markup tampering. The cost: the single-file signature is over the *derived*
projection, not the canonical `content.tiptap.json` — that is what the `.antiek`
container's own signature is for. A single file is a share artifact, not the
canonical store; the doc-model island is inside the signed bytes, so the
canonical payload is transitively covered. **What would reverse it:** if a
future requirement needs the single file to carry a signature *over the
canonical payload* (e.g. to round-trip back into a container with provenance
intact), switch to signing `canonical_json_bytes(doc_model)` and accept that
markup tampering then needs a separate check. Proven:
`test_tampered_markup_fails`, `test_tampered_island_fails`,
`test_genuine_single_file_verifies`, `test_single_file_is_gate_clean`.

## Zero-script invariant — forever

Every shell and every single-file variant is **script-free**: no `<script>`, no
`on*=` handler, no `javascript:`/`vbscript:`/`data:` scheme, no external asset,
no CSS `@import`/`url(http…)`/`expression()`. This is load-bearing: the §7
continuous-research daemon ingests artifacts autonomously, so a script in a
shell is an RCE vector. The signature island is an inert `<template>`, exactly
like the doc-model island. The invariant applies to every shell produced now
and in the future; any future shell change MUST keep passing the SPR-02
zero-script gate (`test_shell_is_gate_clean`, `test_single_file_is_gate_clean`).

## Steelman of the shell-less alternative (rigor #2)

The shell-less alternative — markdown fallback stays the only projection —
costs nothing and adds no new entry. What the shell buys: a `.antiek` opens as a
real, styled, offline web page anywhere, with no viewer. **Who pays, measured:**
on a realistic 12-paragraph notebook the shell is **12.7 KB ≈ 70% of the
container, ~3× the canonical payload**. The multiple is fixed-CSS-dominated for
small notebooks (the inlined stylesheet + the doc-model island are roughly
constant) and **amortizes toward ~1× as the notebook grows**. The cost lands on
share-path storage and bandwidth, not on the canonical store. Operator
ratifies with this number in view; if share-path size becomes a constraint, the
markdown fallback remains and a "shell-on-demand" mode (render at share time,
not write time) is the documented escape hatch.

## Operator actions — what ratification means

1. **Review** this document and the proofs (the test files named above; run
   `./.venv/bin/python -m pytest services/antiek_format/ -q`).
2. **Accept the size cost** (~3× on small notebooks, amortizing) or direct the
   shell-on-demand alternative.
3. **Sign off** the single-file signature scheme + its trade-off.
4. **Rename** this file `antiek-html-shell-amendment.md` (drop `-DRAFT`) and
   record the ratification date + operator name at the top.
5. **Merge** the SPR-04 commits to `main` via the normal PR flow.

Until those steps complete, the shell ships behind the format's existing
gates as engineering-done / ratification-pending.
