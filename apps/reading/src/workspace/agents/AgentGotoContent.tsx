/**
 * agents/AgentGotoContent.tsx — SPR-10 M5 (lazy): every agent grouped by
 * project, herdr B6 keys. Element-scoped handlers only (no window or
 * document key listener; the census): on the LIST, `/` focuses the search,
 * b/w/i/d set the state filter and a clears it, j/k/arrows move, Enter
 * lands on the row through focusAgent and closes. In the SEARCH, typed
 * letters filter by text, ArrowDown leaves for the list, Esc returns to
 * the list (preventDefault, so LemonModal keeps the dialog open).
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { LemonModal } from "../../components/lemon/LemonModal";
import { useSeenVersion } from "../../hooks/useSeenVersion";
import { attentionFor, useAgentStatusStore, useRunEntries } from "./agentStatusStore";
import { FILTER_KEYS, applyFilter, buildGotoRows, moveSelection, type GotoFilter, type GotoPos, type GotoRow } from "./agentGotoModel";
import { focusAgent } from "./focusAgent";
import { StatusDot } from "./StatusDot";

const FILTERS: readonly { key: string; filter: GotoFilter; label: string }[] = [
  { key: "a", filter: "all", label: "all" },
  { key: "b", filter: "blocked", label: "blocked" },
  { key: "w", filter: "working", label: "working" },
  { key: "i", filter: "idle", label: "idle" },
  { key: "d", filter: "done", label: "done" },
];

function rowDomId(runId: string): string {
  return `agentgoto-${runId.replace(/[^A-Za-z0-9-]/g, (c) => `_${c.charCodeAt(0).toString(36)}_`)}`;
}

export default function AgentGotoContent({ onClose }: { onClose: () => void }) {
  const entries = useRunEntries();
  const raw = useAgentStatusStore((s) => s.raw);
  useSeenVersion();
  const [filter, setFilter] = useState<GotoFilter>("all");
  const [query, setQuery] = useState("");
  const [pos, setPos] = useState<GotoPos>({ group: 0, row: 0 });
  const listRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const groups = useMemo(
    () => applyFilter(buildGotoRows(entries.values(), (e) => attentionFor(e, raw.get(e.runId))), filter, query),
    [entries, raw, filter, query],
  );
  const current = groups[pos.group]?.rows[pos.row] ?? groups[0]?.rows[0];

  // Focus the list once mounted (LemonModal's trap focuses its first
  // focusable, which is the list in a browser; this covers environments
  // that cannot lay out).
  useEffect(() => {
    const id = window.setTimeout(() => listRef.current?.focus(), 0);
    return () => window.clearTimeout(id);
  }, []);

  // Give focus back on close (NewTabPickerContent's pattern).
  useLayoutEffect(() => {
    const opener = document.activeElement;
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  const go = (row: GotoRow | undefined) => {
    if (!row) return;
    onClose();
    void focusAgent({
      runId: row.runId,
      viewId: row.viewId,
      viewOpen: row.viewOpen,
      ...(row.investigationId !== undefined ? { investigationId: row.investigationId } : {}),
      title: row.title,
      kind: row.kind,
    });
  };

  const onListKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "/") {
      e.preventDefault();
      searchRef.current?.focus();
      return;
    }
    const f = FILTER_KEYS[e.key];
    if (f !== undefined) {
      e.preventDefault();
      setFilter(f);
      setPos({ group: 0, row: 0 });
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      go(current);
      return;
    }
    const next = moveSelection(groups, pos, e.key);
    if (next.group !== pos.group || next.row !== pos.row || ["j", "k", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(e.key)) {
      e.preventDefault();
      setPos(next);
    }
  };

  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      listRef.current?.focus();
    } else if (e.key === "Escape") {
      e.preventDefault();
      listRef.current?.focus();
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(current);
    }
  };

  return (
    <LemonModal open onClose={onClose} title="Agents" size="sm">
      <div data-keymap-owner="agents.goto">
        <div
          ref={listRef}
          role="listbox"
          aria-label="Agents"
          tabIndex={0}
          aria-activedescendant={current ? rowDomId(current.runId) : undefined}
          onKeyDown={onListKeyDown}
          className="max-h-[60vh] overflow-auto outline-none focus-visible:ring-2 focus-visible:ring-sun rounded"
        >
          {groups.length === 0 ? (
            <p className="px-2 py-3 text-sm text-shadow-1 dark:text-moonlight">
              {query.trim() || filter !== "all" ? "No agent matches." : "No agents yet."}
            </p>
          ) : (
            groups.map((g, gi) => (
              <section key={g.key || "everywhere"} aria-label={g.title} className="mb-2 last:mb-0">
                <h3 className="px-1 pb-1 font-mono text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">{g.title}</h3>
                {g.rows.map((row, ri) => {
                  const isSel = current?.runId === row.runId;
                  return (
                    <div
                      key={row.runId}
                      id={rowDomId(row.runId)}
                      role="option"
                      aria-selected={isSel}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => { setPos({ group: gi, row: ri }); go(row); }}
                      className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm cursor-pointer ${
                        isSel ? "bg-shadow-2 text-bright" : "text-ink dark:text-bright hover:bg-ice-2 dark:hover:bg-charcoal-1"
                      }`}
                    >
                      <StatusDot status={row.status} reason={row.reason} variant="dot" word="visible" />
                      <span data-row-title className="min-w-0 flex-1 truncate">{row.title}</span>
                      <span className="shrink-0 font-mono text-xxs uppercase tracking-wider opacity-80">{row.viewOpen ? "focus" : "open"}</span>
                    </div>
                  );
                })}
              </section>
            ))
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xxs text-shadow-1 dark:text-moonlight">
          {FILTERS.map((f) => (
            <span key={f.filter} data-filter-active={filter === f.filter ? f.filter : undefined} className={filter === f.filter ? "text-ink dark:text-bright underline underline-offset-2" : undefined}>
              <kbd>{f.key}</kbd> {f.label}
            </span>
          ))}
          <span><kbd>/</kbd> search</span>
          <span><kbd>↵</kbd> go</span>
        </div>
        <input
          ref={searchRef}
          type="search"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setPos({ group: 0, row: 0 }); }}
          onKeyDown={onSearchKeyDown}
          aria-label="Search agents"
          placeholder="Search agents"
          className="mt-2 w-full rounded border border-hairline bg-ice-0 px-2.5 py-1.5 text-sm text-ink placeholder:text-shadow-1 dark:bg-charcoal-1 dark:text-bright dark:placeholder:text-moonlight focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
        />
      </div>
    </LemonModal>
  );
}
