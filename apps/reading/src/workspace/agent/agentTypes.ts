/**
 * agentTypes.ts — the agent pane's own tab shape (SPR-07, Phase A).
 *
 * Structural on purpose: Phase A never names companion kind "agent" (the
 * frozen SPR-06 contracts key AGENT_RUN_KIND_OF_TAB by AgentTabKind and
 * cannot be widened here; handoff finding F1). Every file under
 * workspace/agent/ is developed against this type; Phase B registers the
 * kind and maps AgentTabDescriptor onto it.
 */
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

/** The companion kind the pane will register under (Phase B). Phase A
 *  compares by string so the frozen union is never widened here. */
export const AGENT_TAB_KIND = "agent";

export function isAgentPaneTab(tab: { kind: string } | null | undefined): boolean {
  return (tab?.kind as string | undefined) === AGENT_TAB_KIND;
}
