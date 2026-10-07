/**
 * openAgentPane.ts — the ONE open path for the agent pane (SPR-07).
 *
 * Phase A (this base): the frozen contracts cannot represent companion
 * kind "agent" (tree.ts AGENT_RUN_KIND_OF_TAB is keyed by the closed
 * AgentTabKind union; handoff finding F1), so this function computes the
 * ids and REFUSES with `contract_pending` — no side effect, never a
 * divergent opener. Phase B (the hour F1 lands) replaces the refusal with:
 *   1. `useWorkspace.getState().setFullscreenPane(null)` FIRST when the
 *      left pane is fullscreen (fix 5: openAgentTab in the inset never
 *      clears fullscreen, so the composer would sit under [hidden]);
 *   2. `openAgentFromDocument({kind: "agent", scope, agentId,
 *      ...(scope === "project" ? {projectId} : {}), ...(anchor ? {anchor}
 *      : {}), title})` — the frozen opener via F1(c), never a fork;
 *   3. `useAgentPaneStore.getState().bumpNonce(viewId)` so the composer's
 *      mount/refocus effect fires on re-activation.
 */
import type { DocumentAnchor } from "../contracts/anchor";
import { useSelection } from "../contracts/selection";
import type { AgentScope } from "../contracts/tree";
import { agentPaneId, agentTabIdFor } from "./agentPaneId";

export interface OpenAgentPaneInput {
  scope: AgentScope;
  anchor?: DocumentAnchor;
  title?: string;
  draft?: string;
  interview?: boolean;
}

export type OpenAgentPaneResult =
  | { ok: true; viewId: string; reused: boolean }
  | { ok: false; reason: "contract_pending"; agentId: string; viewId: string; blockedBy: string };

export const OPEN_BLOCKED_BY = "ffx-kpa-spr-07 F1: tree.ts AGENT_RUN_KIND_OF_TAB row for kind 'agent' (SPR-06 owner)";

export function openAgentPane(i: OpenAgentPaneInput): OpenAgentPaneResult {
  // TAB_PROJECT_ID ("default") counts as a project: the selection mirrors tabTreeStore.
  const projectId = useSelection.getState().selection.projectId;
  const agentId = agentPaneId(i.scope, i.scope === "project" ? projectId : undefined);
  const viewId = agentTabIdFor(agentId);
  return { ok: false, reason: "contract_pending", agentId, viewId, blockedBy: OPEN_BLOCKED_BY };
}

/** prefix+a / ctrl+alt+a (Phase B handler): project-scoped; an anchor only
 *  when the reading focus exposes a pinned selection (today it exposes page
 *  text only, so no anchor; recorded). */
export function openAgentPaneFromKey(): OpenAgentPaneResult {
  return openAgentPane({ scope: "project" });
}
