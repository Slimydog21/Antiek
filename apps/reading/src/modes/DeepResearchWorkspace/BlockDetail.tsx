import { useRef } from "react";
import { useNavigate } from "react-router-dom";

import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import { recordSpawnRelationship } from "../../hooks/useInvestigationTree";
import { startInvestigation, type DistilledNode } from "../../lib/api";
import { useSettingsResearchTier } from "../../lib/useSettingsResearchTier";
import FloatMenu from "../shared/FloatMenu/FloatMenu";
import {
  useFloatMenuSelection,
  type FloatMenuSelection,
  type SelectionProvenance,
} from "../shared/FloatMenu/useFloatMenuSelection";
import { launchFloatingDeepResearch } from "../Reading/launchFloatingDeepResearch";

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
 * Residual (fh): Deep-research primary path opens deep_research_session window
 * floating|full (parity Reading/HighlightToolbar). Chase startInvestigation
 * remains the degraded fallback when float launch fails.
 * Residual (jj): Settings depth-tier → research_tier on launch (parity ji).
 * Residual (lp): DecisionTreeDriverBadge researchTier (graph block DR entry).
 * Residual (qp): DecisionTreeDriverBadge promptText from live selection or block text.
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
  const { researchTier } = useSettingsResearchTier();

  // The host resolves provenance: this node's source document grounds any note
  // (§9 chain claim→chunk→document). The selection hook reads the DOM range;
  // the host maps it to graph entities — here, the node's own source document.
  const resolveProvenance = (_range: Range, _text: string): SelectionProvenance => ({
    documentId: node.source_document_id ?? null,
    chunkId: null, // a free selection over node text resolves no single chunk
  });

  const selection = useFloatMenuSelection({ scopeRef, resolveProvenance });

  async function deepResearch(
    safeSpawnText: string | null,
    opts?: { viewMode?: "floating" | "full" },
  ) {
    // §9.0: refuse to spawn on a withheld body.
    if (safeSpawnText === null) return;
    const assetId =
      (node.source_document_id || "").trim() || investigationId || "__research__";
    const viewMode = opts?.viewMode === "full" ? "full" : "floating";
    try {
      // Residual (fh/jj): window host first + Settings research_tier.
      await launchFloatingDeepResearch({
        asset_id: assetId,
        selection_text: safeSpawnText,
        goal_hint: "Deep-research the highlighted block detail passage",
        view_mode: viewMode,
        research_tier: researchTier,
      });
    } catch {
      // Degraded: REUSED chase path — child investigation + navigate.
      const resp = await startInvestigation({
        question: safeSpawnText,
        context: safeSpawnText,
        parent_investigation_id: investigationId,
        spawn_context: safeSpawnText,
      });
      recordSpawnRelationship(resp.investigation_id, investigationId);
      navigate(`/inv/${resp.investigation_id}`);
    }
  }

  return (
    <div
      className="flex flex-col h-full text-ink dark:text-bright p-4"
      data-testid="block-detail"
      data-view-format="html"
      data-research-tier={researchTier}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
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
      {/* Residual (lp): model driver + budget + depth before graph-block DR. */}
      <div
        className="mb-2"
        data-testid="block-detail-driver-badge-mount"
        data-view-format="html"
        data-research-tier={researchTier}
      >
        <DecisionTreeDriverBadge
          researchTier={researchTier}
          promptText={
            (selection?.text || node.text || "").trim() || undefined
          }
        />
      </div>
      {/* The scope container the float-menu narrows to — select text here. */}
      <div ref={scopeRef} className="font-serif text-base leading-relaxed">
        {node.text || <span className="italic text-ink-mute dark:text-moonlight">(empty)</span>}
      </div>
      <FloatMenu
        selection={selection}
        investigationId={investigationId}
        onDeepResearch={(
          safeSpawnText: string | null,
          _sel: FloatMenuSelection,
          opts?: { viewMode?: "floating" | "full" },
        ) => void deepResearch(safeSpawnText, opts)}
      />
    </div>
  );
}
