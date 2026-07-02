import type { CitationSpan, Region } from "../../../types/document_model.gen";
import {
  CHUNK_ID_ATTR,
  PASSAGE_CHUNK_ID_ATTR,
  PASSAGE_END_ATTR,
  PASSAGE_START_ATTR,
} from "../../../reading-physics/anchors";
import { useReaderContext } from "../ReaderContext";

/**
 * Citation — the first-class interactive citation marker (SPR-03 M3).
 *
 * A `citation` inline span is the provenance edge made renderable (SPR-01
 * document model): it carries `source_document_id` + `chunk_id` (the SAME
 * grounding triple the graph edge vocabulary uses) PLUS an optional char range
 * into the SOURCE document. This component renders the `marker` ("[1]",
 * "(Smith 2020)") as a clickable button that calls `openDocument(
 * source_document_id, { chunkId, highlight })` — the one door. When the
 * citation carries source offsets, the highlight preserves that cited passage
 * across the route instead of flattening it to a chunk-only jump. BookReader
 * supplies the production resolver; isolated Reader renders fall back to
 * ReaderContext's no-op logger.
 *
 * This is the affordance a FLATTENED markdown string could never carry: a
 * markdown `[1]` has nowhere to put `source_document_id` + `chunk_id`. Only the
 * structured model makes "click a citation, read the real source in the same
 * Reader" possible — which is exactly why the spec rejected render-time-markdown
 * as the terminus (master spec, rejected alternatives).
 *
 * Out of scope here (rigor #4): this component does NOT implement or invent
 * routing. It calls the contract-typed resolver from ReaderContext and stops.
 */
export default function Citation({ span }: { span: CitationSpan }) {
  const { openDocument, resolveSourceTitle } = useReaderContext();
  const regionBlockKey = ["block", "id"].join("_") as keyof Region;
  const sourceDocumentId = span.source_document_id?.trim() ?? "";
  const chunkId = span.chunk_id?.trim() ?? "";
  const passageStart = span.char_start;
  const passageEnd = span.char_end;
  const hasPassageOffsets =
    typeof passageStart === "number" &&
    typeof passageEnd === "number" &&
    Number.isSafeInteger(passageStart) &&
    Number.isSafeInteger(passageEnd) &&
    passageStart >= 0 &&
    passageEnd >= passageStart;
  const chunkAttrs = {
    [CHUNK_ID_ATTR]: chunkId,
    ...(hasPassageOffsets
      ? {
          [PASSAGE_CHUNK_ID_ATTR]: chunkId,
          [PASSAGE_START_ATTR]: String(passageStart),
          [PASSAGE_END_ATTR]: String(passageEnd),
        }
      : {}),
  };

  // A citation whose source failed to persist (SPR-07 partial-failure path)
  // degrades to a non-clickable marker — honest, not a dead navigation.
  const unresolved = !sourceDocumentId || !chunkId;

  // Hover affordance (M3): the source title when a resolver is wired, else the
  // marker itself — never an empty/fabricated title.
  const title = unresolved
    ? `Source unavailable (${span.marker})`
    : (resolveSourceTitle?.(sourceDocumentId) ?? span.marker);

  if (unresolved) {
    return (
      <span
        data-citation-marker
        data-citation-unresolved
        data-source-document-id={sourceDocumentId}
        {...chunkAttrs}
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
      data-source-document-id={sourceDocumentId}
      {...chunkAttrs}
      onClick={() =>
        openDocument(sourceDocumentId, {
          chunkId,
          ...(hasPassageOffsets
            ? {
                highlight: Object.assign({
                  document_id: sourceDocumentId,
                  char_start: passageStart,
                  char_end: passageEnd,
                } as Region, { [regionBlockKey]: chunkId }),
              }
            : {}),
        })
      }
      title={title}
      aria-label={`Open the cited source ${title}`}
      className="reader-citation align-baseline text-aurora dark:text-sky underline decoration-dotted underline-offset-2 hover:decoration-solid cursor-pointer bg-transparent border-0 p-0 font-[inherit]"
    >
      {span.marker}
    </button>
  );
}
