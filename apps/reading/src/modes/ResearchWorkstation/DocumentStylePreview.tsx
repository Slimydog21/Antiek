import { useEffect, useId, useRef, useState } from "react";

import {
  listStyles,
  renderDocument,
  type ProjectionStyle,
  type RenderedDocument,
} from "../../api/styles";
import LemonTag from "../../components/lemon/LemonTag";
import StyleRail from "./StyleRail";
import "./StyleWheel.css";

export interface DocumentStylePreviewProps {
  documentId: string;
  initialStyle?: string | null;
}

/**
 * The reasons `GET /documents/{id}/render` refuses a body, in the reader's
 * words. The API answers with the serve gate's own reason as `detail`; an
 * honest state names it rather than laundering it into "unavailable".
 */
const REFUSAL_COPY: Record<string, string> = {
  no_reader_html:
    "This document has no reader HTML yet — it was ingested as text only, so there is nothing to project.",
  sanitizer_version_stale:
    "This document's reader HTML was sanitized under an older sanitizer version and is held back until an operator re-sanitizes it (tools/resanitize_reader_html.py).",
  rights_denied: "Rights do not release this document's body, so it cannot be projected.",
  taken_down: "This document has been taken down.",
  document_not_found: "This document is not in the substrate.",
};

function messageOf(error: unknown): string {
  const raw = error instanceof Error ? error.message : "The style service is unavailable.";
  return REFUSAL_COPY[raw] ?? raw;
}

/**
 * Preview-only wheel for an INGESTED document. Reuses the artifact rail and
 * deliberately has no Apply and no receipt chain: a document has no version
 * history the way a research artifact does, so every render is a side-effect
 * free projection of the reader sidecar, and switching style re-projects the
 * same bytes (the API's `X-Content-SHA256` is the proof, shown under the
 * preview).
 */
export default function DocumentStylePreview({ documentId, initialStyle }: DocumentStylePreviewProps) {
  const [styles, setStyles] = useState<ProjectionStyle[]>([]);
  const [selected, setSelected] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable" | "empty">("loading");
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [receipt, setReceipt] = useState<RenderedDocument | null>(null);
  const previewRun = useRef(0);
  const previewUrlRef = useRef<string | null>(null);
  const headingId = useId();

  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    void (async () => {
      try {
        const loaded = await listStyles(controller.signal);
        if (controller.signal.aborted) return;
        setStyles(loaded);
        if (!loaded.length) {
          setSelected("");
          setStatus("empty");
          setError("No styles are available for this document.");
          return;
        }
        const requested = loaded.find((style) => style.name === initialStyle) ?? loaded[0];
        setSelected(requested?.name ?? "");
        setStatus("ready");
      } catch (cause) {
        if (controller.signal.aborted) return;
        setStatus("unavailable");
        setError(messageOf(cause));
      }
    })();
    return () => controller.abort();
  }, [documentId, initialStyle]);

  useEffect(() => () => {
    previewRun.current += 1;
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  useEffect(() => {
    if (!selected || status !== "ready") return;
    const controller = new AbortController();
    const run = ++previewRun.current;
    setPreviewing(true);
    setError(null);
    renderDocument(documentId, selected, controller.signal)
      .then((rendered) => {
        if (run !== previewRun.current) return;
        const next = URL.createObjectURL(rendered.html);
        if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = next;
        setPreviewUrl(next);
        setReceipt(rendered);
      })
      .catch((cause) => {
        if (!controller.signal.aborted && run === previewRun.current) {
          setPreviewUrl(null);
          setReceipt(null);
          setError(messageOf(cause));
        }
      })
      .finally(() => {
        if (run === previewRun.current) setPreviewing(false);
      });
    return () => controller.abort();
  }, [documentId, selected, status]);

  if (status === "loading") {
    return (
      <p className="style-wheel__state" role="status">
        Loading style wheel…
      </p>
    );
  }

  if (status === "unavailable") {
    return (
      <p className="style-wheel__state style-wheel__state--error" role="alert">
        Styles unavailable · {error}
      </p>
    );
  }

  const active = styles.find((style) => style.name === selected);

  return (
    <section
      className="style-wheel"
      aria-labelledby={headingId}
      data-testid="document-style-preview"
    >
      <div className="style-wheel__header">
        <div>
          <p className="style-wheel__eyebrow">Ingested document</p>
          <h3 id={headingId}>Preview it in a reading style</h3>
        </div>
      </div>

      {status === "empty" ? (
        <div className="style-wheel__empty" role="status">
          <p>
            <strong>Empty wheel.</strong> No builtins or forks loaded for this session.
          </p>
          <p className="style-wheel__empty-hint">
            The style service returned an empty list. Fork a style from a research artifact to put
            something on the rail, or check that the projection styles package is registered.
          </p>
        </div>
      ) : (
        <StyleRail
          styles={styles}
          selected={selected}
          onSelect={setSelected}
          ariaLabel="Document styles"
        />
      )}

      {active ? (
        <div className="style-wheel__active-meta">
          <p className="style-wheel__description">
            <strong>{active.label}.</strong>{" "}
            {active.description || "No description provided."}
          </p>
          <div className="style-wheel__chips" aria-label="Style provenance">
            <LemonTag colour={active.builtin ? "sun" : "default"} dot>
              {active.builtin ? "builtin" : "fork"}
            </LemonTag>
            {active.source_fidelity ? (
              <LemonTag colour="default">source-first</LemonTag>
            ) : (
              <LemonTag colour="muted">house chrome</LemonTag>
            )}
            <span className="style-wheel__slug" title="Style slug">
              {active.name}
            </span>
          </div>
        </div>
      ) : null}

      {error ? (
        <p className="style-wheel__error" role="alert">
          {error}
        </p>
      ) : null}

      {status === "ready" ? (
        <>
          <div className="style-wheel__preview-shell" aria-busy={previewing}>
            {previewUrl ? (
              <iframe
                title={`${active?.label ?? "Style"} document preview`}
                sandbox=""
                src={previewUrl}
              />
            ) : (
              <p>
                {previewing
                  ? "Projecting the document…"
                  : "Preview unavailable for this document."}
              </p>
            )}
          </div>
          <div className="style-wheel__actions">
            <span>
              Preview only. A document has no version chain to apply a style to; each pick
              re-projects the same reader bytes.
            </span>
            {receipt ? (
              <span className="style-wheel__slug" title={receipt.hash} data-testid="document-render-receipt">
                sha256 {receipt.hash.slice(0, 12)}…
                {receipt.readerRevision ? ` · reader rev ${receipt.readerRevision}` : ""}
              </span>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
