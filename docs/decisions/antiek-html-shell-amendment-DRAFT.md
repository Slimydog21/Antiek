# DRAFT — `.antiek` HTML-shell amendment (HTML Projection Layer, SPR-04)

**Status:** **DRAFT — NOT RATIFIED.** Ratification is **operator-only**. Nothing
in this document changes the wire format until the operator ratifies it; until
then it records intent and sequencing so the format's decision lineage stays
one chain.
**Drafted:** 2026-06-12, by HTML-projection SPR-01 (the sprint that landed the
native container on main).
**Amends:** binding decision #2 of
[`wrestle-evolution-spec-2026-05-23.md`](wrestle-evolution-spec-2026-05-23.md)
(the operator-ratified `.antiek` container decision of 2026-05-23).
**Parent verdict:** the egghead-tribunal ruling of 2026-06-12 — HTML is a
*derived projection face*, never canonical storage; substrate-is-source-of-truth
(master spec §13.2) is untouched.

---

## Sidecar sequencing — read this first

**The native-container core landed now; the sidecar overlay is SEQUENCED behind
its substrate landing, not dropped.** Decision #2 ratified *two* container
variants: the native container for born-Antiek content AND the PDF sidecar
overlay ("PDF stays source-of-truth for imported content; sidecar overlay
carries user data"). The SPR-01 landing (this amendment's sibling PR)
transported only the native core — `sidecar_writer.py`, `sidecar_reader.py`,
and `tests/test_sidecar_e2e.py` stayed on the `wrestle-evolution/integration`
branch because `apply_sidecar` is functionally wired to `substrate.voice`
(anchor re-resolution), `substrate.behavior.taxonomy` (voice-note restore
events), and `services.ingestion.sidecar_detector` — none of which exist on
main, and all of which the SPR-01 sprint page names out-of-scope. The sidecar
half of decision #2 therefore lands **when the voice-anchor + behavior-taxonomy
+ chunks-geometry substrate lands**, as its own reviewed transport. Decision
#2's lineage stays one chain: 2026-05-23 ratification → this landing (native
core) → sidecar landing (behind its substrate) → SPR-04 shell amendment (this
draft). `services/antiek_format/SPEC.md` §11 carries the matching landing-status
annotation.

**Export routes deferred with it:** `interfaces/research/api/themes.py` imports
the branch-only `services.notebooks` surface, and `share_bundle.py` is the
sidecar share flow — both stay behind. SPR-06 of the HTML Projection Layer
wires container emission into share routes against main's substrate
(pre-authorized by the SPR-01 scope ruling).

---

## What SPR-04 will add (the amendment being drafted)

SPR-04 of the HTML Projection Layer spec (`~/specs/antiek-html-projection/`)
will add **one zip entry** to the native `.antiek` container:

- **`projection.html`** — a self-contained, offline-renderable HTML shell of
  the container's content, emitted by the writer at write time the same way
  the markdown projection is emitted by `project_to_markdown`: derived from
  the canonical TipTap body, deterministic (same container → byte-identical
  shell), and **outside nothing** — the entry participates in the same
  deterministic zip layout (sorted entries, fixed 1980 timestamps,
  ZIP_STORED) the format already guarantees.
- The shell obeys the **zero-script invariant**: no `<script>`, no external
  fetches, no CDNs, no executable content of any kind. It must render fully
  offline in a bare browser.
- Whether the shell's bytes join the Ed25519 signing input (a fourth canonical
  section) or stay outside the signature scope like the zip envelope is an
  SPR-04 design decision — flagged here so the ratifier sees it coming; the
  signing-input shape change, if any, is a schema_version MINOR bump per
  SPEC.md §7.

## What the shell is NOT

- **Not canonical.** The TipTap JSON (`content.tiptap.json`) remains the
  single source of truth; the shell is a projection of it, regenerated on
  every write. A reader that ignores `projection.html` entirely loses
  nothing. If shell and body ever disagree, the body wins and the shell is a
  bug.
- **Not executable.** Zero-script, zero-network, zero-form-action. A
  `.antiek` file must never become a code-delivery vehicle.
- **Not a new payload type.** No content class is added; the shell is an
  additional *projection* of the existing classes, exactly parallel to the
  markdown projection — not a new kind of content the substrate must learn to
  ingest. The `_FORBIDDEN_SUBSTRATE_FIELDS` invariant applies to the shell's
  bytes the same as every other entry: no chunks, no embeddings, no
  substrate-derived edges, no attribution or reward data.
- **Not a storage-format change of authority.** Per the 2026-06-12 tribunal
  verdict, HTML-as-canonical-storage was REJECTED; this amendment implements
  HTML-as-projection only.

## Ratification

- **Ratifier: the operator.** This draft becomes binding only by explicit
  operator ratification, recorded by renaming this file to drop `-DRAFT` and
  stamping the ratification date — the same convention as every other closed
  decision in `docs/decisions/`.
- Until ratified, SPR-04 must not ship a writer that emits `projection.html`
  into containers; the renderer work may proceed against fixtures.

## Decision lineage (reconstructible from docs/decisions/ alone)

1. **2026-05-23** — `.antiek` container ratified (native + sidecar), binding
   decision #2 of `wrestle-evolution-spec-2026-05-23.md`.
2. **2026-06-12** — native-container core landed on main (HTML-projection
   SPR-01); sidecar + export routes sequenced, not dropped (this file, section
   "Sidecar sequencing").
3. **(future)** — sidecar overlay lands behind the voice-anchor +
   behavior-taxonomy + chunks-geometry substrate.
4. **(future)** — this amendment ratified by the operator; SPR-04 adds the
   `projection.html` shell entry.
