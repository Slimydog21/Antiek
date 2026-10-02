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

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  getDistillation,
  getTrajectory,
  postTypedEvent,
} from "../../../lib/api";
import type { RefObject } from "react";
import { escOverlayOpen, topModal } from "../../../workspace/escapeOverlay";
import type { DistilledNode } from "../../../lib/api";
import type { Event } from "../../../generated/types";
import AIActionFailure from "../../../shared/AIActionFailure";
import Thinking from "../../../shared/Thinking";

import BlockCard from "./BlockCard";
import Edges from "./Edges";
import type { SourceAnchorRect } from "./evidenceWindowPlacement";
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
  interactionEnabled?: boolean;
  /** Click-to-detail seam for SPR-04 (anchors the float-menu in block detail).
   *  Optional. */
  onOpenDetail?: (node: DistilledNode) => void;
  /** Opens the exact source document in the host's canonical reader. */
  onCiteSource?: (node: DistilledNode, anchor: SourceAnchorRect) => void;
}

type Resource = { investigationId: string; attempt: object | null };
type LoadState = { resource: Resource; attempt: object | null } & (
  | { kind: "loading" }
  | { kind: "error"; reason: string | null }
  | { kind: "loaded"; insights: DistilledNode[]; questions: DistilledNode[]; positions: Map<string, BlockPosition> }
);

export default function Canvas({ investigationId, onOpenDetail, onCiteSource, interactionEnabled = true }: CanvasProps) {
  const resource = useMemo<Resource>(() => ({ investigationId, attempt: null }), [investigationId]);
  const current = useRef<({ resource: Resource } & CanvasProps) | null>(null);
  const [state, setState] = useState<LoadState>({ kind: "loading", resource, attempt: null });
  useLayoutEffect(() => {
    current.current = { resource, investigationId, onOpenDetail, onCiteSource, interactionEnabled };
    return () => { current.current = null; };
  }, [resource, investigationId, onOpenDetail, onCiteSource, interactionEnabled]);

  const load = useCallback(async (previousAttempt: object | null) => {
    if (current.current?.resource !== resource || resource.attempt !== previousAttempt ||
        (previousAttempt !== null && !current.current.interactionEnabled)) return;
    const attempt = {};
    resource.attempt = attempt;
    setState({ kind: "loading", resource, attempt });
    const accepted = () => current.current?.resource === resource && resource.attempt === attempt;
    try {
      const [distill, trajectory] = await Promise.all([
        getDistillation(resource.investigationId), getTrajectory(resource.investigationId),
      ]);
      if (!accepted()) return;
      const nodeIds = [...distill.insights, ...distill.questions].map((node) => node.node_id);
      const positions = resolvePositions(nodeIds, replayPositions(trajectory.events as Event[]));
      setState({ kind: "loaded", resource, attempt, insights: distill.insights, questions: distill.questions, positions });
    } catch (error) {
      if (!accepted()) return;
      setState({ kind: "error", resource, attempt, reason: error instanceof ApiError ? error.body || null : null });
    }
  }, [resource]);
  useEffect(() => { void load(null); }, [load]);

  if (state.resource !== resource || state.attempt !== resource.attempt || state.kind === "loading") {
    return <div {...(!interactionEnabled ? { inert: "" } : {})} className="flex items-center gap-2 px-4 py-8" role="status" aria-live="polite">
      <Thinking size={28} label="Laying out the organism" status="reading the graph…" />
    </div>;
  }
  if (state.kind === "error") {
    return <div className="px-4 py-8" {...(!interactionEnabled ? { inert: "" } : {})}>
      <AIActionFailure title="Couldn’t load the canvas" reason={state.reason} onRetry={() => void load(state.attempt)} />
    </div>;
  }
  const admitted = () => current.current?.resource === resource && resource.attempt === state.attempt &&
    current.current.interactionEnabled === true;
  return <LoadedCanvas key={investigationId} investigationId={investigationId}
    insights={state.insights} questions={state.questions} initialPositions={state.positions}
    interactionEnabled={interactionEnabled} admitted={admitted}
    onOpenDetail={onOpenDetail ? (node) => { if (admitted()) current.current?.onOpenDetail?.(node); } : undefined}
    onCiteSource={onCiteSource ? (node, anchor) => { if (admitted()) current.current?.onCiteSource?.(node, anchor); } : undefined}
  />;
}

function LoadedCanvas({
  investigationId,
  insights,
  questions,
  initialPositions,
  interactionEnabled,
  admitted,
  onOpenDetail,
  onCiteSource,
}: {
  investigationId: string;
  insights: DistilledNode[];
  questions: DistilledNode[];
  initialPositions: Map<string, BlockPosition>;
  interactionEnabled: boolean;
  admitted: () => boolean;
  onOpenDetail?: (node: DistilledNode) => void;
  onCiteSource?: (node: DistilledNode, anchor: SourceAnchorRect) => void;
}) {
  const scrollport = useRef<HTMLDivElement>(null);
  const nodes = useMemo(() => [...insights, ...questions], [insights, questions]);
  // Position state seeds from the replayed events, then tracks live drags.
  // This React state is NOT a persistence store — it's transient view state
  // for the in-flight drag; the durable truth is the event log. Every
  // drag-END re-appends an event so a reload re-derives the same coordinates.
  const [positions, setPositions] = useState<Map<string, BlockPosition>>(initialPositions);

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

  // Empty graph → honest empty state, never a blank void (rigor #3).
  if (nodes.length === 0) {
    return (
      <div {...(!interactionEnabled ? { inert: "" } : {})} className="px-4 py-10 text-center" data-testid="canvas-empty">
        <p className="font-serif text-sm text-ink dark:text-bright">
          Nothing to lay out yet.
        </p>
        <p className="mt-1 font-mono text-xs text-shadow-1 dark:text-moonlight">
          This research distilled no insights or open questions — when it does,
          they’ll appear here as blocks.
        </p>
      </div>
    );
  }


  return (
    <div
      ref={scrollport}
      {...(!interactionEnabled ? { inert: "" } : {})}
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
              scrollport={scrollport}
              interactionEnabled={interactionEnabled}
              admitted={admitted}
              onOpenDetail={onOpenDetail}
              onCiteSource={onCiteSource}
              onCommit={(next) =>
                admitted() && setPositions((prev) => {
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
function DraggableBlock({ node, pos, investigationId, scrollport, interactionEnabled, admitted, onOpenDetail, onCiteSource, onCommit }: {
  node: DistilledNode;
  pos: BlockPosition;
  investigationId: string;
  scrollport: RefObject<HTMLDivElement>;
  interactionEnabled: boolean;
  admitted: () => boolean;
  onOpenDetail?: (node: DistilledNode) => void;
  onCiteSource?: (node: DistilledNode, anchor: SourceAnchorRect) => void;
  onCommit: (next: BlockPosition) => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const committed = useRef(pos);
  const live = useRef({ x: pos.x, y: pos.y });
  const [rendered, setRendered] = useState(live.current);
  const origin = useRef<{ pointerX: number; pointerY: number; x: number; y: number; pointerId: number; target: Element } | null>(null);
  const moved = useRef(false);
  const update = (next: { x: number; y: number }) => { live.current = next; setRendered(next); };
  const cancel = (restore: boolean) => {
    const drag = origin.current; origin.current = null; moved.current = false;
    if (drag) { try { drag.target.releasePointerCapture(drag.pointerId); } catch { /* Capture may already be lost. */ } }
    if (restore) update({ x: committed.current.x, y: committed.current.y });
  };
  useLayoutEffect(() => {
    committed.current = pos;
    if (!origin.current) update({ x: pos.x, y: pos.y });
  }, [pos]);
  useLayoutEffect(() => { if (!interactionEnabled) cancel(true); }, [interactionEnabled]);
  useLayoutEffect(() => () => cancel(false), []);

  const available = () => {
    const block = root.current;
    if (!admitted() || !block?.isConnected || block.closest('[hidden], [aria-hidden="true"], [inert]') || topModal()) return false;
    const ancestorOverlay = block.parentElement?.closest('[data-esc-overlay], [aria-modal="true"]');
    const region = block.closest('[role="region"]');
    const panelTitle = region?.querySelector('[data-panel-title]');
    const persistentPanel = region && panelTitle?.closest('[role="region"]') === region;
    return (!ancestorOverlay || (ancestorOverlay === region && persistentPanel)) && !escOverlayOpen(block);
  };
  const clamp = (point: { x: number; y: number }) => {
    const port = scrollport.current;
    if (!port?.isConnected || port.clientWidth <= 0 || port.clientHeight <= 0) return null;
    const next = clampBlockToViewport({ x: point.x - port.scrollLeft, y: point.y - port.scrollTop },
      { width: port.clientWidth, height: port.clientHeight });
    return { x: next.x + port.scrollLeft, y: next.y + port.scrollTop };
  };
  const commit = (point: { x: number; y: number }) => {
    if (!available()) return false;
    const bounded = clamp(point);
    if (!bounded) return false;
    const next: BlockPosition = { ...committed.current, ...bounded, persisted: true };
    committed.current = next; update(bounded); onCommit(next);
    void postTypedEvent({ investigation_id: investigationId, payload: {
      action_type: "block.positioned", node_id: node.node_id, x: bounded.x, y: bounded.y,
      region_id: next.regionId, region_label: next.regionLabel,
    } }).catch(() => {});
    return true;
  };
  const onTitleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (origin.current || event.target !== event.currentTarget || document.activeElement !== event.currentTarget ||
        !event.currentTarget.isConnected || !available() || event.defaultPrevented || event.nativeEvent.isComposing ||
        event.getModifierState("AltGraph") || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    let dx = 0, dy = 0;
    switch (event.key) {
      case "ArrowLeft": dx = -24; break;
      case "ArrowRight": dx = 24; break;
      case "ArrowUp": dy = -24; break;
      case "ArrowDown": dy = 24; break;
      default: return;
    }
    const next = clamp({ x: live.current.x + dx, y: live.current.y + dy });
    if (!next) return;
    if (next.x === live.current.x && next.y === live.current.y) return;
    event.preventDefault();
    commit(next);
  };
  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!available() || !(event.target instanceof Element) ||
        event.target.closest('button, input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    origin.current = { pointerX: event.clientX, pointerY: event.clientY, ...live.current, pointerId: event.pointerId, target: event.currentTarget };
    moved.current = false;
  };
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = origin.current;
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (!available()) { cancel(true); return; }
    const dx = event.clientX - drag.pointerX, dy = event.clientY - drag.pointerY;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) moved.current = true;
    const next = clamp({ x: drag.x + dx, y: drag.y + dy });
    if (next) update(next);
  };
  const onPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const changed = moved.current, drag = origin.current;
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (!available()) { cancel(true); return; }
    cancel(false);
    if (changed && !commit(live.current)) update({ x: committed.current.x, y: committed.current.y });
  };
  return <div ref={root} data-draggable-block={node.node_id}
    className="absolute cursor-grab touch-none select-none active:cursor-grabbing"
    style={{ left: rendered.x, top: rendered.y, width: BLOCK_WIDTH, zIndex: 1 }}
    onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}>
    <BlockCard node={node} onTitleKeyDown={onTitleKeyDown} onOpenDetail={onOpenDetail}
      onCiteSource={onCiteSource} sourceInvestigationId={investigationId} />
  </div>;
}
