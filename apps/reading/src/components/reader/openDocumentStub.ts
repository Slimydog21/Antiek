// ─────────────────────────────────────────────────────────────────────────
// openDocument — fallback resolver for standalone Reader renders.
//
// SPR-01 pinned the `OpenDocument` type contract in
// `src/lib/openDocument.contract.ts` (types + JSDoc ONLY, no impl). The real
// resolver now lives at `src/lib/openDocument.ts` and routes production doors
// through `/read/:documentId`, where BookReader owns the rights/tier gate.
// This file remains only as the context default for isolated Storybook/unit
// renders that mount <Reader> without the app router.
//
// This is deliberately NOT routing: it logs the call and is overridable via a
// React context (ReaderProvider), so a test can inject a spy and assert the
// citation invoked it with the right source_document_id + chunkId, while
// production hosts supply the real implementation without touching any block
// component (rigor #4: the citation block is decoupled from routing).
// ─────────────────────────────────────────────────────────────────────────

import type {
  OpenDocument,
  OpenDocumentOptions,
} from "../../lib/openDocument.contract";

/**
 * The default fallback. Logs the open intent; performs no navigation. Typed to
 * `OpenDocument` so standalone Reader call sites stay contract-checked.
 */
export const openDocumentStub: OpenDocument = (
  documentId: string,
  opts?: OpenDocumentOptions,
): void => {
  if (typeof console !== "undefined" && console.info) {
    console.info(
      "[Reader] openDocument fallback: no app resolver supplied:",
      documentId,
      opts ?? {},
    );
  }
};
