import { useEffect, type ReactNode } from "react";
import { useParams } from "react-router-dom";

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
 *
 * STARTER KEY (MS-01 F5 generalized, GAPS §8 G-X1): React keeps ONE
 * instance when only a path param changes ("/wrestle" and
 * "/wrestle/:documentId" render the same element type at the same tree
 * position), so "open on mount" opened the starters exactly once per
 * component instance. The starters effect is therefore keyed on the
 * route's params (joined, sorted) plus the starters' identity. When the
 * key moves — /wrestle → /wrestle/:id, /create → /create/:id,
 * /inv/a → /inv/b — the outgoing starters close and the current ones
 * open, exactly as if the host had remounted. A hydration of a new scope
 * (AppShell's layout effect, which runs first) already replaced the
 * workspace and bumps the hydration generation; then the outgoing close
 * is skipped and the open below layers over the restored layout.
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
  const params = useParams();

  const signature = starterSignature(starters, params);

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
    // Re-runs only when the starter key moves (route params) or the starter
    // list's identity changes — never on ordinary parent re-renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  // `panels` is pulled in for future use (and tree-shaking would drop the
  // useEffect line; this is the harmless way to keep the dependency list
  // visible).
  void panels;

  return <>{children}</>;
}

/**
 * The starter key: the route params the starters hang off (sorted `k=v`
 * pairs) plus the starters' own identity (id/kind/mode/title — NOT props,
 * which carry live objects and change every render). Two renders with the
 * same signature need no starter work; a move re-opens the list.
 */
function starterSignature(
  starters: StarterPanel[],
  params: Readonly<Record<string, string | undefined>>,
): string {
  const paramKey = Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([k, v]) => `${k}=${String(v)}`)
    .join("&");
  const listKey = starters
    .map((s, i) => `${i}:${s.id ?? ""}|${s.kind}|${s.mode ?? ""}|${s.title ?? ""}`)
    .join(";");
  return `${paramKey}#${listKey}`;
}

export default PanelHost;
