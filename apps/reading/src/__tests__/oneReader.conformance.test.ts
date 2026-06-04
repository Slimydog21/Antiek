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

import { describe, expect, it } from "vitest";

// Load-bearing imports: the real SPR-01 contract types. If the contract is
// deleted or its surface changes, this file fails to compile under `tsc
// --noEmit` — the stub cannot rot into a no-op that quietly passes.
import type { OpenDocument, OpenDocumentOptions, ReaderProps } from "../lib/openDocument.contract";
import type { Document, Region } from "../types/document_model.gen";

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
 * The renderers SPR-05 deletes / folds into the one `<Reader>`. SPR-09 asserts
 * NONE is importable in the production bundle (a forbidden-import check on the
 * built bundle). MIRRORS FORBIDDEN_PROD_RENDERERS in test_reader_conformance.py.
 * `PdfViewer` / `WrestleApp` are DELIBERATELY ABSENT — they survive behind the
 * ingest entry point (migration-map.md §3), never as an open-a-document
 * renderer.
 */
export const FORBIDDEN_PROD_RENDERERS: readonly string[] = [
  "components/reader/ReadingColumn.tsx::renderBlocks", // the 24-line flattener (:62)
  "modes/ResearchWorkstation/MasterMdViewer.tsx", // cannot open by id
  "modes/Reading/MetaReading/index.tsx::article", // bespoke <article> (:251)
  "modes/DeepResearchWorkspace/index.tsx::canvasTextDiv", // ad-hoc text div (actual: BlockDetail.tsx:87 — see map §5)
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

  it("pins the forbidden-renderer set so no fork survives unnamed", () => {
    expect(FORBIDDEN_PROD_RENDERERS).toContain(
      "components/reader/ReadingColumn.tsx::renderBlocks",
    );
    expect(FORBIDDEN_PROD_RENDERERS).toContain(
      "modes/ResearchWorkstation/MasterMdViewer.tsx",
    );
    expect(FORBIDDEN_PROD_RENDERERS.length).toBeGreaterThanOrEqual(4);
    // PdfViewer survives as INGEST (migration-map.md §3) — it must NOT be on the
    // forbidden-renderer list, or SPR-09 would wrongly delete the ingest surface.
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

describe.skip("oneReader conformance — door (a): every door routes to the one Reader [SPR-09 fills]", () => {
  for (const [door, site] of Object.entries(EXPECTED_OPEN_DOORS)) {
    // SPR-09: parse `site` and assert the call site invokes
    // openDocument(documentId, opts) — NOT navigate('/wrestle/...'), NOT a
    // bespoke renderer mount. Unblocked by SPR-05 (routing) + SPR-03 (Reader).
    it.skip(
      `door ${door} (${site}) routes through openDocument → the one <Reader> [unblocked by SPR-05]`,
      () => {
        throw new Error(
          `SPR-09: assert the call site at ${site} invokes openDocument(documentId, ...). ` +
            `Unblocked by SPR-05 (routing) + SPR-03 (the <Reader>).`,
        );
      },
    );
  }

  it.skip(
    "the three doors that mis-route to /wrestle today now route to openDocument [unblocked by SPR-05]",
    () => {
      // SPR-09: assert DocumentsIndex.open / CommandPalette.openDocument /
      // ChunkModal.openInDocument no longer navigate('/wrestle/:id') — they call
      // openDocument(documentId, opts). This is the convergence the one-door
      // work exists to land.
      throw new Error("SPR-09 asserts the convergence; unblocked by SPR-05");
    },
  );
});

// ───────────────────────────────────────────────────────────────────────────
// Door (b) — SPR-09 fills this against the BUILT bundle. Skipped today: the
// redundant renderers still exist (SPR-05 deletes / folds them).
// ───────────────────────────────────────────────────────────────────────────

describe.skip("oneReader conformance — door (b): no second document renderer in the prod bundle [SPR-09 fills]", () => {
  it.skip(
    "the production bundle imports none of FORBIDDEN_PROD_RENDERERS [unblocked by SPR-05]",
    () => {
      // SPR-09: build the prod bundle and assert it imports none of
      // FORBIDDEN_PROD_RENDERERS (a forbidden-import check; mirrors the Python
      // bundle assertion). PdfViewer/WrestleApp are exempt — they are the ingest
      // surface (migration-map.md §3), reachable ONLY behind the /wrestle door.
      // Unblocked by SPR-05 (deletes/folds the redundant renderers).
      throw new Error(
        `SPR-09: assert the built bundle imports none of [${FORBIDDEN_PROD_RENDERERS.join(", ")}]. ` +
          `Unblocked by SPR-05.`,
      );
    },
  );

  it.skip(
    "exactly one document renderer (<Reader>) is reachable from the open doors [unblocked by SPR-03+SPR-05]",
    () => {
      // SPR-09: assert the only renderer any EXPECTED_OPEN_DOORS path mounts is
      // the one <Reader>. Unblocked by SPR-03 (the Reader) + SPR-05 (routing).
      throw new Error("SPR-09 asserts single-renderer reachability; unblocked by SPR-03+SPR-05");
    },
  );
});
