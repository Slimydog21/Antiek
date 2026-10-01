import { useCompanion, setCompanionTreePort, type AgentTabDescriptor } from "./companionStore";
import { mothershipForPath } from "./mothershipForPath";
import { newTabId } from "./tabId";
import { getTabOwner } from "./tabTreeOwner";
import type { Mothership } from "./tabTree";
import type { useTabTrees } from "./tabTreeStore";
import { projectFromSearch, useProjectSelection } from "./projectSelection";

let mode: Mothership | null = null;
let refresh: (() => void) | null = null;
export function setCompanionMode(next: Mothership): void { mode = next; refresh?.(); }
export function resetCompanionMode(): void { mode = null; }
const currentMode = (): Mothership => mode ?? mothershipForPath(window.location.pathname, window.location.search);

export function installCompanionTreeBinding(store: typeof useTabTrees): void {
  let publishedScope = "";
  const publish = () => {
    const state = store.getState();
    const scope = `${state.contextEpoch}:${state.projectId ?? ""}:${currentMode()}`;
    const tree = state.trees[currentMode()];
    const session = useCompanion.getState();
    const dialogue = session.tabs.filter((tab) => tab.kind === "dialogue");
    const durable: AgentTabDescriptor[] = tree ? Object.values(tree.nodes)
      .filter((node) => node.side === "right")
      .sort((a, b) => a.hier_number.localeCompare(b.hier_number, undefined, { numeric: true }))
      .map((node, index): AgentTabDescriptor => {
        const base = { id: node.tab_id, documentId: node.branch_origin?.document_id, title: node.title || node.kind, publicNumber: node.public_number, persistence: "tree" as const, seq: index + 1 };
        switch (node.kind) {
          case "research": return { ...base, kind: "research-thread", investigationId: node.ref, threadKind: "research" };
          case "dialogue": case "reformat": case "diligence": case "island": return { ...base, kind: "durable-thread", investigationId: node.ref, threadKind: node.kind };
          case "findings": case "flags": return { ...base, kind: "project-tool", projectId: node.ref, toolKind: node.kind };
          case "block": return { ...base, kind: "writing-block", blockId: node.ref };
          default: throw new Error(`Invalid right node kind: ${node.kind}`);
        }
      }) : [];
    const ordered = [...durable];
    const previousIndices = new Map(session.tabs.map((tab, index) => [tab.id, index]));
    for (const tab of dialogue) {
      const index = scope === publishedScope ? previousIndices.get(tab.id) ?? ordered.length : ordered.length;
      ordered.splice(Math.max(0, Math.min(index, ordered.length)), 0, tab);
    }
    publishedScope = scope;
    const activeDialogue = dialogue.some((tab) => tab.id === session.activeTabId);
    useCompanion.setState({ tabs: ordered, activeTabId: activeDialogue ? session.activeTabId : tree?.active_right ?? null });
  };
  refresh = publish;
  store.subscribe(publish);
  setCompanionTreePort({
    owns: (id) => store.getState().trees[currentMode()]?.nodes[id]?.side === "right",
    open: (input) => {
      const state = store.getState();
      if (!state.dispatchAllowed || !input.investigationId?.trim() || input.kind !== "research-thread") return "";
      const requested = projectFromSearch(window.location.search);
      if (requested && (requested !== state.projectId || useProjectSelection.getState().status === "missing")) return "";
      const m = currentMode();
      const tree = state.trees[m];
      const existing = tree && Object.values(tree.nodes).find((node) => node.side === "right" && node.kind === "research" && node.ref === input.investigationId);
      const id = existing?.tab_id ?? newTabId(tree ?? undefined);
      if (!existing) {
        const result = state.spawnTab(m, null, { tab_id: id, side: "right", kind: "research", ref: input.investigationId, title: input.title, ...(input.documentId ? { origin: { document_id: input.documentId, kind: "reference" as const } } : {}), mothership: m, activate: false }, "route");
        if (!result.ok) return "";
      }
      useCompanion.setState({ activeTabId: id });
      state.activateRightTab(m, id);
      publish();
      return id;
    },
    activate: (id) => { store.getState().activateRightTab(currentMode(), id); publish(); },
    close: (id) => {
      const m = currentMode();
      const state = store.getState();
      const tree = state.trees[m];
      const ids = tree && Object.values(tree.nodes).filter((node) => node.side === "right").map((node) => node.tab_id);
      if (!tree || !ids) return;
      const index = ids.indexOf(id);
      if (index === -1) return;
      state.closeTabById(m, id, "lift_children");
      if (tree.active_right === id) state.activateRightTab(m, ids[index - 1] ?? ids[index + 1] ?? null);
      publish();
    },
    restore: (id) => {
      if (!store.getState().dispatchAllowed || getTabOwner().suspended) return false;
      const restored = store.getState().restoreRightTab(currentMode(), id);
      if (restored) { useCompanion.setState({ activeTabId: id }); publish(); }
      return restored;
    },
    reopen: () => {
      const state = store.getState();
      const m = currentMode();
      const tree = state.trees[m];
      if (!tree) return false;
      const held = state.heldClose;
      const id = held?.mothership === m && tree.history[held.token.tab_id]?.node.side === "right" ? held.token.tab_id : Object.values(tree.history)
        .filter((entry) => entry.node.side === "right")
        .sort((a, b) => b.closed_at.localeCompare(a.closed_at))[0]?.node.tab_id;
      return id ? state.restoreRightTab(m, id) : false;
    },
  });
  publish();
}
