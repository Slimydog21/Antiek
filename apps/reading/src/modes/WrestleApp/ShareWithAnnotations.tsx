// SPR-10 / M5 — Share-with-annotations button + flow.
//
// One affordance, three states:
//   - idle     → "Share with annotations" button
//   - working  → spinner + "Building bundle…"
//   - done     → "Downloaded N highlights + M voice notes" (toast-ish
//                inline; auto-clears after 5s)
//   - error    → error message; user can retry
//
// We deliberately do NOT integrate with a global toast surface — the
// SPR-08 NotesPanel + SPR-09 ResearchWorkstation both still use
// inline status text; adding a toast here would be inconsistent.

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ShareBundleError,
  downloadShareBundle,
  type ShareBundleMetadata,
} from "../../../api/library/share-bundle";

type State =
  | { kind: "idle" }
  | { kind: "working" }
  | { kind: "done"; metadata: ShareBundleMetadata }
  | { kind: "error"; message: string };


export interface ShareWithAnnotationsProps {
  documentId: string;
  userId: string;
  /** Optional filename hint passed to the backend. Defaults to the
   *  PDF title slug on the server side. */
  filenameHint?: string;
  /** Render label on the button. Defaults to "Share with annotations". */
  label?: string;
  /** Optional callback fired after a successful download — used by
   *  parent components to log telemetry / refresh state. */
  onShared?: (metadata: ShareBundleMetadata) => void;
}


export default function ShareWithAnnotations(
  props: ShareWithAnnotationsProps,
) {
  const { documentId, userId, filenameHint, label, onShared } = props;
  const [state, setState] = useState<State>({ kind: "idle" });
  const objectUrlRef = useRef<string | null>(null);

  // Auto-clear "done" state after 5s so the button returns to idle
  // and the user can share again. Errors stick around — they need
  // explicit dismissal so the user notices.
  useEffect(() => {
    if (state.kind === "done") {
      const t = window.setTimeout(() => setState({ kind: "idle" }), 5000);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [state]);

  // Revoke the object URL when we unmount so we don't leak blobs.
  useEffect(() => {
    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
      }
    };
  }, []);

  const onClick = useCallback(async () => {
    setState({ kind: "working" });
    try {
      const { metadata, objectUrl } = await downloadShareBundle({
        document_id: documentId,
        user_id: userId,
        filename_hint: filenameHint,
      });
      // Revoke the previous object URL if any (re-sharing the same doc).
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
      }
      objectUrlRef.current = objectUrl;
      setState({ kind: "done", metadata });
      onShared?.(metadata);
    } catch (err) {
      const message = err instanceof ShareBundleError
        ? `${err.code} (HTTP ${err.status})`
        : err instanceof Error
          ? err.message
          : String(err);
      setState({ kind: "error", message });
    }
  }, [documentId, userId, filenameHint, onShared]);

  const buttonLabel = label ?? "Share with annotations";

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onClick}
        disabled={state.kind === "working"}
        aria-busy={state.kind === "working"}
        className={
          "text-xs px-3 py-1.5 rounded-md transition-colors " +
          (state.kind === "working"
            ? "bg-stone-300 text-stone-600 cursor-wait"
            : "bg-stone-900 text-white hover:bg-stone-700 cursor-pointer")
        }
      >
        {state.kind === "working" ? "Building bundle…" : buttonLabel}
      </button>

      {state.kind === "done" && (
        <span className="text-xs font-mono text-emerald-700" role="status">
          Downloaded{" "}
          {summarise(state.metadata)}
        </span>
      )}

      {state.kind === "error" && (
        <span className="text-xs font-mono text-red-700" role="alert">
          Share failed: {state.message}
          <button
            type="button"
            onClick={() => setState({ kind: "idle" })}
            className="ml-2 underline"
          >
            dismiss
          </button>
        </span>
      )}
    </div>
  );
}


function summarise(metadata: ShareBundleMetadata): string {
  const parts: string[] = [];
  if (metadata.highlights_included) {
    parts.push(`${metadata.highlights_included} highlight${metadata.highlights_included === 1 ? "" : "s"}`);
  }
  if (metadata.voice_notes_included) {
    parts.push(`${metadata.voice_notes_included} voice note${metadata.voice_notes_included === 1 ? "" : "s"}`);
  }
  if (metadata.user_asserted_edges_included) {
    parts.push(`${metadata.user_asserted_edges_included} edge${metadata.user_asserted_edges_included === 1 ? "" : "s"}`);
  }
  if (!parts.length) {
    return "bundle (no annotations to include)";
  }
  return parts.join(" + ");
}
