import { useCallback, useMemo, useState } from "react";

import { emitWernerExperience } from "../../werner/reactionBus";
import { getTraceTarget, type OutlineBlockView } from "./writeApi";

/**
 * Xray — the paragraph ↔ blocks provenance view (Write SPR-09 M3).
 *
 * Toggle between (a) the rendered draft and (b) an X-ray that shows, for each
 * paragraph, the blocks that drove it. Click a paragraph → its blocks; click a
 * block → every paragraph using it. The regenerate gesture (drag a block, or the
 * "regenerate" affordance) re-drafts the SECTION the paragraph belongs to: the
 * shipped generate endpoint is section-granular, so the affected paragraph is
 * necessarily refreshed (re-anchored per-block) along with its siblings. A true
 * single-paragraph regenerate is a deferred follow-up (decision doc D-2/D-3).
 * Provenance chains through to chunks → documents (resolve_provenance via the
 * trace endpoint), not just block ids.
 *
 * The data is the PERSISTED `prose_provenance` (paragraph_index → [block_ids])
 * written by SECTION_DRAFT_GENERATED (SPR-09 M3) and read back on the section
 * (GET /deliverables/{id}.prose_provenance). The X-ray reads the SAME map the
 * generation persisted — the link is in the graph, not just on screen.
 *
 * This component is presentation + interaction only; the actual regenerate call
 * is the host's (it owns the section + the generate path), handed in as
 * `onRegenerateParagraph` so the X-ray never forks a second generate path.
 */

export interface XrayProps {
  /** The section's prose. Split into paragraphs by blank line (matching the
   * substrate's `_paragraphs` split). */
  proseText: string;
  /** paragraph_index (string key) → driving block references (persisted). */
  proseProvenance: Record<string, string[]>;
  /** The section's blocks, for resolving a block reference → its display text +
   * provenance kind (a graph-node block's id is its node reference). */
  blocks: OutlineBlockView[];
  /** Hand the host the paragraph the writer acted on (the drag-in-X-ray /
   * regenerate gesture). The host owns the SHIPPED generate path and re-drafts
   * that paragraph's SECTION (section-granular today); the X-ray never forks a
   * second generate path. The index passed is the affected paragraph. */
  onRegenerateParagraph?: (paragraphIndex: number) => void | Promise<void>;
}

/** Split prose into paragraphs the same way the substrate does (blank-line). */
export function splitParagraphs(prose: string): string[] {
  return prose
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}

/** A block reference may be a node reference (graph-node block) or an outline
 * block reference (user-originated). Resolve it to a display label + whether it
 * traces to a source document. */
function blockLabel(blockId: string, blocks: OutlineBlockView[]): {
  label: string;
  outlineBlockId: string | null;
  traceable: boolean;
} {
  // Match on node_id first (the citation id for graph-node blocks), then on
  // outline_block_id (user-originated blocks cite their own outline id).
  const byNode = blocks.find((b) => b.node_id === blockId);
  if (byNode) {
    return {
      label: (byNode.node_label || byNode.content || "(untitled block)").trim(),
      outlineBlockId: byNode.outline_block_id,
      traceable: true, // graph-node → chains to chunk/document
    };
  }
  const byOblk = blocks.find((b) => b.outline_block_id === blockId);
  if (byOblk) {
    return {
      label: (byOblk.content || byOblk.node_label || "(your note)").trim(),
      outlineBlockId: byOblk.outline_block_id,
      traceable: !byOblk.is_user_originated,
    };
  }
  // The block was detached after generation — honest, not invented.
  return { label: "(source no longer attached)", outlineBlockId: null, traceable: false };
}

export default function Xray({
  proseText,
  proseProvenance,
  blocks,
  onRegenerateParagraph,
}: XrayProps) {
  const paragraphs = useMemo(() => splitParagraphs(proseText), [proseText]);
  const [selectedParagraph, setSelectedParagraph] = useState<number | null>(null);
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null);

  const handleRegenerate = useCallback(
    (idx: number) => {
      // Living-TV: rewrite craft is a happy piece_started beat.
      emitWernerExperience("piece_started");
      void onRegenerateParagraph?.(idx);
    },
    [onRegenerateParagraph],
  );
  // The trace chain for the block the user opened (chunk → document).
  const [trace, setTrace] = useState<
    { blockId: string; documentTitle: string | null; detail: string | null } | null
  >(null);

  // block reference → the set of paragraph indices that cite it (the "click a
  // block → every paragraph using it" inversion, complete across the section).
  const blockToParagraphs = useMemo(() => {
    const m = new Map<string, number[]>();
    for (const [k, ids] of Object.entries(proseProvenance)) {
      const idx = Number(k);
      for (const id of ids) {
        const arr = m.get(id) ?? [];
        arr.push(idx);
        m.set(id, arr);
      }
    }
    return m;
  }, [proseProvenance]);

  // Chain a block through to its source chunk/document (resolve_provenance via
  // the trace endpoint) — the X-ray is the visible proof, the chain is real.
  const openTrace = useCallback(
    async (blockId: string) => {
      setSelectedBlock(blockId);
      setSelectedParagraph(null);
      const { outlineBlockId, traceable } = blockLabel(blockId, blocks);
      if (!outlineBlockId || !traceable) {
        setTrace({ blockId, documentTitle: null, detail: "Your own note — traces to your session, not a source." });
        return;
      }
      try {
        const t = await getTraceTarget(outlineBlockId);
        setTrace({
          blockId,
          documentTitle: t.document_title,
          detail: t.full_text_allowed
            ? null
            : t.detail ?? "Source is gated — only its metadata is shown.",
        });
      } catch {
        setTrace({ blockId, documentTitle: null, detail: "Couldn't reach that source right now." });
      }
    },
    [blocks],
  );

  if (paragraphs.length === 0) {
    return (
      <p className="text-xs italic text-ink-mute dark:text-moonlight" data-testid="xray-empty">
        Nothing drafted yet — generate a draft to X-ray its provenance.
      </p>
    );
  }

  return (
    <div data-testid="xray" className="space-y-2">
      <p className="text-[11px] uppercase tracking-wide text-ink-mute dark:text-moonlight">
        X-ray — every paragraph traced to its blocks
      </p>

      {/* The selected block's uses + its source chain (block → paragraphs, and
          block → chunk → document). */}
      {selectedBlock && (
        <div
          data-testid="xray-block-uses"
          className="rounded border border-ocean/50 bg-ocean/5 p-2 text-xs"
        >
          <p className="font-medium text-ink dark:text-bright">
            {blockLabel(selectedBlock, blocks).label}
          </p>
          <p className="text-ink-mute dark:text-moonlight">
            Used in paragraph(s):{" "}
            {(blockToParagraphs.get(selectedBlock) ?? []).map((i) => i + 1).join(", ") || "none"}
          </p>
          {trace?.blockId === selectedBlock && (
            <p className="mt-1 text-ink-soft dark:text-starlight">
              {trace.documentTitle
                ? `Source: ${trace.documentTitle}`
                : trace.detail ?? "Resolving source…"}
            </p>
          )}
          <button
            type="button"
            onClick={() => {
              setSelectedBlock(null);
              setTrace(null);
            }}
            className="mt-1 text-ocean underline"
          >
            clear
          </button>
        </div>
      )}

      <ol className="space-y-2">
        {paragraphs.map((para, idx) => {
          const ids = proseProvenance[String(idx)] ?? [];
          const open = selectedParagraph === idx;
          return (
            <li
              key={idx}
              data-testid={`xray-paragraph-${idx}`}
              className={
                "rounded border p-2 " +
                (open ? "border-ocean ring-1 ring-ocean/40" : "border-rule dark:border-charcoal-1")
              }
            >
              <button
                type="button"
                onClick={() => {
                  setSelectedParagraph(open ? null : idx);
                  setSelectedBlock(null);
                }}
                className="w-full text-left font-serif text-[13px] leading-relaxed text-ink dark:text-bright"
              >
                <span className="mr-1 font-mono text-[10px] text-ink-mute">¶{idx + 1}</span>
                {para}
              </button>

              {/* The paragraph's driving blocks (click paragraph → its blocks). */}
              {open && (
                <div data-testid={`xray-paragraph-blocks-${idx}`} className="mt-1.5 space-y-1">
                  {ids.length === 0 ? (
                    <p className="text-[11px] italic text-emperor">
                      No blocks recorded for this paragraph — unsupported, verify before keeping.
                    </p>
                  ) : (
                    ids.map((bid) => {
                      const { label } = blockLabel(bid, blocks);
                      return (
                        <div key={bid} className="flex items-start gap-2">
                          <button
                            type="button"
                            // Dragging a block re-drafts the SECTION this
                            // paragraph belongs to (M3): the shipped generate
                            // path is section-granular, so the affected paragraph
                            // is refreshed with its siblings. Exposed as a drag
                            // handle + a direct affordance so the gesture is
                            // reachable by both pointer + keyboard.
                            draggable={!!onRegenerateParagraph}
                            onDragEnd={() => handleRegenerate(idx)}
                            onClick={() => void openTrace(bid)}
                            className="flex-1 cursor-grab rounded border-l-2 border-ocean/50 bg-ocean/5 px-2 py-1 text-left text-[12px] text-ink dark:text-bright active:cursor-grabbing"
                            title="Click to trace to source · drag to re-draft this section"
                          >
                            {label}
                          </button>
                        </div>
                      );
                    })
                  )}
                  {onRegenerateParagraph && ids.length > 0 && (
                    <button
                      type="button"
                      onClick={() => handleRegenerate(idx)}
                      className="text-[11px] text-ocean underline"
                    >
                      regenerate this section
                    </button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
