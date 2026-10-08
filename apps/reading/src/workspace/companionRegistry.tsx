/**
 * companionRegistry.tsx — the companion's tab-kind registry, as DATA (the
 * PanelRegistry discipline): one entry per shipped agent kind, each naming
 * its surface and its status glyph. Adding an agent kind later — the island
 * (unit 2), the diligence run (unit 7) — is one entry here, never a
 * restructure of the pane.
 */
import type { ComponentType } from "react";

import type { InvestigationSummary } from "../lib/api";
import { researchStateDotClass, researchStateFor, researchStateStyle } from "../shared/researchState";
import type { AgentTabDescriptor, AgentTabKind } from "./companionStore";
import {
  DialogueSurface,
  ResearchThreadSurface,
  type AgentSurfaceProps,
} from "./CompanionAgents";
import { AgentPane } from "./agent/AgentPane";

export interface AgentGlyph {
  /** Tailwind classes for the status dot (token-resolved, reduced-motion
   *  honored by the shared researchState registry). */
  className: string;
  /** Accessible label for the glyph (the plain-language state). */
  label: string;
}

export interface AgentTabKindMeta {
  /** The strip's fallback title for a tab of this kind. */
  label: string;
  Surface: ComponentType<AgentSurfaceProps>;
  glyph: (tab: AgentTabDescriptor, summary?: InvestigationSummary) => AgentGlyph;
}

export const AGENT_TAB_KINDS: Record<AgentTabKind, AgentTabKindMeta> = {
  "research-thread": {
    label: "research",
    Surface: ResearchThreadSurface,
    glyph: (_tab, summary) => {
      if (!summary) {
        return { className: "bg-[var(--state-muted)]", label: "loading" };
      }
      const state = researchStateFor(summary.status);
      return {
        className: researchStateDotClass(state, false),
        label: researchStateStyle(summary.status).label,
      };
    },
  },
  dialogue: {
    label: "dialogue",
    Surface: DialogueSurface,
    // A dialogue is one-shot: no run state to glyph — a steady brand dot.
    glyph: () => ({ className: "bg-sun", label: "dialogue" }),
  },
};

// ---------------------------------------------------------------------------
// SPR-07: the agent second pane (repair C1)
// ---------------------------------------------------------------------------

/** The agent pane as a companion surface. A tab carrying `agentId` is the
 *  pane (companionStore.AgentTabDescriptor.agentId); its `kind` stays
 *  "dialogue" on the frozen SPR-06 vocabulary (the run kind F1(a) maps kind
 *  "agent" to), so AGENT_TAB_KINDS above stays exactly the frozen table
 *  (tree.test.ts T5 compares the two key sets) and the resolver below is
 *  where the pane is registered. F1 moves this entry under kind "agent". */
function AgentPaneSurface({ tab }: AgentSurfaceProps) {
  if (tab.agentId === undefined) return null;
  return (
    <AgentPane
      tab={{
        id: tab.id,
        title: tab.title,
        scope: tab.scope ?? "cross-project",
        agentId: tab.agentId,
        ...(tab.projectId !== undefined ? { projectId: tab.projectId } : {}),
        ...(tab.anchor ? { anchor: tab.anchor } : {}),
      }}
      interview={tab.interview === true}
    />
  );
}

export const AGENT_PANE_META: AgentTabKindMeta = {
  label: "agent",
  Surface: AgentPaneSurface,
  // A steady brand dot until SPR-10's status source feeds the pane.
  glyph: () => ({ className: "bg-sun", label: "agent" }),
};

/** Is this descriptor the SPR-07 agent pane? ONE rule, shared by the
 *  strip, the resizer's collapse-to-close and the pane itself. */
export function isAgentPaneDescriptor(tab: Pick<AgentTabDescriptor, "agentId">): boolean {
  return tab.agentId !== undefined;
}

/** The registry lookup every consumer goes through: the agent pane when the
 *  tab carries `agentId`, else the tab kind's own entry. */
export function metaFor(tab: Pick<AgentTabDescriptor, "kind" | "agentId">): AgentTabKindMeta {
  return isAgentPaneDescriptor(tab) ? AGENT_PANE_META : AGENT_TAB_KINDS[tab.kind];
}
