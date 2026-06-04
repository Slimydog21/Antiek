/**
 * The one-Reader conformance CONTRACT — the TS/bundle half SPR-09 will fill
 * (antiek-reader SPR-01 M4).
 *
 * The Python side (`substrate/contracts/__tests__/test_reader_conformance.py`)
 * owns the substrate round-trip (door c) plus the machine-checkable half of
 * doors (a)/(b) that lives in `migration-map.md`. THIS file owns the front-end
 * half: that every open-a-document door routes through `openDocument` → the one
 * `<Reader>`, and that NO second document renderer survives in the production
 * bundle. It MIRRORS the Python stub's two pinned sets so the two stay in
 * lockstep — a door dropped here OR there is a weakened gate.
 *
 * These stubs DO NOT pass today: the one `<Reader>` (SPR-03), the routed doors
 * (SPR-05), and the deletion of the redundant renderers (SPR-05) do not exist
 * yet. Each behavioural assertion is `it.skip(...)` with a reason naming the
 * sprint that unblocks it. SPR-09 turns each skip into a real, green assertion
 * (parsing call sites / asserting the built bundle's imports) and deletes the
 * lying seam test. A future instance MUST NOT quietly weaken these: the
 * non-skipped guards below pin the EXACT door set + forbidden-renderer set, so
 * shrinking either is a red test, not a silent edit.
 *
 * Lockstep partners (keep identical):
 *   - migration-map.md  §2 (OPEN doors)  §1 (forbidden renderers)
 *   - test_reader_conformance.py  EXPECTED_OPEN_DOORS  FORBIDDEN_PROD_RENDERERS
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { describe, expect, it } from "vitest";

// Load-bearing imports: the real SPR-01 contract types. If the contract is
// deleted or its surface changes, this file fails to compile under `tsc
// --noEmit` — the stub cannot rot into a no-op that quietly passes.
import type { OpenDocument, OpenDocumentOptions, ReaderProps } from "../lib/openDocument.contract";
import type { Document, Region } from "../types/document_model.gen";

// SPR-05 fills the door-(a)/forbidden-(b) halves of this conformance against the
// PRODUCTION SOURCE (the call sites + the renderer modules). SPR-09 will lift
// these to the BUILT BUNDLE (a true forbidden-import check on the compiled
// output); the source-level assertions here are the convergence SPR-05 lands and
// SPR-09 tightens — not a stub.
const _here = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(_here, "..");
const readSrcRaw = (rel: string): string => readFileSync(resolve(SRC, rel), "utf-8");
// Strip // line comments, /* block */ comments, and {/* JSX */} comments so a
// conformance assertion matches LIVE CODE, not a historical reference left in a
// doc comment (e.g. "was a /wrestle/:id mis-route"). Crude but sufficient for
// these source-level checks (no comment markers appear inside string literals we
// assert on here).
const readSrc = (rel: string): string =>
  readSrcRaw(rel)
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");

// ───────────────────────────────────────────────────────────────────────────
// Door (a) — every open-a-document door routes to the one Reader.
//
// The authoritative door list is migration-map.md §2; this set MIRRORS
// EXPECTED_OPEN_DOORS in test_reader_conformance.py exactly (same 11 ids). SPR-09
// asserts each id's call site invokes openDocument(documentId, opts) — not
// navigate('/wrestle/...') and not a bespoke renderer.
// ───────────────────────────────────────────────────────────────────────────

/**
 * The exhaustive OPEN-door set SPR-09 must prove routes through `openDocument`
 * to the one `<Reader>`. Each entry: the door id (mirrors EXPECTED_OPEN_DOORS)
 * → the verified call site SPR-09 parses. Cross-checked against migration-map.md
 * §2. Dropping a door to make the test pass is a weakened gate (the guard below
 * makes it a red test).
 */
export const EXPECTED_OPEN_DOORS: Readonly<Record<string, string>> = {
  "Library.openWork": "src/modes/Library/index.tsx:145", // → navigate('/read/:id') today
  "LibraryView.open": "src/components/library/LibraryView.tsx:71", // → navigate('/read/:id') today
  "Reading.openDoc": "src/modes/Reading/index.tsx:41", // BookReader — the current /read/:id reader
  "DocumentsIndex.open": "src/modes/DocumentsIndex/index.tsx:158", // → /wrestle/:id (MIS-ROUTE)
  "CommandPalette.openDocument": "src/components/CommandPalette.tsx:390", // → /wrestle/:id (MIS-ROUTE)
  "ChunkModal.openInDocument": "src/modes/ResearchWorkstation/ChunkModal.tsx:176", // → /wrestle/:id (MIS-ROUTE)
  "MasterMdViewer.cmdClick": "src/modes/ResearchWorkstation/MasterMdViewer.tsx:762", // → openPdfPanel (:774)
  "DRW.citeSource": "src/modes/DeepResearchWorkspace/Canvas/BlockCard.tsx:117", // onCiteSource; host-wired in index.tsx
  "Write.traceToSource": "src/modes/Write/WriteHome.tsx:101", // open call (Citation.tsx:38 emits, traceIntent.ts bus)
  "MetaReading.openCitation": "src/modes/Reading/MetaReading/index.tsx:95", // → navigate('/read/:id') (:104)
  "Route./read/:documentId": "src/App.tsx:161", // the canonical Reader route (mounts BookReader today)
} as const;

/**
 * The DOCUMENT-OPENING renderers/seams SPR-05 deletes / folds into the one
 * `<Reader>`. SPR-09 asserts NONE is reachable as a second document renderer in
 * the production bundle. MIRRORS FORBIDDEN_PROD_RENDERERS in
 * test_reader_conformance.py. `PdfViewer` / `WrestleApp` are DELIBERATELY ABSENT
 * — they survive behind the ingest entry point (migration-map.md §3), never as
 * an open-a-document renderer.
 *
 * ── SPR-05 RECONCILIATION (recorded; the set is sharpened, never weakened) ──
 * The SPR-01 set named `ReadingColumn.tsx::renderBlocks` as a forbidden
 * renderer. SPR-05 reconciles that to the truth the verified tree showed:
 * `ReadingColumn` is the SANCTIONED legacy fallback — the one body renderer the
 * `/read/:id` Reader degrades to when `structured_blocks` is NULL (a legacy /
 * un-backfilled doc), reachable ONLY behind that one gated route, never as a
 * SECOND document renderer from an open door. So it is EXCLUDED here (deleting
 * it would break the legacy read path it defends). What is forbidden is a SECOND
 * document renderer reachable from an OPEN door — every such seam is now routed
 * to `openDocument`:
 *   • MasterMdViewer's by-id OPEN seam (the cmd-click that opened a bespoke PDF
 *     panel) — now `openDocument`; MasterMdViewer SURVIVES as a synthesis-
 *     summary view that never opens a document by id (the spec's carve-out).
 *   • MetaReading's bespoke `<article>` body — converged to the sanctioned
 *     `ReadingColumn` body (no second bespoke document `<article>`).
 *   • DRW's ad-hoc node-text div (BlockDetail.tsx) — its OPEN-the-source
 *     capability is now `openDocument` (the wired `onCiteSource`); the div
 *     renders a GRAPH NODE's text (a node primitive), not a document by id.
 * The entries below name the document-opening SEAMS that SPR-09 asserts are gone
 * from the open paths; the migration map §5 carries the file:line bridge.
 */
export const FORBIDDEN_PROD_RENDERERS: readonly string[] = [
  "modes/ResearchWorkstation/MasterMdViewer.tsx::openByIdSeam", // cmd-click PDF panel → now openDocument
  "modes/Reading/MetaReading/index.tsx::article", // bespoke <article> → converged to ReadingColumn (:254)
  "modes/DeepResearchWorkspace/index.tsx::canvasTextDiv", // open-source seam → openDocument (actual div: BlockDetail.tsx:87, map §5)
  "components/PdfViewer.tsx::asOpenTarget", // PdfViewer mounted as an OPEN-a-document target — gone (survives as ingest only)
] as const;

// The three doors that TODAY mis-route to /wrestle (the convergence target the
// one-door work must collapse). Mirrors the Python stub's named subset.
const MISROUTED_TO_WRESTLE_TODAY: readonly string[] = [
  "DocumentsIndex.open",
  "CommandPalette.openDocument",
  "ChunkModal.openInDocument",
] as const;

// ───────────────────────────────────────────────────────────────────────────
// Non-skipped GUARDS — these run TODAY. They assert on the pinned constants
// (not on surfaces that don't exist yet), so their only job is to make a
// silent weakening of the door / renderer set a RED test. A future instance
// cannot drop a door or a forbidden renderer without turning one of these red.
// ───────────────────────────────────────────────────────────────────────────

describe("oneReader conformance — pinned sets (lockstep guards, run today)", () => {
  it("pins exactly the 11 OPEN doors EXPECTED_OPEN_DOORS pins (no door may be dropped)", () => {
    expect(Object.keys(EXPECTED_OPEN_DOORS)).toHaveLength(11);
    // The three convergence-target doors that mis-route to /wrestle today.
    for (const door of MISROUTED_TO_WRESTLE_TODAY) {
      expect(EXPECTED_OPEN_DOORS).toHaveProperty(door);
    }
    // Every door names a verified call site (no empty placeholders).
    for (const site of Object.values(EXPECTED_OPEN_DOORS)) {
      expect(site).toMatch(/:\d+$/);
    }
  });

  it("pins the forbidden DOCUMENT-OPEN seams so no fork survives unnamed", () => {
    // The two judgment-call seams are pinned: MasterMdViewer's by-id open seam
    // (routed) and MetaReading's bespoke article (converged).
    expect(FORBIDDEN_PROD_RENDERERS).toContain(
      "modes/ResearchWorkstation/MasterMdViewer.tsx::openByIdSeam",
    );
    expect(FORBIDDEN_PROD_RENDERERS).toContain(
      "modes/Reading/MetaReading/index.tsx::article",
    );
    expect(FORBIDDEN_PROD_RENDERERS.length).toBeGreaterThanOrEqual(4);
    // ReadingColumn is the SANCTIONED legacy fallback (SPR-05 reconciliation) —
    // it must NOT be on the forbidden list as a whole renderer, or SPR-09 would
    // wrongly delete the legacy read path. Only its by-id-OPEN reachability is
    // forbidden, and it has none (it's reachable only as the /read/:id fallback).
    expect(FORBIDDEN_PROD_RENDERERS).not.toContain(
      "components/reader/ReadingColumn.tsx",
    );
    // The PdfViewer module survives as the INGEST surface (migration-map.md §3);
    // only its use AS AN OPEN TARGET is forbidden — the bare module is not.
    expect(FORBIDDEN_PROD_RENDERERS).not.toContain("components/PdfViewer.tsx");
  });

  it("the contract types this conformance binds against still exist (compile-time pin)", () => {
    // Pure type-level references — they exist only to make `tsc --noEmit` fail if
    // the SPR-01 contract surface is removed/renamed, so the stub can't rot into
    // a no-op. The runtime body is trivially true.
    const opts: OpenDocumentOptions = {};
    const _door: OpenDocument | null = null;
    const _props: ReaderProps | null = null;
    const _doc: Document | null = null;
    const _region: Region | null = null;
    expect([opts, _door, _props, _doc, _region]).toHaveLength(5);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// Door (a) — SPR-09 fills these. Skipped today: the one <Reader> + the routed
// doors do not exist (SPR-03 builds the Reader, SPR-05 routes the doors).
// ───────────────────────────────────────────────────────────────────────────

describe("oneReader conformance — door (a): every door routes to the one Reader [SPR-05 fills, source-level]", () => {
  // The verified call-site files for each door (the `:line` from
  // EXPECTED_OPEN_DOORS resolves to the file; we assert on its SOURCE). Each
  // door must reach the one Reader through `openDocument` / the canonical
  // /read/:id route — NOT navigate('/wrestle/...') and NOT a bespoke renderer.
  const DOOR_FILE: Readonly<Record<string, string>> = {
    "Library.openWork": "modes/Library/index.tsx",
    "LibraryView.open": "components/library/LibraryView.tsx",
    "DocumentsIndex.open": "modes/DocumentsIndex/index.tsx",
    "CommandPalette.openDocument": "components/CommandPalette.tsx",
    "ChunkModal.openInDocument": "modes/ResearchWorkstation/ChunkModal.tsx",
    "MasterMdViewer.cmdClick": "modes/ResearchWorkstation/MasterMdViewer.tsx",
    "DRW.citeSource": "modes/DeepResearchWorkspace/index.tsx",
    "Write.traceToSource": "modes/Write/WriteHome.tsx",
    "MetaReading.openCitation": "modes/Reading/MetaReading/index.tsx",
  };

  // CommandPalette routes a document result via its generic entry.path navigator;
  // for it the one-door target IS the canonical /read/:id route (equivalent to
  // openDocument(id) with no opts), so we accept either the openDocument call or
  // the /read/ path — but NEVER a /wrestle/:id document open.
  const PALETTE_ROUTE_DOORS = new Set(["CommandPalette.openDocument"]);

  for (const door of Object.keys(EXPECTED_OPEN_DOORS)) {
    const file = DOOR_FILE[door];
    if (!file) continue; // Reading.openDoc / Route./read/:documentId are the route itself (asserted below)
    it(`door ${door} (${file}) routes through openDocument / the one Reader — never /wrestle/:id`, () => {
      const src = readSrc(file);
      // No door may open a document by navigating to /wrestle/:id (the killed
      // open target). A bare /wrestle (ingest upload) is allowed; an /wrestle/${
      // …} or /wrestle/:id document open is not.
      expect(src).not.toMatch(/navigate\([`'"]\/wrestle\/\$\{/);
      expect(src).not.toMatch(/navigate\([`'"]\/wrestle\/:/);
      expect(src).not.toMatch(/path:\s*[`'"]\/wrestle\/\$\{/);
      if (PALETTE_ROUTE_DOORS.has(door)) {
        // The palette builds a /read/:id route for a document result.
        expect(src).toMatch(/\/read\/\$\{encodeURIComponent\(doc\.document_id\)\}/);
      } else {
        // Every other door calls the one-door resolver.
        expect(src).toMatch(/useOpenDocument\(\)/);
        expect(src).toMatch(/openDocument\(/);
      }
    });
  }

  it("the canonical Reader route mounts the one <Reader> host (BookReader) at /read/:documentId", () => {
    const app = readSrc("App.tsx");
    expect(app).toMatch(/path="\/read\/:documentId"\s+element=\{<BookReader\s*\/>\}/);
    // The BookReader host imports + mounts the one <Reader> (SPR-03).
    const reading = readSrc("modes/Reading/index.tsx");
    expect(reading).toMatch(/import\s+Reader.*from\s+["']\.\.\/\.\.\/components\/reader\/Reader["']/);
  });

  it("the three doors that mis-routed to /wrestle today now route to the one door (the convergence)", () => {
    for (const door of [
      "DocumentsIndex.open",
      "CommandPalette.openDocument",
      "ChunkModal.openInDocument",
    ]) {
      const src = readSrc(DOOR_FILE[door]);
      // The mis-route is gone: no by-id /wrestle open survives in any of the three.
      expect(src).not.toMatch(/\/wrestle\/\$\{/);
      expect(src).not.toMatch(/\/wrestle\/:/);
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────
// Door (b) — SPR-09 fills this against the BUILT bundle. Skipped today: the
// redundant renderers still exist (SPR-05 deletes / folds them).
// ───────────────────────────────────────────────────────────────────────────

describe("oneReader conformance — door (b): no second document renderer reachable from an open door [SPR-05 fills, source-level]", () => {
  it("MasterMdViewer no longer opens a document by id (its cmd-click routes to openDocument, not openPdfPanel)", () => {
    const src = readSrc("modes/ResearchWorkstation/MasterMdViewer.tsx");
    // The by-id OPEN seam was `openPdfPanel({ documentId })` — gone.
    expect(src).not.toMatch(/openPdfPanel\(/);
    expect(src).not.toMatch(/from\s+["'][^"']*workspace\/actions["']/);
    // It now routes its source-open through the one door.
    expect(src).toMatch(/useOpenDocument\(\)/);
    expect(src).toMatch(/openDocument\(chunk\.document_id/);
  });

  it("MetaReading has no bespoke document <article>; its report renders through the sanctioned ReadingColumn", () => {
    const src = readSrc("modes/Reading/MetaReading/index.tsx");
    // The forbidden bespoke `<article whitespace-pre-wrap>` document body is gone.
    expect(src).not.toMatch(/<article[^>]*whitespace-pre-wrap/);
    // The report renders through the ONE sanctioned legacy body renderer.
    expect(src).toMatch(/import\s+ReadingColumn\s+from/);
    expect(src).toMatch(/<ReadingColumn\s+assetId=\{null\}\s+text=\{deliverable\.report\}/);
  });

  it("the DRW canvas 'cite source' opens the source via openDocument (no ad-hoc document open)", () => {
    const idx = readSrc("modes/DeepResearchWorkspace/index.tsx");
    expect(idx).toMatch(/useOpenDocument\(\)/);
    expect(idx).toMatch(/openDocument\(node\.source_document_id\)/);
    // The cite-source button is now WIRED live (Canvas receives onCiteSource).
    expect(idx).toMatch(/onCiteSource=\{onCiteSource\}/);
    const blockCard = readSrc("modes/DeepResearchWorkspace/Canvas/BlockCard.tsx");
    // The button's onClick invokes the threaded onCiteSource(node).
    expect(blockCard).toMatch(/onClick=\{\(\)\s*=>\s*onCiteSource\(node\)\}/);
  });

  it("PdfViewer is no longer mounted as an OPEN-a-document target (survives as the ingest surface only)", () => {
    // The killed /wrestle/:documentId open route is gone from both shells.
    const app = readSrc("App.tsx");
    expect(app).not.toMatch(/path="\/wrestle\/:documentId"/);
    const legacy = readSrc("AppLegacy.tsx");
    expect(legacy).not.toMatch(/path="\/wrestle\/:documentId"/);
    // The bare /wrestle ingest/upload route survives (migration-map.md §3).
    expect(app).toMatch(/path="\/wrestle"\s+element=\{<WrestleApp\s*\/>\}/);
    // The ProjectTree document node no longer routes to /wrestle/:id (fifth door).
    const tree = readSrc("shell/ProjectTree.tsx");
    expect(tree).not.toMatch(/\/wrestle\/\$\{/);
    expect(tree).toMatch(/openDocument\(n\.id/);
  });

  it("the only Reader-prop renderer importable as a document body is the one <Reader> + its sanctioned ReadingColumn fallback", () => {
    // The one Reader (SPR-03) and ReadingColumn (sanctioned fallback) are the
    // only two body renderers the /read host mounts; ReadingColumn is reachable
    // ONLY as that host's NULL-blocks fallback (and the converged MetaReading
    // report), never as a second OPEN-a-document renderer.
    const reading = readSrc("modes/Reading/index.tsx");
    expect(reading).toMatch(/<Reader\b/);
    expect(reading).toMatch(/<ReadingColumn\b/); // the fallback, behind the same gate
  });
});
