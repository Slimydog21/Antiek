/**
 * BlockCard — one card per insight / open-question graph node, the atomic
 * unit of the DRW "organism" canvas (Living Roadmap SPR-03 M1).
 *
 * It is PRESENTATIONAL and graph-driven: it renders a `DistilledNode` read off
 * the graph via `getDistillation` (apps/reading/src/lib/api.ts) and nothing
 * else. It owns no fetch, no store, no position math — the canvas places it
 * absolutely and feeds it props. That keeps it reusable in Write (SPR-09
 * X-ray) and Read later, exactly as the spec asks.
 *
 * Kind distinction (acceptance criterion): an INSIGHT and a QUESTION are
 * visually distinct — a colored left bar + a kind label + a tinted background.
 * We clone the *idiom* from Notebook's ClaimCardBlock / QuestionCardBlock
 * (the colored left-bar + an Inspect/cite affordance) but NOT their TipTap
 * NodeViews — a canvas block is a different concept (a free-floating graph
 * node, not an inline editor node). The colors match DistillView's section
 * dots: aurora for insights, sun-deep for questions.
 *
 * Provenance (§9, acceptance criterion): every block surfaces a source
 * affordance. When the node carries a `source_document_id` we render a
 * "cite source" button (mirroring ClaimCardBlock's "Inspect"); when it does
 * not, we say "no source on record" honestly rather than hide the chain.
 * A raw document id is NEVER rendered as a label (copy-lint discipline).
 *
 * Click-to-detail (acceptance criterion + SPR-04 seam): clicking the card
 * body calls `onOpenDetail(node)`. That is the seam SPR-04 anchors its
 * highlight→float-menu on; we do NOT build the float-menu here (it is OUT
 * of scope — SPR-04 owns {Note·Dialogue·Search·Deep-research}).
 */

import type { DistilledNode } from "../../../lib/api";
import { emitWernerExperience } from "../../../werner/reactionBus";

export interface BlockCardProps {
  node: DistilledNode;
  /** Click-to-detail seam for SPR-04. Optional — when absent the card is
   *  inert (renders, but opens nothing). */
  onOpenDetail?: (node: DistilledNode) => void;
  /** Cite-source / inspect-provenance affordance. Optional — when absent we
   *  still show the source's *presence* (or absence) honestly, just without a
   *  click target. */
  onCiteSource?: (node: DistilledNode) => void;
}

const KIND_STYLE = {
  insight: {
    bar: "border-aurora",
    bg: "bg-aurora/10 dark:bg-aurora/15",
    label: "text-aurora",
    text: "insight",
  },
  question: {
    bar: "border-sun-deep dark:border-sun",
    bg: "bg-sun/10 dark:bg-sun/15",
    label: "text-sun-deep dark:text-sun",
    text: "question",
  },
} as const;

function styleFor(kind: string) {
  // The §2.1 primitive is "insight" | "question"; anything else is an
  // unexpected graph kind — render it like a question (the open/neutral
  // styling) rather than crash, and keep the raw kind visible so the
  // anomaly is honest rather than silently coerced.
  return kind === "insight" ? KIND_STYLE.insight : KIND_STYLE.question;
}

export default function BlockCard({ node, onOpenDetail, onCiteSource }: BlockCardProps) {
  const s = styleFor(node.kind);
  const hasSource = Boolean(node.source_document_id);
  const clickable = Boolean(onOpenDetail);

  return (
    <div
      data-block-card={node.kind}
      data-node-id={node.node_id}
      className={
        `flex flex-col gap-1.5 rounded-r border-l-edge ${s.bar} ${s.bg} ` +
        "py-2 pl-3 pr-3 shadow-z1 dark:shadow-z1-night"
      }
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`font-mono text-[10px] uppercase tracking-wider ${s.label}`}>
          {/* Show the real kind so an unexpected graph kind is visible, not
              silently relabeled. */}
          {node.kind === "insight" || node.kind === "question" ? s.text : node.kind}
        </span>
        {node.escalated && (
          <span className="font-mono text-[10px] text-sun-deep dark:text-sun" title="this needs more research">
            needs more research
          </span>
        )}
      </div>

      {/* Card body — the click-to-detail target (SPR-04 seam). A button so
          it's keyboard-reachable; falls back to a plain div when inert. */}
      {clickable ? (
        <button
          type="button"
          onClick={() => { emitWernerExperience("highlight"); onOpenDetail?.(node); }}
          className="text-left"
          aria-label="Open block detail"
        >
          <p className="line-clamp-4 font-serif text-[13px] leading-relaxed text-ink dark:text-bright">
            {node.text || <span className="italic text-ink-mute dark:text-moonlight">(empty)</span>}
          </p>
        </button>
      ) : (
        <p className="line-clamp-4 font-serif text-[13px] leading-relaxed text-ink dark:text-bright">
          {node.text || <span className="italic text-ink-mute dark:text-moonlight">(empty)</span>}
        </p>
      )}

      {/* Provenance affordance — the §9 chain stays reachable. We surface the
          source's presence/absence in human terms; a raw id is never a label. */}
      <div className="flex items-center gap-2 text-[10px] text-shadow-1 dark:text-moonlight">
        {hasSource ? (
          onCiteSource ? (
            <button
              type="button"
              onClick={() => { emitWernerExperience("highlight"); onCiteSource(node); }}
              className="font-mono underline decoration-dotted underline-offset-2 hover:text-ink dark:hover:text-bright"
            >
              cite source
            </button>
          ) : (
            <span className="font-mono">grounded in a source</span>
          )
        ) : (
          <span className="font-mono italic">no source on record</span>
        )}
        {node.refinement_count > 0 && (
          <span className="font-mono">
            changed {node.refinement_count === 1 ? "once" : `${node.refinement_count} times`}
          </span>
        )}
      </div>
    </div>
  );
}
