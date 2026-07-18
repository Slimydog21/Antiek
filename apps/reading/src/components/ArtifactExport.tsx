import { useState } from "react";

import { API_BASE, apiFetch } from "../lib/api";
import { emitWernerExperience } from "../werner/reactionBus";

/**
 * The export formats, presented with EQUAL prominence + neutral copy (SPR-08
 * M4). A file-biased offer (pushing `.antiek` over the plain HTML view) would
 * manufacture exactly the demand signal the form-factor gate measures, so the
 * order is fixed and the labels are plain — no "✨ new format ✨".
 */
export const ARTIFACT_EXPORT_FORMATS = [
  { id: "html", label: "HTML", ext: "html" },
  { id: "antiek", label: ".antiek", ext: "antiek" },
  { id: "antiek_html", label: ".antiek.html", ext: "antiek.html" },
] as const;

export interface ArtifactExportProps {
  /** API path to the artifact resource, e.g. `/api/syntheses/abc`. The
   * component appends `/artifact?format=…`. */
  basePath: string;
  /** Download filename stem, e.g. `synthesis-abc`; the format ext is appended. */
  filenamePrefix: string;
  /** Optional leading label; defaults to "Export:". */
  label?: string;
}

/**
 * The ONE artifact-export affordance. All three surfaces (Research / Read /
 * Write) render THIS — never a private copy — so the neutrality rule lives in a
 * single place. The rights filter is enforced server-side (a 403 with a reason
 * on a source-level restriction); this surfaces that SPECIFIC reason verbatim,
 * never a generic error.
 */
export function ArtifactExport({
  basePath,
  filenamePrefix,
  label = "Export:",
}: ArtifactExportProps) {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function doExport(format: string, ext: string): Promise<void> {
    if (exporting) return;
    setExporting(true);
    setError(null);
    try {
      const resp = await apiFetch(
        `${API_BASE}${basePath}/artifact?format=${encodeURIComponent(format)}`,
      );
      if (resp.status === 403) {
        const body = (await resp.json().catch(() => null)) as
          | { reason?: string }
          | null;
        setError(body?.reason ?? "Export refused under the source's rights.");
        emitWernerExperience("fail");
        return;
      }
      if (!resp.ok) {
        setError(`Export failed (HTTP ${resp.status}).`);
        emitWernerExperience("fail");
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${filenamePrefix}.${ext}`;
      anchor.click();
      URL.revokeObjectURL(url);
      // Living-TV: HTML-first artifact export — happy craft (HTML vision).
      emitWernerExperience("piece_started");
    } catch {
      setError("Export failed — the server could not be reached.");
      emitWernerExperience("fail");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="text-xs font-mono text-shadow-1 dark:text-moonlight">
      <span className="mr-1">{label}</span>
      {ARTIFACT_EXPORT_FORMATS.map((f, i) => (
        <button
          key={f.id}
          type="button"
          disabled={exporting}
          onClick={() => void doExport(f.id, f.ext)}
          className={`${i > 0 ? "ml-3 " : ""}underline decoration-dotted underline-offset-2 hover:text-ink dark:hover:text-bright disabled:opacity-50`}
        >
          {exporting ? "…" : f.label}
        </button>
      ))}
      {error && (
        <p className="mt-1 text-amber-700 dark:text-amber-400">
          Export refused: {error}
        </p>
      )}
    </div>
  );
}
