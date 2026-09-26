/**
 * TabPathHeader — the breadcrumb from the root document to the active tab
 * (DESIGN-MODEL §2a): `1 Origin of Species › 1.3 Lyell, Principles ›
 * 1.3.2 ch. 3`. Past four crumbs it compresses in the middle
 * (`1 › … › 1.3 › 1.3.2`); the ellipsis opens the whole path as a list,
 * and Esc (or a click elsewhere) closes it and returns focus to the
 * ellipsis. Every crumb is a link to its tab.
 */
import { useEffect, useRef, useState } from "react";

import type { TabLabel } from "./tabLabels";
import { NumberedLabel } from "./tabStripParts";
import type { TabTree } from "./tabTree";

/** Crumbs shown in full; a longer path compresses in the middle. */
export const PATH_CRUMBS_MAX = 4;

const crumbClass =
  "flex items-center gap-1 min-w-0 overflow-hidden rounded px-1 py-0.5 text-ink-soft dark:text-moonlight hover:bg-ice-2 dark:hover:bg-charcoal-1 hover:text-ink dark:hover:text-bright focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun";

export function TabPathHeader({
  tree,
  path,
  labelOf,
  onActivate,
}: {
  tree: TabTree;
  /** Root → active, as tab ids. */
  path: string[];
  labelOf: (tabId: string) => TabLabel;
  onActivate: (tabId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ellipsisRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const compressed = path.length > PATH_CRUMBS_MAX;

  // A new path closes the expanded list.
  const pathKey = path.join("\u0000");
  useEffect(() => setOpen(false), [pathKey]);

  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector<HTMLElement>("[aria-current='page']")?.focus();
    function onPointerDown(e: PointerEvent) {
      const t = e.target as Node;
      if (listRef.current?.contains(t) || ellipsisRef.current?.contains(t)) return;
      setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function close() {
    setOpen(false);
    ellipsisRef.current?.focus();
  }

  const shown: (string | "ellipsis")[] = compressed
    ? [path[0], "ellipsis", path[path.length - 2], path[path.length - 1]]
    : path;
  const last = path[path.length - 1];

  function crumb(id: string, extra = "") {
    const tab = tree.nodes[id];
    return (
      <button
        type="button"
        data-crumb={id}
        aria-current={id === last ? "page" : undefined}
        onClick={() => onActivate(id)}
        className={`${crumbClass} ${id === last ? "text-ink dark:text-bright" : ""} ${extra}`}
      >
        <NumberedLabel tab={tab} label={labelOf(id)} />
      </button>
    );
  }

  return (
    <nav
      aria-label="Tab path"
      data-tab-path
      className="relative flex items-center min-w-0 h-7 px-1.5 text-xs border-b border-hairline"
    >
      <ol className="flex items-center min-w-0 gap-0.5">
        {shown.map((item, i) => (
          <li
            key={item === "ellipsis" ? "ellipsis" : item}
            className={`flex items-center gap-0.5 min-w-0 ${item === last ? "shrink" : "shrink-[2]"}`}
          >
            {i > 0 ? (
              <span aria-hidden="true" className="text-ink-mute dark:text-moonlight/60 px-0.5">
                ›
              </span>
            ) : null}
            {item === "ellipsis" ? (
              <button
                ref={ellipsisRef}
                type="button"
                data-crumb-ellipsis
                aria-expanded={open}
                aria-controls="tab-path-full"
                aria-label={`Show the whole path (${path.length} tabs)`}
                onClick={() => setOpen((o) => !o)}
                className={`${crumbClass} shrink-0 font-mono`}
              >
                …
              </button>
            ) : (
              crumb(item, item === path[0] ? "max-w-[11rem]" : item === last ? "" : "max-w-[13rem]")
            )}
          </li>
        ))}
      </ol>

      {compressed && open ? (
        <div
          ref={listRef}
          id="tab-path-full"
          data-tab-path-full
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              e.stopPropagation();
              close();
            }
          }}
          className="absolute left-1.5 top-full z-30 mt-0.5 max-h-[50vh] w-[min(28rem,calc(100vw-2rem))] overflow-auto rounded border border-hairline bg-ice-0 dark:bg-charcoal-2 shadow-z2 py-1"
        >
          <p className="px-2 pb-1 text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            Path · {path.length} tabs
          </p>
          <ol>
            {path.map((id, depth) => (
              <li key={id} style={{ paddingLeft: `${4 + Math.min(depth, 6) * 10}px` }} className="pr-1">
                {crumb(id, "w-full")}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </nav>
  );
}
