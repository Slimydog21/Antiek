import { useEffect, type ReactNode } from "react";

import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";
import type { PanelKind, PanelMode } from "./panel.types";

/**
 * PanelHost — opt-in wrapper a route component renders to live inside
 * the workspace panel shell.
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

  return <PanelLayout mainSlot={children} />;
}

export default PanelHost;
