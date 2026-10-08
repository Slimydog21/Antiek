/**
 * agentTypes.ts — the agent pane's own tab shape (SPR-07, Phase A).
 *
 * Structural on purpose: the frozen SPR-06 contracts key
 * AGENT_RUN_KIND_OF_TAB by AgentTabKind and cannot be widened here (handoff
 * finding F1). Every file under workspace/agent/ is developed against this
 * type; companionRegistry.AgentPaneSurface maps an AgentTabDescriptor that
 * carries `agentId` onto it (repair C1).
 */
import type { AgentTabKind } from "../companionStore";
import type { DocumentAnchor } from "../contracts/anchor";
import type { AgentScope } from "../contracts/tree";

export interface AgentPaneTab {
  /** The companion tab id (Phase B: `agent:pane:<agentId>`). */
  id: string;
  title: string;
  scope: AgentScope;
  /** Present iff scope === "project". */
  projectId?: string;
  /** agentPaneId(): `p:<projectId>` | `x:<seq>`. */
  agentId: string;
  anchor?: DocumentAnchor;
}

/** The ambient typed-event scope the pane's exchanges are bucketed under —
 *  the AISidecar "__sidecar__" / companion "__companion__" convention
 *  (CompanionAgents.tsx:32), kept distinct per surface. */
export const AGENT_PANE_SCOPE = "__agent__";

/** The pane the draft key names; the only host today. */
export const PANE = "companion";

/** The companion kind F1 will register the pane under. Until the SPR-06
 *  owner lands that row the pane is a "dialogue"-kind tab carrying
 *  `agentId` (companionStore.ts); the discriminator below is that field,
 *  never the kind, so the frozen union is not widened here. */
export const AGENT_TAB_KIND = "agent";

/** The companion kind the pane's tab carries on the frozen vocabulary: the
 *  run kind F1(a) maps kind "agent" to, so the opener's `agentKind` and the
 *  tree's `runKind` are identical either way. F1 flips this to "agent". */
export const AGENT_PANE_TAB_KIND: AgentTabKind = "dialogue";

export function isAgentPaneTab(tab: { agentId?: string } | null | undefined): boolean {
  return tab?.agentId !== undefined;
}
