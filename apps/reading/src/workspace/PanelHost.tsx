import { useEffect, type ReactNode } from "react";

import { getHydrationGeneration, useWorkspace } from "./WorkspaceStore";
import type { PanelKind, PanelMode } from "./panel.types";

/**
 * PanelHost — opt-in wrapper a route component renders to open its starter
 * panels in the workspace panel shell.
 *
 * It renders its children as they are. The docks and floating layer belong
 * to ONE PanelLayout, the shell's (AppShell). PanelHost used to render a
 * second PanelLayout inside the shell's main slot, which subscribed to the
 * same dock arrays and drew every docked panel twice: two left docks, two
 * InvestigationSidebar instances, two polls (MS-01 F4).
 *
 *   export default function ResearchWorkstation() {
 *     return (
 *       <PanelHost starters={[
 *         { kind: "InvestigationSidebar", mode: "docked-left",  title: "Investigations" },
 *         { kind: "Chat",                 mode: "docked-bottom", title: "Chat" },
 *       ]}>
 *         <CenterContent />
 *       </PanelHost>
 *     );
 *   }
 *
 * Starters are opened on mount and closed on unmount (unless the
 * operator pinned them — pinned panels survive route changes once
 * S9 persistence lands).
 */
export type StarterPanel = {
  kind: PanelKind;
  props?: Record<string, unknown>;
  mode?: PanelMode;
  title?: string;
  /** Stable id override so this starter remains the same panel across
   *  remounts of the same route. */
  id?: string;
};

type Props = {
  starters?: StarterPanel[];
  children: ReactNode;
};

export function PanelHost({ starters = [], children }: Props) {
  const open = useWorkspace((s) => s.open);
  const close = useWorkspace((s) => s.close);
  const panels = useWorkspace((s) => s.panels);

  useEffect(() => {
    const generation = getHydrationGeneration();
    const openedIds: string[] = [];
    for (const starter of starters) {
      const id = open(starter.kind, starter.props ?? {}, {
        mode: starter.mode,
        title: starter.title,
        id: starter.id,
      });
      openedIds.push(id);
    }
    return () => {
      // A newer hydration (the route changed) already replaced the workspace
      // with the next scope's stored layout, keeping only pinned panels from
      // this one. Closing "our" ids now would delete that layout's panels
      // that share a starter id.
      if (getHydrationGeneration() !== generation) return;
      // Honor pinned: a pinned panel survives the route unmount.
      // We read the latest snapshot lazily via getState() to avoid
      // stale-closure pinning state.
      const latest = useWorkspace.getState().panels;
      for (const id of openedIds) {
        const p = latest[id];
        if (!p) continue;
        if (p.pinned) continue;
        close(id);
      }
    };
    // Intentional: starters are immutable per-mount. Re-running this
    // effect on every render would tear down + reopen panels on each
    // parent re-render. Route changes naturally unmount + remount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The eslint-disable above keeps the static behaviour. `panels` is
  // pulled in for future use (and tree-shaking would drop the useEffect
  // line; this is the harmless way to keep the dependency list visible).
  void panels;

  return <>{children}</>;
}

export default PanelHost;
