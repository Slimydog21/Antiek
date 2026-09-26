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
 * The strip shows up to COMPANION_MAX_VISIBLE_TABS tabs in activation
 * order; the rest collapse into a ⋯ menu. Overflow is visual only — the
 * prefix n/p keys cycle ALL tabs (companionStore.cycleAgentTab wraps).
 */
import { useEffect, useRef, useState } from "react";

import { EmptyState } from "../components/states";
import { useInvestigationList } from "../hooks/useInvestigationList";
import type { InvestigationSummary } from "../lib/api";
import { AGENT_TAB_KINDS } from "./companionRegistry";
import { useCompanion } from "./companionStore";
import type { AgentTabDescriptor } from "./companionStore";

/** Tabs on the strip before the ⋯ menu takes the rest. Five keeps every tab
 *  legible at the pane's 320px width (title + glyph + close); more is what
 *  the menu is for. */
const COMPANION_MAX_VISIBLE_TABS = 5;

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
  const visible = tabs.slice(0, COMPANION_MAX_VISIBLE_TABS);
  const overflowed = tabs.slice(COMPANION_MAX_VISIBLE_TABS);

  return (
    <section
      aria-label="Companion"
      data-companion-pane
      className="flex flex-col h-full min-h-0 min-w-0"
    >
      <div className="flex items-center gap-1 shrink-0 border-b border-hairline px-1.5 py-1">
        <div
          role="tablist"
          aria-label="Agents"
          aria-orientation="horizontal"
          onKeyDown={(e) => {
            // The ARIA tabs pattern, automatic activation: an agent surface
            // swaps in place, so the arrow keys open as they move.
            if (e.ctrlKey || e.metaKey || e.altKey || visible.length === 0) return;
            const i = Math.max(0, visible.findIndex((t) => t.id === activeTabId));
            let next: number | null = null;
            if (e.key === "ArrowRight") next = (i + 1) % visible.length;
            else if (e.key === "ArrowLeft") next = (i - 1 + visible.length) % visible.length;
            else if (e.key === "Home") next = 0;
            else if (e.key === "End") next = visible.length - 1;
            if (next === null) return;
            e.preventDefault();
            const id = visible[next].id;
            activateAgentTab(id);
            document.getElementById(agentTabDomId(id))?.focus();
          }}
          className="flex items-center gap-1 min-w-0"
        >
          {visible.map((tab) => (
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
        {overflowed.length > 0 ? (
          <OverflowMenu
            tabs={overflowed}
            activeTabId={activeTabId}
            summaryOf={summaryOf}
            onActivate={activateAgentTab}
          />
        ) : null}
        <NewAgentButton investigations={investigations} onPick={openAgentTab} />
      </div>

      <div
        className="flex-1 min-h-0 overflow-auto"
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
      className={`group flex items-center max-w-[140px] rounded text-xs ${
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
  activeTabId,
  summaryOf,
  onActivate,
}: {
  tabs: AgentTabDescriptor[];
  activeTabId: string | null;
  summaryOf: (tab: AgentTabDescriptor) => InvestigationSummary | undefined;
  onActivate: (id: string) => void;
}) {
  return (
    <details className="relative" data-companion-overflow>
      <summary
        className="list-none cursor-pointer text-xs text-shadow-1 dark:text-moonlight px-1.5 py-0.5 rounded hover:bg-ice-2 dark:hover:bg-charcoal-1"
        aria-label={`${tabs.length} more agents`}
      >
        ⋯
      </summary>
      <div
        role="menu"
        data-esc-overlay=""
        className="absolute right-0 top-full mt-1 z-10 min-w-[180px] rounded border border-hairline bg-ice-0 dark:bg-charcoal-2 shadow-z2 py-1"
      >
        {tabs.map((tab) => {
          const meta = AGENT_TAB_KINDS[tab.kind];
          const glyph = meta.glyph(tab, summaryOf(tab));
          const title =
            tab.kind === "research-thread"
              ? (summaryOf(tab)?.question ?? tab.title)
              : tab.title;
          return (
            <button
              key={tab.id}
              type="button"
              role="menuitem"
              onClick={onActivate.bind(null, tab.id)}
              className="w-full flex items-center gap-1.5 px-2 py-1 text-xs text-left text-ink dark:text-bright hover:bg-ice-2 dark:hover:bg-charcoal-1"
            >
              <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${glyph.className}`} />
              <span className="truncate">{title}</span>
              {tab.id === activeTabId ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span className="sr-only">(active)</span>
                </>
              ) : null}
            </button>
          );
        })}
      </div>
    </details>
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
    <div className="relative ml-auto" ref={ref}>
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
