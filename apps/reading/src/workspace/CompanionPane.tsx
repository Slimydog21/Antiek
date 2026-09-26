/**
 * CompanionPane — the C4 companion right pane: AI agents as tabs.
 *
 * ONE component, TWO mounts (the BookReader discipline):
 *   - omarchy-inset preset: it IS the right inset pane's content (mounted by
 *     PanelLayout; the pane's identity per D3);
 *   - docked preset: it is the "Companion" right-dock panel's content
 *     (PanelRegistry kind "Companion", opened on first agent spawn).
 *
 * Contents: a tab strip (agent tabs: title + status glyph + close), the
 * active agent's surface, and a calm "+ new agent" affordance (pick an open
 * investigation, or start a one-shot dialogue). Tab kinds come from the
 * registry (companionRegistry.tsx) as data — islands (unit 2) and diligence
 * (unit 7) slot in later without restructuring.
 *
 * Every agent is a tab on ONE strip, in activation order. At the pane's
 * width the strip scrolls sideways (the pane's content never does): edge
 * fades mark the sides it continues on, and an overflow menu lists every
 * agent, with a search box past AGENT_MENU_SEARCH_AFTER of them. "+ new
 * agent" sits outside the scroller, so it is always reachable (B3-1). The
 * prefix n/p keys and the arrow keys reach ALL tabs (cycleAgentTab wraps).
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { EmptyState } from "../components/states";
import { useInvestigationList } from "../hooks/useInvestigationList";
import type { InvestigationSummary } from "../lib/api";
import { AGENT_TAB_KINDS } from "./companionRegistry";
import { useCompanion } from "./companionStore";
import type { AgentTabDescriptor } from "./companionStore";
import { EdgeFades, scrollStripOnWheel, useStripOverflow } from "./stripOverflow";

/** Past this many agents the overflow menu gets a search box: scanning a
 *  longer list is not navigation (DESIGN-MODEL §1, the switcher's rule). */
const AGENT_MENU_SEARCH_AFTER = 8;

/** Agent rows offered by "+ new agent": working first, then newest — a
 *  handful, calm, never the whole history. */
const NEW_AGENT_WORKING_FIRST = 6;

export default function CompanionPane() {
  const tabs = useCompanion((s) => s.tabs);
  const activeTabId = useCompanion((s) => s.activeTabId);
  const activateAgentTab = useCompanion((s) => s.activateAgentTab);
  const openAgentTab = useCompanion((s) => s.openAgentTab);
  const { investigations } = useInvestigationList();

  const summaryOf = (tab: AgentTabDescriptor): InvestigationSummary | undefined =>
    tab.kind === "research-thread"
      ? investigations.find((i) => i.investigation_id === tab.investigationId)
      : undefined;

  const active = tabs.find((t) => t.id === activeTabId) ?? null;
  const scroller = useRef<HTMLDivElement>(null);
  const tabKey = useMemo(() => tabs.map((t) => t.id).join("\u0000"), [tabs]);
  // Re-measured when the tab set changes and when questions land (they
  // title, and so size, the thread tabs).
  const overflow = useStripOverflow(scroller, [tabKey, investigations]);
  const overflowing = overflow.start || overflow.end;

  // The active agent scrolls into view (a key, the menu, a new agent).
  useEffect(() => {
    if (!activeTabId) return;
    // The whole tab, its close button included (the tab button alone left
    // the × under the end fade).
    document
      .getElementById(agentTabDomId(activeTabId))
      ?.closest("[data-agent-tab]")
      ?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [activeTabId]);

  return (
    <section
      aria-label="Companion"
      data-companion-pane
      className="flex flex-col h-full min-h-0 min-w-0 overflow-hidden"
    >
      <div
        data-agent-strip-row
        className="flex items-center gap-1 shrink-0 min-w-0 border-b border-hairline px-1.5 py-1"
      >
        <div className="relative flex-1 min-w-0">
          <div
            ref={scroller}
            role="tablist"
            aria-label="Agents"
            aria-orientation="horizontal"
            onWheel={scrollStripOnWheel}
            onKeyDown={(e) => {
              // The ARIA tabs pattern, automatic activation: an agent surface
              // swaps in place, so the arrow keys open as they move.
              if (e.ctrlKey || e.metaKey || e.altKey || tabs.length === 0) return;
              const i = Math.max(0, tabs.findIndex((t) => t.id === activeTabId));
              let next: number | null = null;
              if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
              else if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
              else if (e.key === "Home") next = 0;
              else if (e.key === "End") next = tabs.length - 1;
              if (next === null) return;
              e.preventDefault();
              const id = tabs[next].id;
              activateAgentTab(id);
              document.getElementById(agentTabDomId(id))?.focus();
            }}
            className="flex items-center gap-1 min-w-0 overflow-x-auto overscroll-x-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            {tabs.map((tab) => (
            <AgentTab
              key={tab.id}
              tab={tab}
              summary={summaryOf(tab)}
              active={tab.id === activeTabId}
              onActivate={() => activateAgentTab(tab.id)}
                onClose={() => closeAgentTabWithUndo(tab, summaryOf(tab))}
              />
            ))}
          </div>
          <EdgeFades overflow={overflow} />
        </div>
        {overflowing ? (
          <OverflowMenu
            tabs={tabs}
            hidden={overflow.hiddenBefore + overflow.hiddenAfter}
            activeTabId={activeTabId}
            summaryOf={summaryOf}
            onActivate={activateAgentTab}
          />
        ) : null}
        <NewAgentButton investigations={investigations} onPick={openAgentTab} />
      </div>

      <div
        className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden"
        id={COMPANION_PANEL_DOM_ID}
        {...(active ? { role: "tabpanel", "aria-labelledby": agentTabDomId(active.id) } : {})}
      >
        {active ? (
          <ActiveAgentSurface tab={active} summary={summaryOf(active)} />
        ) : (
          <div className="p-3" data-companion-empty>
            <EmptyState
              variant="inline"
              art={false}
              title="No agents yet"
              body="+ new agent starts a research thread or a one-shot dialogue here, beside your reading."
            />
          </div>
        )}
      </div>
    </section>
  );
}

/** The agent surface the tabs control. */
const COMPANION_PANEL_DOM_ID = "companion-agent-panel";

function agentTabDomId(tabId: string): string {
  return `agenttab-${tabId.replace(/[^A-Za-z0-9-]/g, (c) => `_${c.charCodeAt(0).toString(36)}_`)}`;
}

function ActiveAgentSurface({
  tab,
  summary,
}: {
  tab: AgentTabDescriptor;
  summary?: InvestigationSummary;
}) {
  const meta = AGENT_TAB_KINDS[tab.kind];
  const Surface = meta.Surface;
  return <Surface tab={tab} summary={summary} />;
}

/** Close an agent tab (a view act: the agent itself is untouched) behind
 *  the shared 10 s Undo, which puts it back in its place (the store's one
 *  close path, shared with prefix+shift+x). */
function closeAgentTabWithUndo(tab: AgentTabDescriptor, summary?: InvestigationSummary): void {
  const title = tab.kind === "research-thread" ? (summary?.question ?? tab.title) : tab.title;
  useCompanion.getState().closeAgentTabWithUndo(tab.id, title);
}

function AgentTab({
  tab,
  summary,
  active,
  onActivate,
  onClose,
}: {
  tab: AgentTabDescriptor;
  summary?: InvestigationSummary;
  active: boolean;
  onActivate: () => void;
  onClose: () => void;
}) {
  const meta = AGENT_TAB_KINDS[tab.kind];
  const glyph = meta.glyph(tab, summary);
  const title = tab.kind === "research-thread" ? (summary?.question ?? tab.title) : tab.title;
  // The tab IS the button (the ARIA tabs pattern: a tab's children are
  // presentational, so it can never hold a second control). Close is a mouse
  // affordance outside the tab; from the keyboard, Delete closes (never
  // Backspace, too easy to hit by accident), behind a 10 s Undo, and the
  // tab names that key to assistive tech (aria-keyshortcuts).
  return (
    <span
      role="none"
      data-agent-tab={tab.id}
      className={`group flex shrink-0 items-center max-w-[140px] rounded text-xs ${
        active ? "bg-shadow-2 text-bright" : "text-ink-soft dark:text-moonlight hover:bg-ice-2 dark:hover:bg-charcoal-1"
      }`}
    >
      <button
        type="button"
        role="tab"
        id={agentTabDomId(tab.id)}
        aria-selected={active}
        aria-controls={COMPANION_PANEL_DOM_ID}
        tabIndex={active ? 0 : -1}
        aria-keyshortcuts="Delete"
        onClick={onActivate}
        onKeyDown={(e) => {
          if (e.key === "Delete") {
            e.preventDefault();
            onClose();
          }
        }}
        className="flex items-center gap-1 min-w-0 pl-1.5 py-0.5 text-left rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
      >
        <span
          role="img"
          className={`inline-block w-2 h-2 rounded-full shrink-0 ${glyph.className}`}
          aria-label={glyph.label}
          title={glyph.label}
        />
        <span className="truncate">{title}</span>
      </button>
      <button
        type="button"
        tabIndex={-1}
        aria-hidden="true"
        data-agent-close
        onClick={onClose}
        aria-label={`Close ${title} agent (the agent itself is untouched)`}
        title={`Close ${title} (Delete). The agent itself is untouched.`}
        className="shrink-0 text-shadow-1 hover:text-bright px-1 py-0.5"
      >
        ×
      </button>
    </span>
  );
}

function OverflowMenu({
  tabs,
  hidden,
  activeTabId,
  summaryOf,
  onActivate,
}: {
  tabs: AgentTabDescriptor[];
  /** Agents scrolled out of view on the strip (the trigger's count). */
  hidden: number;
  activeTabId: string | null;
  summaryOf: (tab: AgentTabDescriptor) => InvestigationSummary | undefined;
  onActivate: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const searchable = tabs.length > AGENT_MENU_SEARCH_AFTER;

  useEffect(() => {
    if (!open) return;
    (searchable ? searchRef.current : ref.current?.querySelector<HTMLElement>("[role='menuitem']"))?.focus();
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    // The menu's own Esc (a transient overlay: one Esc, one handler).
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      e.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, searchable]);

  const titleOf = (tab: AgentTabDescriptor) =>
    tab.kind === "research-thread" ? (summaryOf(tab)?.question ?? tab.title) : tab.title;
  const q = query.trim().toLowerCase();
  const shown = q ? tabs.filter((t) => titleOf(t).toLowerCase().includes(q)) : tabs;

  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        ref={triggerRef}
        type="button"
        data-agent-overflow
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`All agents (${tabs.length}${hidden > 0 ? `, ${hidden} out of view` : ""})`}
        title="All agents"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-0.5 text-xs text-shadow-1 dark:text-moonlight px-1.5 py-0.5 rounded hover:bg-ice-2 dark:hover:bg-charcoal-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
      >
        <span aria-hidden="true">⋯</span>
        {hidden > 0 ? <span className="font-mono text-xxs tabular-nums">{hidden}</span> : null}
      </button>
      {open ? (
        <div
          role="menu"
          aria-label="All agents"
          data-esc-overlay=""
          className="absolute right-0 top-full mt-1 z-10 w-[min(16rem,calc(100vw-2rem))] rounded border border-hairline bg-ice-0 dark:bg-charcoal-2 shadow-z2 dark:shadow-z2-night py-1"
        >
          {searchable ? (
            <div className="px-1.5 pb-1">
              <input
                ref={searchRef}
                type="search"
                aria-label="Find an agent"
                placeholder="Find an agent"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full rounded border border-hairline bg-transparent px-2 py-1 text-xs text-ink dark:text-bright placeholder:text-shadow-1 outline-none focus-visible:ring-2 focus-visible:ring-sun"
              />
            </div>
          ) : null}
          <div className="max-h-[50vh] overflow-y-auto">
            {shown.map((tab) => {
              const meta = AGENT_TAB_KINDS[tab.kind];
              const glyph = meta.glyph(tab, summaryOf(tab));
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onActivate(tab.id);
                    setOpen(false);
                    setQuery("");
                  }}
                  className="w-full flex items-center gap-1.5 px-2 py-1 text-xs text-left text-ink dark:text-bright hover:bg-ice-2 dark:hover:bg-charcoal-1 focus-visible:bg-ice-2 dark:focus-visible:bg-charcoal-1 focus-visible:outline-none"
                >
                  <span aria-hidden="true" className={`inline-block w-2 h-2 rounded-full shrink-0 ${glyph.className}`} />
                  <span className="truncate">{titleOf(tab)}</span>
                  {tab.id === activeTabId ? (
                    <>
                      <span aria-hidden="true" className="ml-auto text-shadow-1">·</span>
                      <span className="sr-only">(active)</span>
                    </>
                  ) : null}
                </button>
              );
            })}
            {shown.length === 0 ? (
              <p className="px-2 py-1 text-xxs text-shadow-1 dark:text-moonlight">No agent matches.</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function NewAgentButton({
  investigations,
  onPick,
}: {
  investigations: InvestigationSummary[];
  onPick: (input: { kind: "research-thread" | "dialogue"; investigationId?: string; title?: string }) => string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Working first, then newest — a handful, not the whole history.
  const working = investigations.filter((i) => i.status === "in_progress");
  const rest = investigations.filter((i) => i.status !== "in_progress");
  const offered = [...working, ...rest].slice(0, NEW_AGENT_WORKING_FIRST);

  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        type="button"
        aria-label="New agent"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="text-xs text-shadow-1 dark:text-moonlight px-1.5 py-0.5 rounded hover:bg-ice-2 dark:hover:bg-charcoal-1 whitespace-nowrap"
      >
        + new agent
      </button>
      {open ? (
        <div
          role="menu"
          data-esc-overlay=""
          aria-label="New agent"
          className="absolute right-0 top-full mt-1 z-10 min-w-[220px] max-w-[280px] rounded border border-hairline bg-ice-0 dark:bg-charcoal-2 shadow-z2 py-1"
        >
          <button
            type="button"
            role="menuitem"
            className="w-full px-2 py-1 text-xs text-left text-ink dark:text-bright hover:bg-ice-2 dark:hover:bg-charcoal-1"
            onClick={() => {
              onPick({ kind: "dialogue" });
              setOpen(false);
            }}
          >
            One-shot dialogue
          </button>
          {offered.length > 0 ? (
            <p className="px-2 pt-1 text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              Research threads
            </p>
          ) : null}
          {offered.map((inv) => (
            <button
              key={inv.investigation_id}
              type="button"
              role="menuitem"
              className="w-full px-2 py-1 text-xs text-left text-ink dark:text-bright hover:bg-ice-2 dark:hover:bg-charcoal-1 truncate"
              onClick={() => {
                onPick({
                  kind: "research-thread",
                  investigationId: inv.investigation_id,
                  title: inv.question ?? undefined,
                });
                setOpen(false);
              }}
            >
              {inv.question ?? inv.investigation_id}
            </button>
          ))}
          {offered.length === 0 ? (
            <p className="px-2 py-1 text-xxs text-shadow-1 dark:text-moonlight">
              No research threads yet.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
