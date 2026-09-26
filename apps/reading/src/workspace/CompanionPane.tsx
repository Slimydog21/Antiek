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
  const closeAgentTab = useCompanion((s) => s.closeAgentTab);
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
      <div
        role="tablist"
        aria-label="Agents"
        className="flex items-center gap-1 shrink-0 border-b border-hairline px-1.5 py-1"
      >
        {visible.map((tab) => (
          <AgentTab
            key={tab.id}
            tab={tab}
            summary={summaryOf(tab)}
            active={tab.id === activeTabId}
            onActivate={() => activateAgentTab(tab.id)}
            onClose={() => closeAgentTab(tab.id)}
          />
        ))}
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

      <div className="flex-1 min-h-0 overflow-auto">
        {active ? (
          <ActiveAgentSurface tab={active} summary={summaryOf(active)} />
        ) : (
          <p className="p-3 text-sm text-ink-soft dark:text-moonlight" data-companion-empty>
            No agents yet. <span className="text-shadow-1">+ new agent</span> starts a
            research thread or a one-shot dialogue here — beside your reading.
          </p>
        )}
      </div>
    </section>
  );
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
  return (
    <div
      role="tab"
      aria-selected={active}
      data-agent-tab={tab.id}
      className={`group flex items-center gap-1 max-w-[140px] rounded px-1.5 py-0.5 text-xs cursor-default ${
        active ? "bg-shadow-2 text-bright" : "text-ink-soft dark:text-moonlight hover:bg-ice-2 dark:hover:bg-charcoal-1"
      }`}
    >
      <button
        type="button"
        onClick={onActivate}
        className="flex items-center gap-1 min-w-0 text-left"
        aria-label={`Activate ${title}`}
      >
        <span
          className={`inline-block w-2 h-2 rounded-full shrink-0 ${glyph.className}`}
          aria-label={glyph.label}
          title={glyph.label}
        />
        <span className="truncate">{title}</span>
      </button>
      <button
        type="button"
        onClick={onClose}
        aria-label={`Close ${title} agent (the agent itself is untouched)`}
        className="shrink-0 text-shadow-1 hover:text-bright px-0.5"
      >
        ×
      </button>
    </div>
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
              {tab.id === activeTabId ? <span aria-label="active">·</span> : null}
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
