// SPR-09 / M6 — Save-As menu for the per-document notebook surface.
//
// Default save target flipped to `.antiek`. PDF + Markdown move to
// the "Export" menu — they are projections, no longer the source of
// truth. The substrate-resident rows are always written; what this
// component picks is the FILE artifact the operator wants alongside
// the rows.
//
// The actual file emission happens server-side: AntiekPersistence in
// services/notebooks/persistence.py writes the .antiek archive next to
// every save. This UI calls the existing /api/notebooks/by-doc save
// endpoint with a save_kind, plus invokes export endpoints for PDF /
// Markdown when the operator picks an alternate format.
//
// What's NOT here:
// - Round-trip Markdown ↔ .antiek. Markdown export is one-way; see
//   services/antiek_format/SPEC.md §8.
// - Federated publish (Sprint 30+). Save-As writes to local disk only.
// - Multi-format simultaneous export. Operator picks one at a time;
//   the chooser is single-select.

import { useCallback, useState } from "react";

import { savePerDocNotebook } from "../../api/notebooks/by-doc";
import type { PerDocNotebookResponse } from "../../api/notebooks/by-doc";

export type SaveAsTarget = "antiek" | "pdf" | "markdown";

interface SaveAsProps {
  documentId: string;
  notebook: PerDocNotebookResponse;
  onSaved?: (next: PerDocNotebookResponse) => void;
  // Optional override hooks for tests / Storybook.
  exportPdf?: (notebookId: string) => Promise<void>;
  exportMarkdown?: (notebookId: string) => Promise<void>;
}

const TARGET_LABELS: Record<SaveAsTarget, string> = {
  antiek: ".antiek (default — signed, lossless)",
  pdf: "PDF (export — lossy projection)",
  markdown: "Markdown (export — universal-fallback, lossy)",
};

export default function SaveAs({
  documentId,
  notebook,
  onSaved,
  exportPdf,
  exportMarkdown,
}: SaveAsProps): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const handle = useCallback(
    async (target: SaveAsTarget) => {
      setBusy(true);
      setStatus(null);
      try {
        if (target === "antiek") {
          // AntiekPersistence on the server writes the .antiek archive
          // alongside the substrate rows on every save. We just call
          // save with save_kind="explicit" to materialise the archive
          // synchronously.
          const updated = await savePerDocNotebook(documentId, {
            notebook_id: notebook.notebook_id,
            content_json: notebook.content_json,
            blocks: notebook.blocks,
            save_kind: "explicit",
          });
          onSaved?.(updated);
          setStatus("Saved .antiek (substrate + signed archive).");
        } else if (target === "pdf") {
          if (!exportPdf) {
            setStatus(
              "PDF export pipeline is the existing Sprint 15 route; wiring " +
                "is in apps/reading/src/api/notebooks/export.ts (lands in " +
                "SPR-09 follow-up).",
            );
            return;
          }
          await exportPdf(notebook.notebook_id);
          setStatus("Exported PDF.");
        } else if (target === "markdown") {
          if (!exportMarkdown) {
            setStatus(
              "Markdown export will call /api/notebooks/by-doc/<doc>/export?" +
                "format=markdown, which proxies to " +
                "services.antiek_format.markdown_projector. " +
                "(SPR-09 follow-up wires the route.)",
            );
            return;
          }
          await exportMarkdown(notebook.notebook_id);
          setStatus("Exported markdown (one-way projection).");
        }
      } catch (err) {
        setStatus(`Save-As failed: ${err instanceof Error ? err.message : String(err)}`);
      } finally {
        setBusy(false);
      }
    },
    [documentId, notebook, onSaved, exportPdf, exportMarkdown],
  );

  return (
    <div className="border border-stone-200 bg-white rounded-md p-3 text-sm space-y-2"
         data-testid="save-as-menu">
      <p className="text-xs uppercase tracking-wider text-stone-500 font-mono">
        Save as
      </p>
      <ul className="space-y-1">
        {(Object.keys(TARGET_LABELS) as SaveAsTarget[]).map((t) => (
          <li key={t}>
            <button
              type="button"
              disabled={busy}
              onClick={() => void handle(t)}
              className="w-full text-left px-2 py-1 rounded hover:bg-stone-100
                         disabled:opacity-50 font-mono text-xs"
              data-testid={`save-as-${t}`}
            >
              {TARGET_LABELS[t]}
            </button>
          </li>
        ))}
      </ul>
      {status && (
        <p className="text-[11px] text-stone-600 italic" data-testid="save-as-status">
          {status}
        </p>
      )}
      <p className="text-[10px] text-stone-400 font-mono">
        Default flipped to .antiek in SPR-09. PDF + Markdown are projections;
        the substrate is the source of truth.
      </p>
    </div>
  );
}
