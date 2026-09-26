/**
 * WriteOutlinePane — the C5 right pane for Write mode: ONE TAB PER OUTLINE
 * BUILDING-BLOCK, each a drag-and-drop target for source documents.
 *
 * Mode contract (ratified): in writing mode this pane REPLACES the C4
 * companion in the right pane (mounted by RightPaneForMode; in the docked
 * preset it is the "WriteOutline" right-dock panel). It is NOT the
 * companion — no agent tabs here; agents stay one keystroke away on the AI
 * sidecar (mod+/), untouched.
 *
 * Each block tab shows the block's content summary, its provenance kind,
 * and its source documents: the node-trace it was born from (when
 * node-backed) plus the sources the operator ASSIGNED by dropping them here
 * (repository search hits, left reader tabs). Assignment lands in
 * blockSources.ts — the honest session-scoped bridge until the write-through
 * endpoint lands (labelled as such, never a pretend-write).
 */
import { useEffect, useState } from "react";
import { matchPath, useLocation } from "react-router-dom";

import { getDeliverable } from "../lib/api";
import type { SectionResponse } from "../lib/api";
import {
  blockDisplayText,
  getSectionBlocks,
  type OutlineBlockView,
} from "../modes/Write/writeApi";
import { useBlockSources } from "./blockSources";
import { useWriteOutline } from "./writeOutlineStore";

/** The drag payload a source document carries (repository hits, reader tabs). */
export const SOURCE_DOCUMENT_MIME = "application/x-antiek-source-document";

export interface SourceDocumentDragPayload {
  document_id: string;
  document_title: string | null;
}

interface SectionBlocks {
  section: SectionResponse;
  blocks: OutlineBlockView[];
}

/** Stable empty record for the selector (a fresh `{}` per call loops
 *  useSyncExternalStore). */
const NO_ASSIGNMENTS: Record<string, never[]> = {};

export default function WriteOutlinePane() {
  const location = useLocation();
  const deliverableId = matchPath("/write/:deliverableId", location.pathname)?.params
    .deliverableId as string | undefined;

  const [sections, setSections] = useState<SectionBlocks[]>([]);
  const [failed, setFailed] = useState(false);
  const activeBlockId = useWriteOutline((s) => s.activeBlockId);
  const setActiveBlock = useWriteOutline((s) => s.setActiveBlock);
  const setBlocks = useWriteOutline((s) => s.setBlocks);
  const assignments = useBlockSources((s) =>
    deliverableId ? (s.records[deliverableId] ?? NO_ASSIGNMENTS) : NO_ASSIGNMENTS,
  );
  const assign = useBlockSources((s) => s.assign);
  const unassign = useBlockSources((s) => s.unassign);
  const ensureDeliverable = useBlockSources((s) => s.ensureDeliverable);

  useEffect(() => {
    if (!deliverableId) {
      setSections([]);
      setBlocks([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const detail = await getDeliverable(deliverableId);
        if (cancelled || !detail) {
          if (!cancelled) setFailed(true);
          return;
        }
        const perSection = await Promise.all(
          [...detail.sections]
            .sort((a, b) => a.section_index - b.section_index)
            .map(async (section) => ({
              section,
              blocks: (await getSectionBlocks(section.section_id)).sort(
                (a, b) => a.block_index - b.block_index,
              ),
            })),
        );
        if (cancelled) return;
        setSections(perSection);
        setFailed(false);
        setBlocks(
          perSection.flatMap((s) => s.blocks.map((b) => b.outline_block_id)),
        );
        void ensureDeliverable(deliverableId);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [deliverableId, setBlocks, ensureDeliverable]);

  const flat = sections.flatMap((s) =>
    s.blocks.map((b) => ({ section: s.section, block: b })),
  );
  const active = flat.find((f) => f.block.outline_block_id === activeBlockId) ?? null;

  if (!deliverableId) {
    return (
      <section aria-label="Outline" data-write-outline className="flex h-full flex-col">
        <p className="p-3 text-sm text-ink-soft dark:text-moonlight">
          Open a piece to see its building blocks here — one tab each, ready to
          take source documents by drag-and-drop.
        </p>
      </section>
    );
  }

  return (
    <section
      aria-label="Outline"
      data-write-outline
      className="flex h-full min-h-0 min-w-0 flex-col"
    >
      <div
        role="tablist"
        aria-label="Outline blocks"
        className="flex items-center gap-1 shrink-0 overflow-x-auto border-b border-hairline px-1.5 py-1"
      >
        {flat.length === 0 && !failed ? (
          <span className="px-1 text-xs text-shadow-1 dark:text-moonlight">
            loading the outline…
          </span>
        ) : null}
        {flat.map(({ section, block }) => {
          const assigned = assignments[block.outline_block_id] ?? [];
          const isActive = block.outline_block_id === activeBlockId;
          return (
            <button
              key={block.outline_block_id}
              type="button"
              role="tab"
              aria-selected={isActive}
              data-block-tab={block.outline_block_id}
              onClick={() => setActiveBlock(block.outline_block_id)}
              onDragOver={(e) => {
                if (e.dataTransfer.types.includes(SOURCE_DOCUMENT_MIME)) e.preventDefault();
              }}
              onDrop={(e) => {
                const raw = e.dataTransfer.getData(SOURCE_DOCUMENT_MIME);
                if (!raw) return;
                e.preventDefault();
                const payload = JSON.parse(raw) as SourceDocumentDragPayload;
                assign(deliverableId, block.outline_block_id, payload);
                setActiveBlock(block.outline_block_id);
              }}
              className={`flex max-w-[150px] items-center gap-1 rounded px-1.5 py-0.5 text-xs ${
                isActive
                  ? "bg-ice-2 text-ink dark:bg-charcoal-1 dark:text-bright"
                  : "text-ink-soft hover:bg-ice-2 dark:text-moonlight dark:hover:bg-charcoal-1"
              }`}
              title={`${section.title ?? "section"} · drop a source document to assign it`}
            >
              <span className="truncate">{blockDisplayText(block)}</span>
              {assigned.length > 0 ? (
                <span className="shrink-0 font-mono text-sun-deep" aria-label={`${assigned.length} assigned sources`}>
                  ·{assigned.length}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {failed ? (
          <p className="p-3 text-sm text-ink-soft dark:text-moonlight">
            That piece isn't available right now.
          </p>
        ) : active ? (
          <BlockCard
            section={active.section}
            block={active.block}
            assigned={assignments[active.block.outline_block_id] ?? []}
            onUnassign={(documentId) =>
              unassign(deliverableId, active.block.outline_block_id, documentId)
            }
          />
        ) : (
          <p className="p-3 text-sm text-ink-soft dark:text-moonlight">
            {flat.length === 0
              ? "This piece has no blocks yet — add them in the outline on the left."
              : "Pick a block tab."}
          </p>
        )}
      </div>
    </section>
  );
}

function provenanceLabel(b: OutlineBlockView): string {
  if (b.is_user_originated || b.provenance_kind !== "graph_node") return "yours";
  return b.block_kind === "open_question" ? "question" : b.block_kind;
}

function BlockCard({
  section,
  block,
  assigned,
  onUnassign,
}: {
  section: SectionResponse;
  block: OutlineBlockView;
  assigned: { document_id: string; document_title: string | null }[];
  onUnassign: (documentId: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2 p-3" data-block-card={block.outline_block_id}>
      <div className="flex items-center gap-2">
        <span className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          {provenanceLabel(block)}
        </span>
        <span className="text-xxs text-shadow-1 dark:text-moonlight">
          {section.title ?? "untitled section"}
        </span>
      </div>
      <p className="text-sm font-serif leading-relaxed text-ink dark:text-bright">
        {blockDisplayText(block)}
      </p>
      <div>
        <p className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Source documents
        </p>
        {assigned.length === 0 ? (
          <p className="mt-1 text-xs text-ink-soft dark:text-moonlight" data-no-sources>
            None assigned yet — drag a repository hit or a left document tab onto
            this block's tab. Assignments are session state until the write-through
            endpoint lands (blockSources.ts TODO).
          </p>
        ) : (
          <ul className="mt-1 flex flex-col gap-0.5" data-assigned-sources>
            {assigned.map((a) => (
              <li key={a.document_id} className="flex items-center gap-1 text-xs">
                <span className="truncate text-ink dark:text-bright">
                  {a.document_title ?? a.document_id}
                </span>
                <button
                  type="button"
                  onClick={() => onUnassign(a.document_id)}
                  aria-label={`Remove ${a.document_title ?? a.document_id} from this block`}
                  className="shrink-0 px-0.5 text-shadow-1 hover:text-ink dark:hover:text-bright"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
