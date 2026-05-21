import { useWorkspace } from "./WorkspaceStore";
import type { PanelMode } from "./panel.types";

/**
 * Cross-mode convenience actions over the workspace store. Wrap common
 * patterns (open a known panel kind with a derived id + title) so
 * callers don't repeat the same `useWorkspace.getState().open(...)`
 * dance everywhere a CTA fires.
 *
 * Each action is a thin wrapper that:
 *   - chooses a stable, deterministic id so re-firing focuses the
 *     existing panel instead of duplicating;
 *   - sets a sensible default mode + title;
 *   - returns the resulting id (or null on miss).
 *
 * Add to this file when a NEW cross-mode CTA appears more than twice.
 * Avoid adding helpers for single-callsite actions — direct
 * useWorkspace().open(...) is fine there.
 */

/** Open the notebook at `notebookId` (or create a new untitled
 *  notebook if absent). Default mode is "floating" so the operator can
 *  drag it aside while continuing to read. S5+ consumers wire this
 *  from MasterMdViewer claim chips, PdfViewer regions, and ClaimCard. */
export function openNotebook(opts: {
  notebookId?: string | null;
  mode?: PanelMode;
  title?: string;
} = {}): string {
  const mode = opts.mode ?? "floating";
  const id = opts.notebookId
    ? `notebook:${opts.notebookId}`
    : "notebook:new";
  return useWorkspace.getState().open(
    "Notebook",
    { notebookId: opts.notebookId ?? null },
    { mode, title: opts.title ?? (opts.notebookId ? "Notebook" : "Untitled notebook"), id },
  );
}

/** Open a PDF region as a floating PDF panel jumped to a page. */
export function openPdfPanel(opts: {
  documentId: string;
  page?: number;
  title?: string;
}): string {
  const id = `pdf:${opts.documentId}${opts.page ? `:p${opts.page}` : ""}`;
  return useWorkspace.getState().open(
    "PdfViewer",
    { documentId: opts.documentId, initialPage: opts.page },
    { mode: "floating", title: opts.title ?? `PDF · ${opts.documentId.slice(-6)}`, id },
  );
}

/** Open a claim in a floating ClaimInspector. */
export function openClaimInspector(opts: {
  claimId: string;
  investigationId: string;
  documentId?: string;
}): string {
  const id = `claim:${opts.claimId}`;
  return useWorkspace.getState().open(
    "ClaimInspector",
    {
      claimId: opts.claimId,
      investigationId: opts.investigationId,
      documentId: opts.documentId,
    },
    { mode: "floating", title: "Claim", id },
  );
}
