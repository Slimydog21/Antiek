/**
 * RecordCrumb — the Topbar's name for a record route (/inv/:id, /read/:id,
 * /write/:id), said the way its document tab says it (lane A stage B3,
 * defect 9): the title from tabTitles through labelForTab, never the URL
 * slug ("Inv finches") and never a raw id. While the title is being looked
 * up the crumb reads as the kind's noun.
 *
 * The open tab showing the route names it when there is one (a footnote hop
 * on the same book reads as its passage, like the strip); otherwise the
 * route's own surface does. Loaded with the tab-tree chunk, never the entry
 * chunk; Topbar draws the noun until it lands.
 */
import { useEffect } from "react";

import { mothershipForPath, rootRefForPath, tabShowsPath } from "./documentSpace";
import { labelForTab } from "./tabLabels";
import { requestTabTitle, titleKey, useTabTitles } from "./tabTitles";
import { useTabTrees } from "./tabTreeStore";

export default function RecordCrumb({ pathname, search }: { pathname: string; search: string }) {
  const ref = rootRefForPath(pathname);
  const mothership = mothershipForPath(pathname, search);
  const tab = useTabTrees((s) => {
    const tree = s.trees[mothership];
    if (!tree) return null;
    const active = tree.active_tab_id ? tree.nodes[tree.active_tab_id] : null;
    if (active && tabShowsPath(active, pathname)) return active;
    return Object.values(tree.nodes).find((n) => tabShowsPath(n, pathname)) ?? null;
  });
  const parent = useTabTrees((s) => (tab?.parent_tab_id ? (s.trees[mothership]?.nodes[tab.parent_tab_id] ?? null) : null));
  const surface = tab ?? (ref ? { kind: ref.kind, ref: ref.ref } : null);
  const entry = useTabTitles((s) => (surface ? s.entries[titleKey(surface.kind, surface.ref)] : undefined));

  useEffect(() => {
    if (surface) requestTabTitle(surface);
    // The surface is named by its kind and ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [surface?.kind, surface?.ref]);

  if (!surface) return null;
  const label = labelForTab(tab ?? { kind: surface.kind, ref: surface.ref }, parent, entry);
  return (
    <span
      className={`text-1 font-medium truncate ${label.source === "fallback" ? "text-2" : ""}`}
      title={label.pending ? `${label.text} (looking up the title…)` : label.text}
      data-record-crumb
    >
      {label.text}
    </span>
  );
}
