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
