/**
 * agentPaneId.ts — the pane's id algebra (SPR-07 M1).
 *
 *   agentId     `p:<projectId>` for a project-scoped agent (one per project:
 *               re-opening focuses, never duplicates) or `x:<seq>` for a
 *               cross-project one;
 *   tab id      `agent:pane:<agentId>` (Phase B pins it to the store's
 *               agentTabId);
 *   draft key   account-scoped, keyed by {project, agent, pane}; the anchor
 *               is NOT in the key (decision 4: typed words survive a
 *               re-anchor; the chip is re-announced instead).
 */
import { accountStorageKey } from "../../lib/accountWorkspaceOwner";
import type { AgentScope } from "../contracts/tree";

export const AGENT_TAB_ID_PREFIX = "agent:pane:";

export function agentPaneId(scope: AgentScope, projectId?: string, seq?: number): string {
  if (scope === "project" && projectId) return `p:${projectId}`;
  return `x:${seq ?? 0}`;
}

export function agentTabIdFor(agentId: string): string {
  return `${AGENT_TAB_ID_PREFIX}${agentId}`;
}

/** null ⇒ signed out ⇒ no I/O (accountWorkspaceOwner.ts:188). */
export function agentDraftKey(i: { projectId?: string; agentId: string; pane: string }): string | null {
  return accountStorageKey(`antiek.agent.draft.v1.${i.projectId ?? "*"}.${i.agentId}.${i.pane}`);
}
