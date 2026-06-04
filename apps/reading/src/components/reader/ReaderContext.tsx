import { createContext, useContext } from "react";

import type { OpenDocument } from "../../lib/openDocument.contract";
import { openDocumentStub } from "./openDocumentStub";

/**
 * ReaderContext — the seam the one <Reader> threads its `openDocument` resolver
 * through to deep children (notably the first-class Citation span, SPR-03 M3).
 *
 * Why a context and not a prop drilled through every block: a citation can be
 * nested arbitrarily deep (a citation inside a table cell inside a list item),
 * and threading a callback through nine block components by hand re-introduces
 * the coupling this sprint is trying to delete. The context decouples the
 * citation block from routing entirely:
 *
 *  - SPR-03 (now): the default is `openDocumentStub` (console no-op) — a
 *    citation is fully clickable and a test injects a spy via the provider to
 *    assert it fired with the right source_document_id + chunkId.
 *  - SPR-05 (later): the real `openDocument` (rights/tier gate → mount the
 *    Reader) is supplied at the provider with ZERO change to any block
 *    component. The seam is already the right shape.
 */
export interface ReaderContextValue {
  /** Resolve + open a document. SPR-03 stub; SPR-05 real (rights/tier gate). */
  openDocument: OpenDocument;
  /** Resolve a citation's source title for the hover affordance (M3). Optional;
   *  SPR-03 has no title resolver, so the marker is the fallback hover text. */
  resolveSourceTitle?: (sourceDocumentId: string) => string | undefined;
}

const ReaderContext = createContext<ReaderContextValue>({
  openDocument: openDocumentStub,
});

export function ReaderProvider({
  value,
  children,
}: {
  value: ReaderContextValue;
  children: React.ReactNode;
}) {
  return <ReaderContext.Provider value={value}>{children}</ReaderContext.Provider>;
}

export function useReaderContext(): ReaderContextValue {
  return useContext(ReaderContext);
}

export default ReaderContext;
