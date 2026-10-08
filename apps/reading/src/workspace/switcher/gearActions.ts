/**
 * gearActions.ts — SPR-04 M4: the ONLY file in the switcher that names a
 * store. The reducer (switcherKeys.ts) names an effect; this runs it.
 *
 * Every check reads the stores' CURRENT state (useContextTreeStore,
 * useCompanion, useWorkspace), never a snapshot the surface captured at
 * keypress: a publish can land between the keypress and the effect (gear 3
 * runs on a microtask after the dialog closes), and a snapshot would admit
 * an agent the current tree no longer holds (repair round 2026-10-07T22:40Z,
 * F2/F10).
 *
 * Gear → store mapping (specs/antiek-keyboard-panes-agents-20261007/
 * sprint-04-geared-switcher.html, ffx-kpa-spr-04 M4). "Store that changes"
 * is the mechanically observed set over all 12 zustand stores
 * (gearActions.test.tsx watchStores), not a claim:
 *
 * | Effect            | Path                                                    | Store that changes                       |
 * |-------------------|---------------------------------------------------------|------------------------------------------|
 * | select-project    | toggleProjectPicker({ focusId: id }): the picker opens  | none directly → the picker's `choose`    |
 * |                   | over the switch with that row focused; its `choose` is  | (the census-sanctioned writer) →         |
 * |                   | the one UI writer of the selected project               | tabTreeStore (trees reset, epoch+1,      |
 * |                   | (writerCensus.test.ts:29; not spelled here). On close focus returns to    | persistence) → the selection mirror      |
 * |                   | the gear-1 tab; the surface's effect on                 |                                          |
 * |                   | selection.projectId feeds `project-arrived`.            |                                          |
 * |                   | After F1 (the census names this file) this becomes      |                                          |
 * |                   | one line: selectProject on useSelection.getState().  |                                          |
 * |                   | DEVIATION: the sprint page also says "+ workspace slot".|                                          |
 * |                   | No SPR-01 slot store exists on this base (grep          |                                          |
 * |                   | workspaceSlot|useSlots|slotStore finds nothing), so     |                                          |
 * |                   | the slot leg is owed to SPR-01's landing, not faked.    |                                          |
 * | select-subproject | isSelectionPathOf({projectId, subProjectId}, store tree)| useSelection; tabTreeStore via           |
 * |                   | else refused; selectSubProject(id, tree) (its boolean is| spawnNewTab only (newTab.ts:56, the one  |
 * |                   | IGNORED: same-id returns false, selection.ts:113);      | spawn path: awaits ensureMothership,     |
 * |                   | route null → "no-route", else spawnNewTab(research)     | retries once on an epoch change); AND    |
 * |                   |                                                         | useTabTitles (spawnNewTab → setTabTitle, |
 * |                   |                                                         | newTab.ts:84: the title cache)           |
 * | select-agent      | isSelectionPathOf({...cur, agentId}, store tree) else   | useCompanion (activate if useCompanion   |
 * |                   | refused; the companion's OWN tab list decides open vs   | holds the view, else the contract opener;|
 * |                   | open (the effect's viewOpen is the model's reading and  | !ok → "open-failed" with ZERO writes),   |
 * |                   | can be stale); then selectAgent (boolean ignored); then | then useSelection, then useWorkspace     |
 * |                   | focusCompanion()                                        | (inset: focusedPane "right" + DOM focus; |
 * |                   |                                                         | docked: focusedPanelId = companion:main, |
 * |                   |                                                         | opened if absent; no DOM focus target    |
 * |                   |                                                         | exists for a docked panel)               |
 * | close / notch     | nothing                                                 | none                                     |
 *
 * Never spawns `/inv/` for a non-investigation node: the route is the
 * model's (`node.route`), decided by the node's source, not here.
 */
import { COMPANION_PANEL_ID } from "../companionVisibility";
import { useCompanion } from "../companionStore";
import { openAgentFromDocument } from "../contracts/openers";
import { isSelectionPathOf, useSelection } from "../contracts/selection";
import { useContextTreeStore } from "../contracts/treeStore";
import { spawnNewTab } from "../newTab";
import { focusPane, toggleProjectPicker } from "../shortcuts";
import { useWorkspace } from "../WorkspaceStore";
import type { GearEffect } from "./switcherKeys";

export type GearActionOutcome =
  | { ok: true; changed: readonly ("picker" | "subproject" | "tabs" | "agent" | "companion")[]; tab?: "no-route" }
  | { ok: false; reason: "refused" | "open-failed" };

const REFUSED: GearActionOutcome = { ok: false, reason: "refused" };

/** The companion, by preset: focusPane("right") means "the right inset
 *  pane" only in omarchy-inset (in docked it cycles panels, shortcuts.ts
 *  focusPane); docked focuses the companion dock panel itself. */
function focusCompanion(): void {
  const ws = useWorkspace.getState();
  if (ws.layoutPreset === "omarchy-inset") {
    focusPane("right");
    return;
  }
  // `open` on an existing id focuses it instead of duplicating (WorkspaceStore.open).
  ws.open("Companion", {}, { mode: "docked-right", id: COMPANION_PANEL_ID, title: "Companion" });
}

export async function runGearEffect(effect: GearEffect): Promise<GearActionOutcome> {
  const tree = useContextTreeStore.getState().tree;
  switch (effect.type) {
    case "select-project": {
      toggleProjectPicker({ focusId: effect.id });
      return { ok: true, changed: ["picker"] };
    }
    case "select-subproject": {
      const cur = useSelection.getState().selection;
      if (!isSelectionPathOf({ projectId: cur.projectId, subProjectId: effect.id }, tree)) return REFUSED;
      useSelection.getState().selectSubProject(effect.id, tree);
      if (effect.route === null) return { ok: true, changed: ["subproject"], tab: "no-route" };
      await spawnNewTab({ kind: "research", ref: effect.route, title: effect.label });
      return { ok: true, changed: ["subproject", "tabs"] };
    }
    case "select-agent": {
      const cur = useSelection.getState().selection;
      if (!isSelectionPathOf({ ...cur, agentId: effect.id }, tree)) return REFUSED;
      const companion = useCompanion.getState();
      if (companion.tabs.some((t) => t.id === effect.viewId)) {
        companion.activateAgentTab(effect.viewId);
      } else {
        const opened = openAgentFromDocument({
          kind: effect.kind,
          scope: effect.scope,
          ...(effect.investigationId !== undefined ? { investigationId: effect.investigationId } : {}),
          title: effect.label,
        });
        if (!opened.ok) return { ok: false, reason: "open-failed" };
      }
      useSelection.getState().selectAgent(effect.id, tree);
      focusCompanion();
      return { ok: true, changed: ["agent", "companion"] };
    }
    case "close":
    case "notch":
      return { ok: true, changed: [] };
  }
}
