/**
 * SiblingStrip — the active tab and its siblings, herdr style, as an ARIA
 * tablist (DESIGN-MODEL §2a "Sibling strip"). It never shows the whole
 * tree; the tree panel does that.
 *
 * Tabs follow the ARIA tabs pattern with MANUAL activation: ←/→ (and
 * Home/End) move a single roving tab stop, Enter or Space opens the tab —
 * opening can navigate, so an arrow key never does. Every tab controls the
 * one document panel (the route content), which the strip labels with the
 * selected tab. A long row scrolls sideways, keeping the active tab in view;
 * edge fades mark the sides it continues on and a `+n` chip counts the tabs
 * scrolled out of view, opening the tree panel where every tab is (B3-8).
 */
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { EdgeFades, scrollStripOnWheel, useStripOverflow } from "./stripOverflow";
import type { TabLabel } from "./tabLabels";
import { DOCUMENT_PANEL_ID, KindGlyph, NumberedLabel, domIdFor } from "./tabStripParts";
import type { TabTree } from "./tabTree";

export function SiblingStrip({
  tree,
  siblings,
  activeId,
  label,
  labelOf,
  onActivate,
  onShowAll,
}: {
  tree: TabTree;
  siblings: readonly string[];
  activeId: string;
  /** The tablist's accessible name ("Top-level tabs", "Tabs under 1.3"). */
  label: string;
  labelOf: (tabId: string) => TabLabel;
  onActivate: (tabId: string) => void;
  /** The hidden-count chip's action: show every tab (the tree panel). */
  onShowAll?: () => void;
}) {
  const [roving, setRoving] = useState<string | null>(null);
  const stop = roving !== null && siblings.includes(roving) ? roving : activeId;
  const els = useRef(new Map<string, HTMLButtonElement>());
  const scroller = useRef<HTMLDivElement>(null);
  // Re-measured when the tab set changes and when titles land (they size
  // the tabs).
  const overflow = useStripOverflow(scroller, [siblings, labelOf]);
  const hidden = overflow.hiddenBefore + overflow.hiddenAfter;

  // A new selection takes the tab stop and scrolls into view.
  useEffect(() => {
    setRoving(null);
    els.current.get(activeId)?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [activeId]);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const i = siblings.indexOf(stop);
    let next: number | null = null;
    if (e.key === "ArrowRight") next = (i + 1) % siblings.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + siblings.length) % siblings.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = siblings.length - 1;
    if (next === null) return;
    e.preventDefault();
    const id = siblings[next];
    setRoving(id);
    const el = els.current.get(id);
    el?.focus();
    el?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }

  return (
    <>
    <div className="relative flex min-w-0" data-sibling-viewport>
    <div
      ref={scroller}
      role="tablist"
      aria-label={label}
      aria-orientation="horizontal"
      data-sibling-strip
      onKeyDown={onKeyDown}
      onWheel={scrollStripOnWheel}
      className="flex items-stretch gap-px min-w-0 overflow-x-auto overscroll-x-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {siblings.map((id) => {
        const tab = tree.nodes[id];
        const selected = id === activeId;
        const tabLabel = labelOf(id);
        return (
          <button
            key={id}
            ref={(el) => {
              if (el) els.current.set(id, el);
              else els.current.delete(id);
            }}
            type="button"
            role="tab"
            id={domIdFor("doctab", id)}
            aria-selected={selected}
            aria-controls={DOCUMENT_PANEL_ID}
            tabIndex={id === stop ? 0 : -1}
            data-tab-id={id}
            onClick={() => onActivate(id)}
            onFocus={() => setRoving(id)}
            draggable={tab.kind === "reader"}
            onDragStart={
              tab.kind === "reader"
                ? (e) => {
                    e.dataTransfer.setData(
                      "application/x-antiek-source-document",
                      JSON.stringify({
                        document_id: tab.ref,
                        document_title: tabLabel.source === "title" ? tabLabel.text : null,
                      }),
                    );
                    e.dataTransfer.effectAllowed = "copy";
                  }
                : undefined
            }
            className={`flex items-center gap-1.5 shrink-0 max-w-[15rem] min-w-0 h-7 px-2 text-xs border-b-2 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sun ${
              selected
                ? "border-sun bg-ice-2 dark:bg-charcoal-1 text-ink dark:text-bright"
                : "border-transparent text-ink-soft dark:text-moonlight hover:bg-ice-2/60 dark:hover:bg-charcoal-1/60 hover:text-ink dark:hover:text-bright"
            }`}
          >
            <KindGlyph tab={tab} className="text-shadow-1 dark:text-moonlight" />
            <NumberedLabel tab={tab} label={tabLabel} />
          </button>
        );
      })}
    </div>
    <EdgeFades overflow={overflow} />
    </div>
    {hidden > 0 ? (
      <button
        type="button"
        data-hidden-tabs-chip
        onClick={onShowAll}
        aria-label={`${hidden} tabs out of view: show all tabs (prefix t)`}
        title={`${hidden} more here (prefix t shows every tab)`}
        className="shrink-0 ml-1 my-1 flex items-center rounded px-1.5 font-mono text-xxs tabular-nums text-ink-soft dark:text-moonlight border border-hairline hover:bg-ice-2 dark:hover:bg-charcoal-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
      >
        +{hidden}
      </button>
    ) : null}
    </>
  );
}
