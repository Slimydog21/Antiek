/**
 * gearActions.ts — SPR-04 M4: the ONLY file in the switcher that names a
 * store. The reducer (switcherKeys.ts) names an effect; this runs it.
 *
 * Gear → store mapping (specs/antiek-keyboard-panes-agents-20261007/
 * sprint-04-geared-switcher.html, ffx-kpa-spr-04 M4):
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
 * | select-subproject | isSelectionPathOf({projectId, subProjectId}) else       | useSelection; tabTreeStore via           |
 * |                   | refused; selectSubProject(id, tree) (its boolean is     | spawnNewTab only (newTab.ts:56, the one  |
 * |                   | IGNORED: same-id returns false, selection.ts:113);      | spawn path: awaits ensureMothership,     |
 * |                   | route null → "no-route", else spawnNewTab(research)     | retries once on an epoch change)         |
 * | select-agent      | isSelectionPathOf({...cur, agentId}) else refused;      | useSelection, useCompanion,              |
 * |                   | selectAgent (boolean ignored); viewOpen →               | useWorkspace.focusedPane                 |
 * |                   | activateAgentTab(viewId) + focusPane("right"), else     |                                          |
 * |                   | openAgentFromDocument(...) (!ok → "open-failed")        |                                          |
 * | close / notch     | nothing                                                 | none                                     |
 *
 * Never spawns `/inv/` for a non-investigation node: the route is the
 * model's (`node.route`), decided by the node's source, not here.
 */
import { useCompanion } from "../companionStore";
import { openAgentFromDocument } from "../contracts/openers";
import { isSelectionPathOf, useSelection } from "../contracts/selection";
import type { ContextTree } from "../contracts/tree";
import { spawnNewTab } from "../newTab";
import { focusPane, toggleProjectPicker } from "../shortcuts";
import type { GearEffect } from "./switcherKeys";

export type GearActionOutcome =
  | { ok: true; changed: readonly ("picker" | "subproject" | "tabs" | "agent" | "companion")[]; tab?: "no-route" }
  | { ok: false; reason: "refused" | "open-failed" };

const REFUSED: GearActionOutcome = { ok: false, reason: "refused" };

export async function runGearEffect(effect: GearEffect, tree: ContextTree): Promise<GearActionOutcome> {
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
      useSelection.getState().selectAgent(effect.id, tree);
      if (effect.viewOpen) {
        useCompanion.getState().activateAgentTab(effect.viewId);
      } else {
        const opened = openAgentFromDocument({
          kind: effect.kind,
          scope: effect.scope,
          ...(effect.investigationId !== undefined ? { investigationId: effect.investigationId } : {}),
          title: effect.label,
        });
        if (!opened.ok) return { ok: false, reason: "open-failed" };
      }
      focusPane("right");
      return { ok: true, changed: ["agent", "companion"] };
    }
    case "close":
    case "notch":
      return { ok: true, changed: [] };
  }
}
