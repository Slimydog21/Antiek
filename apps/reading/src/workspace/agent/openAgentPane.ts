/**
 * openAgentPane.ts — the ONE open path for the agent pane (SPR-07).
 *
 * Idempotent open-or-focus: the pane is a companion tab with its own id
 * space (`agent:pane:<agentId>`, agentPaneId.ts); an existing tab is
 * activated and its composer refocused (bumpNonce), never duplicated.
 *
 *   1. In the inset preset a LEFT-pane fullscreen is cleared FIRST (fix 5:
 *      companionStore.openAgentTab never clears fullscreen, so the composer
 *      would sit under [hidden] and the focus effect would land nowhere);
 *   2. the tab opens through companionStore.openAgentTab — the store the
 *      frozen opener itself delegates to (openers.ts:4-5). The frozen
 *      `openAgentFromDocument` is not callable here: the frozen vocabulary
 *      has no project-scoped kind (it refuses kind "dialogue" + scope
 *      "project", openers.ts:84) and forwards neither agentId nor projectId
 *      (handoff F1(c)). The hour F1 lands, step 2 becomes
 *      `openAgentFromDocument({kind: "agent", scope, agentId, projectId,
 *      anchor, title})` and nothing else here changes;
 *   3. `useAgentPaneStore.bumpNonce(viewId)` so the composer's mount/refocus
 *      effect fires on re-activation (AgentComposer.tsx).
 *
 * The tab's `kind` is "dialogue": the run kind F1(a) maps kind "agent" to,
 * and the only kind the frozen AGENT_RUN_KIND_OF_TAB admits for a
 * thought-partner dialogue. The pane's project scope is enforced in this
 * browser only (the badge says so); the frozen pre-backend adapter files
 * the tab as session-global until F2 (CONTRACTS.md §2 scope provenance).
 */
import type { DocumentAnchor } from "../contracts/anchor";
import { useSelection } from "../contracts/selection";
import type { AgentScope } from "../contracts/tree";
import { useCompanion } from "../companionStore";
import { useWorkspace } from "../WorkspaceStore";
import { writeAgentDraft } from "./agentDraft";
import { AGENT_TAB_ID_PREFIX, agentDraftKey, agentPaneId, agentTabIdFor } from "./agentPaneId";
import { useAgentPaneStore } from "./agentPaneStore";
import { AGENT_PANE_TAB_KIND, PANE } from "./agentTypes";

export interface OpenAgentPaneInput {
  scope: AgentScope;
  /** The project a project-scoped pane belongs to; the selection's when absent. */
  projectId?: string;
  /** The exact pane id (a deep link); derived from scope + project otherwise. */
  agentId?: string;
  anchor?: DocumentAnchor;
  title?: string;
  /** Seeds the composer (written under the pane's draft key before the mount). */
  draft?: string;
  interview?: boolean;
}

export type OpenAgentPaneResult =
  | { ok: true; viewId: string; agentId: string; reused: boolean }
  | { ok: false; reason: "no_project" };

/** The next `x:<seq>` id: one past the highest cross-project pane open. */
function nextCrossProjectSeq(): number {
  const prefix = `${AGENT_TAB_ID_PREFIX}x:`;
  let max = 0;
  for (const t of useCompanion.getState().tabs) {
    if (!t.id.startsWith(prefix)) continue;
    const n = Number(t.id.slice(prefix.length));
    if (Number.isFinite(n) && n > max) max = n;
  }
  return max + 1;
}

export function openAgentPane(i: OpenAgentPaneInput): OpenAgentPaneResult {
  // TAB_PROJECT_ID ("default") counts as a project: the selection mirrors tabTreeStore.
  const projectId = i.scope === "project" ? (i.projectId ?? useSelection.getState().selection.projectId) : undefined;
  if (i.scope === "project" && !projectId) return { ok: false, reason: "no_project" };
  const agentId = i.agentId ?? agentPaneId(i.scope, projectId, i.scope === "cross-project" ? nextCrossProjectSeq() : undefined);
  const viewId = agentTabIdFor(agentId);

  const ws = useWorkspace.getState();
  if (ws.layoutPreset === "omarchy-inset" && ws.fullscreenPane === "left") ws.setFullscreenPane(null);

  if (i.draft !== undefined) {
    writeAgentDraft(agentDraftKey({ ...(projectId ? { projectId } : {}), agentId, pane: PANE }), i.draft);
  }

  const store = useCompanion.getState();
  const reused = store.tabs.some((t) => t.id === viewId);
  const title = i.title?.trim() || (i.scope === "project" ? "Project agent" : "Agent");
  const opened = store.openAgentTab({
    kind: AGENT_PANE_TAB_KIND,
    title,
    scope: i.scope,
    agentId,
    ...(projectId ? { projectId } : {}),
    ...(i.anchor ? { anchor: i.anchor } : {}),
    ...(i.interview ? { interview: true } : {}),
  });
  useAgentPaneStore.getState().bumpNonce(opened);
  return { ok: true, viewId: opened, agentId, reused };
}

/** prefix+a / ctrl+alt+a: project-scoped; an anchor only when the reading
 *  focus exposes a pinned selection (today it exposes page text only, so no
 *  anchor; recorded). */
export function openAgentPaneFromKey(): OpenAgentPaneResult {
  return openAgentPane({ scope: "project" });
}

/** The `#pane=agent:<agentId>` deep link (paneHash.ts): `p:<projectId>` opens
 *  that project's pane, `x:<n>` a cross-project one. Unknown shapes open nothing. */
export function openAgentPaneFromAgentId(agentId: string): OpenAgentPaneResult | null {
  if (agentId.startsWith("p:") && agentId.length > 2) return openAgentPane({ scope: "project", projectId: agentId.slice(2) });
  if (/^x:\d+$/.test(agentId)) return openAgentPane({ scope: "cross-project", agentId });
  return null;
}
