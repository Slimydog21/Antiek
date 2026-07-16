import { useRef } from "react";
import { useNavigate } from "react-router-dom";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import { recordSpawnRelationship } from "../../hooks/useInvestigationTree";
import { startInvestigation, type DistilledNode } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";
import FloatMenu from "../shared/FloatMenu/FloatMenu";
import {
  useFloatMenuSelection,
  type FloatMenuSelection,
  type SelectionProvenance,
} from "../shared/FloatMenu/useFloatMenuSelection";

/**
 * BlockDetail — the SECOND host for the shared {@link FloatMenu} (Living
 * Roadmap SPR-04 M1: prove the SAME component mounts in >1 place). It opens off
 * `BlockCard`'s `onOpenDetail` seam (BlockCard.tsx:26) and shows a graph node's
 * text in a scoped reading surface where a highlight opens the four-action
 * menu — exactly the menu the Research synthesis host mounts, not a fork.
 *
 * Provenance here is RICHER than the synthesis host: a block IS a graph node
 * with a `source_document_id` (DistilledNode.source_document_id), so a NOTE on a
 * block-detail selection chains to that document. (A chunk id isn't resolved
 * from a free selection over the node text, so chunk stays null — honest.)
 *
 * Deep-research reuses the chase path directly (startInvestigation with
 * parent_investigation_id + recordSpawnRelationship — the same calls
 * ChaseSlideOver.tsx:57,64 make), spawning a child investigation linked back to
 * the source highlight.
 */
export default function BlockDetail({
  node,
  investigationId,
  onClose,
}: {
  node: DistilledNode;
  investigationId: string;
  /** Dismiss the detail (the host renders it as an overlay/panel; this closes
   *  it). Optional so a standalone mount still works. */
  onClose?: () => void;
}) {
  const scopeRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // The host resolves provenance: this node's source document grounds any note
  // (§9 chain claim→chunk→document). The selection hook reads the DOM range;
  // the host maps it to graph entities — here, the node's own source document.
  const resolveProvenance = (_range: Range, _text: string): SelectionProvenance => ({
    documentId: node.source_document_id ?? null,
    chunkId: null, // a free selection over node text resolves no single chunk
  });

  const selection = useFloatMenuSelection({ scopeRef, resolveProvenance });

  async function deepResearch(safeSpawnText: string | null) {
    // §9.0: refuse to spawn on a withheld body.
    if (safeSpawnText === null) return;
    // REUSED chase path — child investigation linked to the parent + the
    // selection (ChaseSlideOver.tsx:57,64).
    const resp = await startInvestigation({
      question: safeSpawnText,
      context: safeSpawnText,
      parent_investigation_id: investigationId,
      spawn_context: safeSpawnText,
    });
    recordSpawnRelationship(resp.investigation_id, investigationId);
    // Living-TV: block-detail chase spawn is deep research start.
    emitWernerExperience("deep_research_start");
    navigate(`/inv/${resp.investigation_id}`);
  }

  return (
    <div className="flex flex-col h-full text-ink dark:text-bright p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="block-detail-werner-brand"
            className="h-6 w-6 shrink-0 object-contain"
          />
          {node.kind} · block detail
        </span>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close block detail"
            className="font-mono text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright"
          >
            ✕
          </button>
        )}
      </div>
      {/* The scope container the float-menu narrows to — select text here. */}
      <div ref={scopeRef} className="font-serif text-base leading-relaxed">
        {node.text || <span className="italic text-ink-mute dark:text-moonlight">(empty)</span>}
      </div>
      <FloatMenu
        selection={selection}
        investigationId={investigationId}
        onDeepResearch={(safeSpawnText: string | null, _sel: FloatMenuSelection) =>
          void deepResearch(safeSpawnText)
        }
      />
    </div>
  );
}
