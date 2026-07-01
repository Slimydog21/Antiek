/**
 * Canvas — the DRW "organism" view (Living Roadmap SPR-03 M2). Renders an
 * investigation's insight + open-question graph nodes as draggable BlockCards
 * on a FREE 2D coordinate space, with lineage edges (M3) and typed-event-backed
 * theme regions (M4). A region is created by selecting blocks and assigning a
 * label; membership rides the same `block.positioned` event as
 * coordinates, so there is still one event-log source of truth.
 *
 * ── BOUNDARY: this is a FREE canvas, NOT a reading-physics consumer ──
 * The canvas places blocks in its own pixel coordinate space. It deliberately
 * imports NOTHING from `src/reading-physics/` — that module's `layout-map`
 * anchors widgets to positions INSIDE a document (a different concern: in-text
 * augmentations). Wiring the reading-physics layout-map into canvas positions
 * would be a category error. A future maintainer: keep canvas geometry local
 * (canvasLayout.ts) and the reading-physics map for in-document widgets.
 * (The reading_physics_check.py lint only guards reading-physics modules, so
 * this file is correctly outside its scope; this comment is the human guard.)
 *
 * ── PERSISTENCE: position is a typed event, never a side store (defensibility) ──
 * Each drag-end appends ONE `block.positioned` typed event through
 * `postTypedEvent → /events/typed` (the single-writer funnel). It is NOT a
 * browser-local / Zustand side store. The reason is the DuckDB single-writer
 * invariant (CLAUDE.md §1, runtime/db_lock): a canvas position is graph
 * view-state, and the only sanctioned writer is the host funnel. A client
 * side-store would be a second source of truth that can diverge. We re-derive
 * positions on mount by replaying the persisted events (`getTrajectory` →
 * `replayPositions`), so the event log is the single source of truth.
 * Would-reverse-it: if the operator decided canvas position should be PURELY
 * ephemeral view-state never persisted at all, this whole event would be
 * dropped (and React local state alone would hold position for the session).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  getDistillation,
  getTrajectory,
  postTypedEvent,
} from "../../../lib/api";
import type { DistilledNode } from "../../../lib/api";
import type { Event } from "../../../generated/types";
import AIActionFailure from "../../../shared/AIActionFailure";
import Thinking from "../../../shared/Thinking";

import BlockCard from "./BlockCard";
import Edges from "./Edges";
import ThemeRegion, { type ThemeRegionData } from "./ThemeRegion";
import {
  BLOCK_HEIGHT,
  BLOCK_WIDTH,
  clampBlockToViewport,
  replayPositions,
  resolvePositions,
  type BlockPosition,
} from "./canvasLayout";

export interface CanvasProps {
  investigationId: string;
  /** Click-to-detail seam for SPR-04 (anchors the float-menu in block detail).
   *  Optional. */
  onOpenDetail?: (node: DistilledNode) => void;
  /** "Cite source" seam (SPR-05 one door): opens the node's source document in
   *  the ONE Reader. Threaded down to each BlockCard's onCiteSource. Optional —
   *  when absent a card shows the source's presence without a click target. */
  onCiteSource?: (node: DistilledNode) => void;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; reason: string | null }
  | {
      kind: "loaded";
      insights: DistilledNode[];
      questions: DistilledNode[];
      positions: Map<string, BlockPosition>;
    };

export default function Canvas({ investigationId, onOpenDetail, onCiteSource }: CanvasProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      // Two reads: the graph nodes (distill) + the position events (trajectory).
      // Positions are re-derived from the event log — NOT a side store.
      const [distill, trajectory] = await Promise.all([
        getDistillation(investigationId),
        getTrajectory(investigationId),
      ]);
      const nodes = [...distill.insights, ...distill.questions];
      const nodeIds = nodes.map((n) => n.node_id);
      const persisted = replayPositions(trajectory.events as Event[]);
      const positions = resolvePositions(nodeIds, persisted);
      setState({
        kind: "loaded",
        insights: distill.insights,
        questions: distill.questions,
        positions,
      });
    } catch (e) {
      const reason = e instanceof ApiError ? e.body || null : null;
      setState({ kind: "error", reason });
    }
  }, [investigationId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return (
      <div className="flex items-center gap-2 px-4 py-8" role="status" aria-live="polite">
        <Thinking size={28} label="Laying out the organism" status="reading the graph…" />
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="px-4 py-8">
        <AIActionFailure
          title="Couldn’t load the canvas"
          reason={state.reason}
          onRetry={() => void load()}
        />
      </div>
    );
  }

  return (
    <LoadedCanvas
      investigationId={investigationId}
      insights={state.insights}
      questions={state.questions}
      initialPositions={state.positions}
      onOpenDetail={onOpenDetail}
      onCiteSource={onCiteSource}
    />
  );
}

function LoadedCanvas({
  investigationId,
  insights,
  questions,
  initialPositions,
  onOpenDetail,
  onCiteSource,
}: {
  investigationId: string;
  insights: DistilledNode[];
  questions: DistilledNode[];
  initialPositions: Map<string, BlockPosition>;
  onOpenDetail?: (node: DistilledNode) => void;
  onCiteSource?: (node: DistilledNode) => void;
}) {
  const nodes = useMemo(() => [...insights, ...questions], [insights, questions]);
  // Position state seeds from the replayed events, then tracks live drags.
  // This React state is NOT a persistence store — it's transient view state
  // for the in-flight drag; the durable truth is the event log. Every
  // drag-END re-appends an event so a reload re-derives the same coordinates.
  const [positions, setPositions] = useState<Map<string, BlockPosition>>(initialPositions);
  const [selectedNodeIds, setSelectedNodeIds] = useState<Set<string>>(() => new Set());
  const [regionLabel, setRegionLabel] = useState("");

  // Canvas extent: large enough to hold the furthest block + margin so edges
  // have room and a deep branch doesn't clip (rigor #3).
  const extent = useMemo(() => {
    let maxX = 800;
    let maxY = 600;
    for (const p of positions.values()) {
      maxX = Math.max(maxX, p.x + BLOCK_WIDTH + 120);
      maxY = Math.max(maxY, p.y + BLOCK_HEIGHT + 160);
    }
    return { width: maxX, height: maxY };
  }, [positions]);

  const regions = useMemo<ThemeRegionData[]>(() => {
    const grouped = new Map<string, ThemeRegionData>();
    for (const p of positions.values()) {
      if (!p.regionId) continue;
      const existing = grouped.get(p.regionId);
      if (existing) {
        grouped.set(p.regionId, {
          ...existing,
          label: existing.label || p.regionLabel,
          members: [...existing.members, p],
        });
      } else {
        grouped.set(p.regionId, {
          regionId: p.regionId,
          label: p.regionLabel,
          members: [p],
        });
      }
    }
    return [...grouped.values()];
  }, [positions]);

  const selectedCount = selectedNodeIds.size;

  const toggleSelected = useCallback((nodeId: string) => {
    setSelectedNodeIds((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }, []);

  const groupSelected = useCallback(() => {
    if (selectedNodeIds.size < 2) return;
    const label = regionLabel.trim();
    const regionId = `theme-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    const updates: Array<{ nodeId: string; next: BlockPosition }> = [];
    for (const nodeId of selectedNodeIds) {
      const p = positions.get(nodeId);
      if (!p) continue;
      updates.push({
        nodeId,
        next: {
          ...p,
          regionId,
          regionLabel: label || null,
          persisted: true,
        },
      });
    }
    if (updates.length < 2) return;
    setPositions((prev) => {
      const next = new Map(prev);
      for (const update of updates) {
        next.set(update.nodeId, update.next);
      }
      return next;
    });
    setSelectedNodeIds(new Set());
    setRegionLabel("");
    for (const update of updates) {
      void postTypedEvent({
        investigation_id: investigationId,
        payload: {
          action_type: "block.positioned",
          node_id: update.nodeId,
          x: update.next.x,
          y: update.next.y,
          region_id: update.next.regionId,
          region_label: update.next.regionLabel,
        },
      }).catch(() => {
        // Same persistence contract as drag: if the event fails, reload falls
        // back to the event log rather than a second local source of truth.
      });
    }
  }, [investigationId, positions, regionLabel, selectedNodeIds]);

  const ungroupSelected = useCallback(() => {
    if (selectedNodeIds.size === 0) return;
    const updates: Array<{ nodeId: string; next: BlockPosition }> = [];
    for (const nodeId of selectedNodeIds) {
      const p = positions.get(nodeId);
      if (!p || !p.regionId) continue;
      updates.push({
        nodeId,
        next: {
          ...p,
          regionId: null,
          regionLabel: null,
          persisted: true,
        },
      });
    }
    if (updates.length === 0) return;
    setPositions((prev) => {
      const next = new Map(prev);
      for (const update of updates) {
        next.set(update.nodeId, update.next);
      }
      return next;
    });
    setSelectedNodeIds(new Set());
    for (const update of updates) {
      void postTypedEvent({
        investigation_id: investigationId,
        payload: {
          action_type: "block.positioned",
          node_id: update.nodeId,
          x: update.next.x,
          y: update.next.y,
          region_id: null,
          region_label: null,
        },
      }).catch(() => {
        // Same persistence contract as grouping and drag.
      });
    }
  }, [investigationId, positions, selectedNodeIds]);

  // Empty graph → honest empty state, never a blank void (rigor #3).
  if (nodes.length === 0) {
    return (
      <div className="px-4 py-10 text-center" data-testid="canvas-empty">
        <p className="font-serif text-[14px] text-ink dark:text-bright">
          Nothing to lay out yet.
        </p>
        <p className="mt-1 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          This research distilled no insights or open questions — when it does,
          they’ll appear here as blocks.
        </p>
      </div>
    );
  }

  return (
    <div
      data-testid="block-canvas"
      className="relative h-full w-full overflow-auto bg-ice-1 dark:bg-charcoal-1"
    >
      <div className="relative" style={{ width: extent.width, height: extent.height }}>
        {selectedCount > 0 && (
          <div className="absolute left-3 top-3 z-20 inline-flex items-center gap-2 rounded-hog border border-edge bg-ice-0/95 px-2 py-1 shadow-sm dark:bg-charcoal-2/95">
            <span className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              {selectedCount} selected
            </span>
            <input
              aria-label="Theme label"
              value={regionLabel}
              onChange={(e) => setRegionLabel(e.target.value)}
              placeholder="Theme label"
              className="h-7 w-32 rounded-hog border border-edge bg-transparent px-2 font-mono text-[11px] text-ink outline-none placeholder:text-shadow-1 dark:text-bright"
            />
            <button
              type="button"
              disabled={selectedCount < 2}
              onClick={groupSelected}
              className="h-7 rounded-hog border border-aurora px-2 font-mono text-[10px] uppercase tracking-wider text-aurora disabled:cursor-not-allowed disabled:border-edge disabled:text-shadow-1"
            >
              Group
            </button>
            <button
              type="button"
              onClick={ungroupSelected}
              className="h-7 rounded-hog border border-edge px-2 font-mono text-[10px] uppercase tracking-wider text-shadow-1"
            >
              Ungroup
            </button>
            <button
              type="button"
              onClick={() => setSelectedNodeIds(new Set())}
              className="h-7 rounded-hog border border-edge px-2 font-mono text-[10px] uppercase tracking-wider text-shadow-1"
            >
              Clear
            </button>
          </div>
        )}

        {regions.map((region) => (
          <ThemeRegion key={region.regionId} region={region} />
        ))}

        {/* M3 lineage edges sit behind the blocks. */}
        <Edges
          questions={questions}
          positions={positions}
          width={extent.width}
          height={extent.height}
        />

        {/* M1 + M2: each node is a draggable, absolutely-positioned block. */}
        {nodes.map((node) => {
          const p = positions.get(node.node_id);
          if (!p) return null;
          return (
            <DraggableBlock
              key={node.node_id}
              node={node}
              pos={p}
              investigationId={investigationId}
              onOpenDetail={onOpenDetail}
              onCiteSource={onCiteSource}
              selected={selectedNodeIds.has(node.node_id)}
              onToggleSelected={toggleSelected}
              onCommit={(next) =>
                setPositions((prev) => {
                  const m = new Map(prev);
                  m.set(node.node_id, next);
                  return m;
                })
              }
            />
          );
        })}
      </div>
    </div>
  );
}

/**
 * One draggable block. Drag is hand-rolled with pointer-capture, REUSING the
 * proven pattern from `src/workspace/PanelHandle.tsx` (lines 39–80): capture
 * the pointer on down, accumulate deltas on move, clamp to the viewport so the
 * block can never be lost off-screen (`clampBlockToViewport`, modeled on
 * `clampRectToViewport`, src/workspace/panelLayoutLogic.ts:18). On pointer-up
 * we persist the final position as a typed event (the single-writer funnel),
 * NOT a side store.
 */
function DraggableBlock({
  node,
  pos,
  investigationId,
  onOpenDetail,
  onCiteSource,
  selected,
  onToggleSelected,
  onCommit,
}: {
  node: DistilledNode;
  pos: BlockPosition;
  investigationId: string;
  onOpenDetail?: (node: DistilledNode) => void;
  onCiteSource?: (node: DistilledNode) => void;
  selected: boolean;
  onToggleSelected: (nodeId: string) => void;
  onCommit: (next: BlockPosition) => void;
}) {
  // Live drag state lives in refs (no re-render churn mid-drag) + a local
  // state mirror for the rendered transform.
  const dragOrigin = useRef<{ pointerX: number; pointerY: number; x: number; y: number } | null>(null);
  const moved = useRef(false);
  const [live, setLive] = useState<{ x: number; y: number }>({ x: pos.x, y: pos.y });

  // Keep the rendered position in sync when the resolved position changes
  // (e.g. a reload re-derives from events).
  useEffect(() => {
    setLive({ x: pos.x, y: pos.y });
  }, [pos.x, pos.y]);

  const viewport = () => ({
    width: typeof window !== "undefined" ? window.innerWidth : 1440,
    height: typeof window !== "undefined" ? window.innerHeight : 900,
  });

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    // Don't start a drag from an interactive control inside the card.
    const target = e.target as HTMLElement;
    if (target.closest("button,input")) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragOrigin.current = { pointerX: e.clientX, pointerY: e.clientY, x: live.x, y: live.y };
    moved.current = false;
  }, [live.x, live.y]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const o = dragOrigin.current;
    if (!o) return;
    const dx = e.clientX - o.pointerX;
    const dy = e.clientY - o.pointerY;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) moved.current = true;
    const clamped = clampBlockToViewport({ x: o.x + dx, y: o.y + dy }, viewport());
    setLive(clamped);
  }, []);

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    const o = dragOrigin.current;
    dragOrigin.current = null;
    if (!o) return;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // jsdom / no-capture environments — harmless.
    }
    // No real movement → not a drag; leave persistence untouched (a click
    // is handled by BlockCard's detail button instead).
    if (!moved.current) return;

    const next: BlockPosition = {
      x: live.x,
      y: live.y,
      regionId: pos.regionId,
      regionLabel: pos.regionLabel,
      persisted: true,
    };
    onCommit(next);

    // Persist via the single-writer typed-event funnel (NOT a side store).
    // Fire-and-forget: the next reload re-derives from the event log, so a
    // failed POST simply means the drag didn't stick — no optimistic lie that
    // survives a refresh, and no second source of truth to reconcile.
    void postTypedEvent({
      investigation_id: investigationId,
      payload: {
        action_type: "block.positioned",
        node_id: node.node_id,
        x: live.x,
        y: live.y,
        region_id: pos.regionId,
        region_label: pos.regionLabel,
      },
    }).catch(() => {
      // Swallow — authoritative state is the event log on next load.
    });
  }, [investigationId, live.x, live.y, node.node_id, onCommit, pos.regionId, pos.regionLabel]);

  const onClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest("button,input")) return;
    if (!e.shiftKey) return;
    e.preventDefault();
    onToggleSelected(node.node_id);
  }, [node.node_id, onToggleSelected]);

  return (
    <div
      data-draggable-block={node.node_id}
      data-selected={selected ? "true" : "false"}
      className={`absolute cursor-grab touch-none select-none active:cursor-grabbing ${
        selected ? "outline outline-2 outline-aurora outline-offset-2" : ""
      }`}
      style={{ left: live.x, top: live.y, width: BLOCK_WIDTH, zIndex: 1 }}
      onClick={onClick}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <input
        type="checkbox"
        aria-label={`Select ${node.kind} block`}
        checked={selected}
        onChange={() => onToggleSelected(node.node_id)}
        onPointerDown={(e) => e.stopPropagation()}
        className="absolute left-2 top-2 z-10 h-4 w-4 accent-aurora"
      />
      <BlockCard node={node} onOpenDetail={onOpenDetail} onCiteSource={onCiteSource} />
    </div>
  );
}
