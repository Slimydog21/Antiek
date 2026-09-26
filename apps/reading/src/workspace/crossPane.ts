/**
 * crossPane.ts — the C4→C5 seam: an agent in the companion (right pane)
 * opens a document in the LEFT pane.
 *
 * THE CONTRACT IS THE EVENT SHAPE, not the handler. For cockpit PR 2 the
 * handler bridges to today's behavior: open/focus the reader window via
 * openWindow with the stable per-document id (`win:reader:<documentId>` —
 * re-opening focuses, never duplicates, per windowsStore). PR 3 (the left
 * tab strip over tabTree) REPLACES the handler through
 * setOpenDocumentHandler; every caller — this pane, future agent kinds —
 * is untouched.
 */
import { openWindow } from "../components/windows/openWindow";

export interface OpenDocumentOrigin {
  /** Where the request was born (e.g. "companion"). Metadata only. */
  from: string;
  investigationId?: string;
  agentTabId?: string;
}

export interface OpenDocumentRequest {
  documentId: string;
  origin: OpenDocumentOrigin;
}

/** The PR-2 bridge: today's behavior. One reader window per document. */
function bridgeToReaderWindow(req: OpenDocumentRequest): void {
  openWindow(
    "reader",
    { documentId: req.documentId },
    { id: `win:reader:${encodeURIComponent(req.documentId)}` },
  );
}

let handler: (req: OpenDocumentRequest) => void = bridgeToReaderWindow;

/** PR 3's seam: swap the handler (null restores the bridge). Callers never
 *  change — they speak `openDocumentInLeftPane`, not windows or tab trees. */
export function setOpenDocumentHandler(
  next: ((req: OpenDocumentRequest) => void) | null,
): void {
  handler = next ?? bridgeToReaderWindow;
}

/** Open (focus) a document in the left pane. An empty identity is an honest
 *  no-op: no id, no window, never a guessed target. */
export function openDocumentInLeftPane(
  documentId: string,
  origin: OpenDocumentOrigin,
): void {
  if (!documentId.trim()) return;
  handler({ documentId, origin });
}
