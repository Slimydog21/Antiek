/**
 * Canvas — the DRW "organism" view (Living Roadmap SPR-03 M2). Renders an
 * investigation's insight + open-question graph nodes as draggable BlockCards
 * on a FREE 2D coordinate space, with lineage edges (M3). Theme grouping (M4)
 * is DEFERRED: the canvas renders blocks + lineage edges only. The
 * `region_id`/`region_label` event fields and the `ThemeRegion` component are
 * a reserved, unmounted forward-compatible seam (no region-assign gesture
 * shipped in SPR-03) — see docs/decisions/spr-03-block-canvas-lineage.md.
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

export default function Canvas({ investigationId, onOpenDetail }: CanvasProps) {
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
    />
  );
}

function LoadedCanvas({
  investigationId,
  insights,
  questions,
  initialPositions,
  onOpenDetail,
}: {
  investigationId: string;
  insights: DistilledNode[];
  questions: DistilledNode[];
  initialPositions: Map<string, BlockPosition>;
  onOpenDetail?: (node: DistilledNode) => void;
}) {
  const nodes = useMemo(() => [...insights, ...questions], [insights, questions]);
  // Position state seeds from the replayed events, then tracks live drags.
  // This React state is NOT a persistence store — it's transient view state
  // for the in-flight drag; the durable truth is the event log. Every
  // drag-END re-appends an event so a reload re-derives the same coordinates.
  const [positions, setPositions] = useState<Map<string, BlockPosition>>(initialPositions);

  // Empty graph → honest empty state, never a blank void (rigor #3).
  if (nodes.length === 0) {
    return (
      <div className="px-4 py-10 text-center" data-testid="canvas-empty">
        <p className="font-serif text-[14px] text-ink dark:text-bright">
          Nothing to lay out yet.
        </p>
        <p className="mt-1 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          This completed research produced no distilled insights or open
          questions to arrange as blocks.
        </p>
      </div>
    );
  }

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

  return (
    <div
      data-testid="block-canvas"
      className="relative h-full w-full overflow-auto bg-ice-1 dark:bg-charcoal-1"
    >
      <div className="relative" style={{ width: extent.width, height: extent.height }}>
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
  onCommit,
}: {
  node: DistilledNode;
  pos: BlockPosition;
  investigationId: string;
  onOpenDetail?: (node: DistilledNode) => void;
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
    if (target.closest("button")) return;
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
      // M4 (theme grouping) is DEFERRED — no region-assign gesture shipped, so
      // region is always null. The fields stay as a reserved forward-compatible
      // seam (see the file header + the decision note).
      regionId: null,
      regionLabel: null,
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
        // Reserved-but-always-null until an M4 region-assign gesture exists.
        region_id: null,
        region_label: null,
      },
    }).catch(() => {
      // Swallow — authoritative state is the event log on next load.
    });
  }, [investigationId, live.x, live.y, node.node_id, onCommit]);

  return (
    <div
      data-draggable-block={node.node_id}
      className="absolute cursor-grab touch-none select-none active:cursor-grabbing"
      style={{ left: live.x, top: live.y, width: BLOCK_WIDTH, zIndex: 1 }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <BlockCard node={node} onOpenDetail={onOpenDetail} />
    </div>
  );
}
