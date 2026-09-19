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
 *  from MasterMdViewer claim chips, canonical hosted-document regions, and ClaimCard.
 *
 *  Two notebook surfaces exist (see PanelRegistry):
 *    - "Notebook"        substrate-backed block model (legacy on main)
 *    - "NotebookEditor"  TipTap-based, local autosave (S7-full)
 *  The `kind` opt picks which one. Default: NotebookEditor — the
 *  redesign's preferred editor. */
export function openNotebook(opts: {
  notebookId?: string | null;
  mode?: PanelMode;
  title?: string;
  kind?: "Notebook" | "NotebookEditor";
} = {}): string {
  const mode = opts.mode ?? "floating";
  const kind = opts.kind ?? "NotebookEditor";
  const prefix = kind === "NotebookEditor" ? "notebookeditor" : "notebook";
  const id = opts.notebookId
    ? `${prefix}:${opts.notebookId}`
    : `${prefix}:new`;
  return useWorkspace.getState().open(
    kind,
    { notebookId: opts.notebookId ?? null },
    {
      mode,
      title:
        opts.title ?? (opts.notebookId ? "Notebook" : "Untitled notebook"),
      id,
    },
  );
}

/** Open a canonical hosted HTML document; page remains provenance chrome. */
export function openHostedDocumentPanel(opts: {
  documentId: string;
  chunkIds?: string[];
  citationReceiptSha256?: string;
  page?: number;
  title?: string;
}): string {
  const receipt = opts.citationReceiptSha256 && /^[a-f0-9]{64}$/.test(opts.citationReceiptSha256)
    ? `:citation:${opts.citationReceiptSha256}`
    : "";
  const id = `hosted-document:${opts.documentId}${opts.page ? `:p${opts.page}` : ""}${receipt}`;
  return useWorkspace.getState().open(
    "HostedDocument",
    { documentId: opts.documentId, initialPage: opts.page, citationChunkIds: opts.chunkIds ?? [], citationReceiptSha256: receipt ? opts.citationReceiptSha256 : undefined },
    { mode: "floating", title: opts.title ?? `Document · ${opts.documentId.slice(-6)}`, id },
  );
}

/** Open a claim in a floating ClaimInspector. */
export function openClaimInspector(opts: {
  claimId: string;
  investigationId: string;
  documentId?: string;
  claimIndex?: number;
  contentHash?: string;
  sessionGeneration?: number;
}): string {
  const identity = opts.contentHash && Number.isInteger(opts.claimIndex)
    ? `${opts.contentHash}:${opts.claimIndex}`
    : opts.claimId;
  const id = `claim:${opts.sessionGeneration ?? "legacy"}:${identity}`;
  return useWorkspace.getState().open(
    "ClaimInspector",
    {
      claimId: opts.claimId,
      investigationId: opts.investigationId,
      documentId: opts.documentId,
      claimIndex: opts.claimIndex,
      contentHash: opts.contentHash,
    },
    { mode: "floating", title: "Claim", id },
  );
}
