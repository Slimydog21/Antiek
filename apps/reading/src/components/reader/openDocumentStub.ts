// ─────────────────────────────────────────────────────────────────────────
// openDocument — the SPR-03 STUB resolver (the real one is SPR-05).
//
// SPR-01 pinned the `OpenDocument` type contract in
// `src/lib/openDocument.contract.ts` (types + JSDoc ONLY, no impl). SPR-05
// implements the real resolver (rights/tier gate → mount the one <Reader>) and
// routes every door through it. SPR-03 only needs SOMETHING typed to the
// contract so a citation's onClick has a target to call — so this file ships a
// no-op/console stub that satisfies `OpenDocument` exactly.
//
// This is deliberately NOT routing: it logs the call and is overridable via a
// React context (ReaderProvider), so a test can inject a spy and assert the
// citation invoked it with the right source_document_id + chunkId, and SPR-05
// can later swap the real implementation in at the provider without touching
// any block component (rigor #4: the citation block is decoupled from routing).
// ─────────────────────────────────────────────────────────────────────────

import type {
  OpenDocument,
  OpenDocumentOptions,
} from "../../lib/openDocument.contract";

/**
 * The default stub. Logs the open intent; performs no navigation (SPR-05 owns
 * routing). Typed to `OpenDocument` so the call site is contract-checked today.
 */
export const openDocumentStub: OpenDocument = (
  documentId: string,
  opts?: OpenDocumentOptions,
): void => {
  if (typeof console !== "undefined" && console.info) {
    console.info(
      "[Reader] openDocument (SPR-03 stub — SPR-05 implements routing):",
      documentId,
      opts ?? {},
    );
  }
};
