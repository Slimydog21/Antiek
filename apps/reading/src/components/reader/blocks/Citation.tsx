import type { CitationSpan } from "../../../types/document_model.gen";
import { useReaderContext } from "../ReaderContext";

/**
 * Citation — the first-class interactive citation marker (SPR-03 M3).
 *
 * A `citation` inline span is the provenance edge made renderable (SPR-01
 * document model): it carries `source_document_id` + `chunk_id` (the SAME
 * grounding triple the graph edge vocabulary uses) PLUS an optional char range
 * into the SOURCE document. This component renders the `marker` ("[1]",
 * "(Smith 2020)") as a clickable button that calls `openDocument(
 * source_document_id, { chunkId })` — the one door (SPR-05 implements the
 * resolver; here it is the SPR-03 stub via ReaderContext).
 *
 * This is the affordance a FLATTENED markdown string could never carry: a
 * markdown `[1]` has nowhere to put `source_document_id` + `chunk_id`. Only the
 * structured model makes "click a citation, read the real source in the same
 * Reader" possible — which is exactly why the spec rejected render-time-markdown
 * as the terminus (master spec, rejected alternatives).
 *
 * Out of scope here (rigor #4): this component does NOT implement or invent
 * routing. It calls the contract-typed resolver from ReaderContext and stops.
 * SPR-05 supplies the real `openDocument`.
 */
export default function Citation({ span }: { span: CitationSpan }) {
  const { openDocument, resolveSourceTitle } = useReaderContext();

  // A citation whose source failed to persist (SPR-07 partial-failure path)
  // degrades to a non-clickable marker — honest, not a dead navigation.
  const unresolved =
    !span.source_document_id?.trim() || !span.chunk_id?.trim();

  // Hover affordance (M3): the source title when a resolver is wired, else the
  // marker itself — never an empty/fabricated title.
  const title = unresolved
    ? `Source unavailable (${span.marker})`
    : (resolveSourceTitle?.(span.source_document_id) ?? span.marker);

  if (unresolved) {
    return (
      <span
        data-citation-marker
        data-citation-unresolved
        data-source-document-id={span.source_document_id || ""}
        data-chunk-id={span.chunk_id || ""}
        title={title}
        aria-label={title}
        className="reader-citation align-baseline text-shadow-1 dark:text-moonlight decoration-dotted underline-offset-2 cursor-not-allowed"
      >
        {span.marker}
      </span>
    );
  }

  return (
    <button
      type="button"
      // The provenance triple is exposed as data attributes so a deep-link /
      // test can locate the marker and read its target without reaching into
      // React internals (mirrors the data-akb-* marker discipline elsewhere).
      data-citation-marker
      data-source-document-id={span.source_document_id}
      data-chunk-id={span.chunk_id}
      onClick={() =>
        openDocument(span.source_document_id, { chunkId: span.chunk_id })
      }
      title={title}
      aria-label={`Open the cited source ${title}`}
      className="reader-citation align-baseline text-aurora dark:text-sky underline decoration-dotted underline-offset-2 hover:decoration-solid cursor-pointer bg-transparent border-0 p-0 font-[inherit]"
    >
      {span.marker}
    </button>
  );
}
