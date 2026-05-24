/**
 * BlockShelf — filtered scrollable list of ResearchBlocks.
 */

import { useMemo, useState } from "react";
import {
  LemonCard, LemonInput, LemonSelect, LemonTag,
} from "../../components/lemon";
import type { ResearchBlockSummary, ResearchSource } from "./types";
import { ALL_SOURCES, SOURCE_VISUAL } from "./types";
import { ResearchBlock } from "./ResearchBlock";

export interface BlockShelfProps {
  blocks: ResearchBlockSummary[];
  onActivate?: (block: ResearchBlockSummary) => void;
  multiSelect?: boolean;
  selectedIds?: Set<string>;
  onSelectionChange?: (selected: Set<string>) => void;
  initialSourceFilter?: ResearchSource[];
  initialSessionFilter?: string | null;
  initialSearch?: string;
  className?: string;
}

export function BlockShelf({
  blocks, onActivate, multiSelect = false,
  selectedIds, onSelectionChange,
  initialSourceFilter, initialSessionFilter, initialSearch,
  className,
}: BlockShelfProps) {
  const [sourceFilter, setSourceFilter] = useState<Set<ResearchSource>>(
    () => new Set(initialSourceFilter ?? []),
  );
  const [sessionFilter, setSessionFilter] = useState<string | null>(
    initialSessionFilter ?? null,
  );
  const [search, setSearch] = useState<string>(initialSearch ?? "");
  const [internalSelection, setInternalSelection] = useState<Set<string>>(
    () => new Set(),
  );
  const effectiveSelection = selectedIds ?? internalSelection;
  const setSelection = (next: Set<string>) => {
    if (selectedIds === undefined) setInternalSelection(next);
    onSelectionChange?.(next);
  };

  const sessionOptions = useMemo(() => {
    const set = new Set<string>();
    for (const b of blocks) if (b.session_id) set.add(b.session_id);
    return Array.from(set).sort();
  }, [blocks]);

  const filteredBlocks = useMemo(() => {
    const q = search.trim().toLowerCase();
    return blocks.filter((b) => {
      if (sourceFilter.size > 0 && !sourceFilter.has(b.source)) return false;
      if (sessionFilter !== null && b.session_id !== sessionFilter) return false;
      if (q.length > 0) {
        const haystack = `${b.title ?? ""} ${b.operator_label ?? ""}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [blocks, sourceFilter, sessionFilter, search]);

  const toggleSource = (s: ResearchSource) => {
    const next = new Set(sourceFilter);
    if (next.has(s)) next.delete(s); else next.add(s);
    setSourceFilter(next);
  };

  const handleBlockClick = (b: ResearchBlockSummary) => {
    if (multiSelect) {
      const next = new Set(effectiveSelection);
      if (next.has(b.document_id)) next.delete(b.document_id);
      else next.add(b.document_id);
      setSelection(next);
    } else {
      onActivate?.(b);
    }
  };

  return (
    <div className={["flex flex-col gap-2", className ?? ""].filter(Boolean).join(" ")}>
      <div className="sticky top-0 z-10 bg-ice-1 dark:bg-charcoal-3 p-2 border-b-2 border-ink dark:border-bright">
        <div className="flex flex-wrap gap-1 mb-2" role="group" aria-label="Filter by source">
          {ALL_SOURCES.map((s) => {
            const visual = SOURCE_VISUAL[s];
            const active = sourceFilter.has(s);
            return (
              <button
                key={s}
                type="button"
                onClick={() => toggleSource(s)}
                aria-pressed={active}
                className="outline-none focus-visible:ring-2 focus-visible:ring-sun-deep"
              >
                <LemonTag colour={active ? visual.tagColour : "muted"}>
                  {visual.label}
                </LemonTag>
              </button>
            );
          })}
        </div>
        <div className="flex gap-2 items-center">
          <LemonInput
            placeholder="Search title or label"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1"
            aria-label="Search blocks"
          />
          {sessionOptions.length > 0 && (
            <LemonSelect
              value={sessionFilter ?? "__all__"}
              onChange={(v) => setSessionFilter(v === "__all__" ? null : v)}
              options={[
                { value: "__all__", label: "All sessions" },
                ...sessionOptions.map((s) => ({ value: s, label: s })),
              ]}
              aria-label="Filter by session"
            />
          )}
        </div>
        <div className="text-xs text-shadow-2 dark:text-moonlight mt-2">
          {filteredBlocks.length} of {blocks.length} block
          {blocks.length === 1 ? "" : "s"}
          {multiSelect && effectiveSelection.size > 0 && (
            <span> · {effectiveSelection.size} selected</span>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-2 overflow-auto" role="list">
        {filteredBlocks.length === 0 ? (
          <LemonCard elevation="z1" colour="glacial">
            <div className="text-sm text-shadow-2 dark:text-moonlight">
              No pastes match. Clear filters above, or paste new research from
              the bridge's paste route.
            </div>
          </LemonCard>
        ) : (
          filteredBlocks.map((b) => (
            <div role="listitem" key={b.document_id}>
              <ResearchBlock
                block={b} size="standard"
                selected={effectiveSelection.has(b.document_id)}
                onActivate={handleBlockClick}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
