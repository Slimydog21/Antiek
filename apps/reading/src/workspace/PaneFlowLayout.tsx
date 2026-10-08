import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

import { useWorkspace } from "./WorkspaceStore";
import { escOverlayOpen } from "./escapeOverlay";
import { adjacentPane, PANE_GAP, paneGeometry, paneKey, revealPane, samePane, spatialPaneNeighbor, spatialPaneNeighbor2D } from "./paneFlowGeometry";
import type { PaneGeometry } from "./paneFlowGeometry";
import type { PaneArrangement, PaneTarget } from "./panel.types";
import { installPaneHostLease } from "./paneHostLease";
import type { PaneHostLease } from "./paneHostLease";
import { useViewportTier } from "./useViewportTier";

type Host = { target: PaneTarget; node: HTMLElement };
type FrameAttachment = { node: HTMLElement; lease: PaneHostLease<Host> | null };
type Flow = {
  desktop: boolean;
  arrangement: Exclude<PaneArrangement, "legacy"> | null;
  geometry: PaneGeometry;
  zoom: PaneTarget | null;
  focused: PaneTarget | null;
  register: (target: PaneTarget, node: HTMLElement) => PaneHostLease<Host>;
};
type Controller = {
  root: HTMLElement;
  flow: Flow;
  hosts: Map<string, Host>;
  pointerActive: () => boolean;
  reveal: (target: PaneTarget) => boolean;
  rememberScroll: () => void;
  restoreZoom: () => boolean;
};

const FlowContext = createContext<Flow | null>(null);
const controllers = new WeakMap<Element, Controller>();

function visibleHost(node: HTMLElement): boolean {
  return node.isConnected && !node.closest("[hidden], [inert]") && node.getClientRects().length > 0;
}

function editing(node: Element): boolean {
  return (node instanceof HTMLElement && node.isContentEditable)
    || Boolean(node.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])"));
}

function admittedController(node: Element, requireFlow = true): { controller: Controller; host: Host } | null {
  const root = node.closest("[data-pane-flow-root]");
  const frame = node.closest("[data-pane-host]");
  if (!root || (requireFlow && !frame)) return null;
  const controller = controllers.get(root);
  if (!controller?.flow.desktop || (requireFlow && (!controller.flow.arrangement || controller.flow.geometry.kind !== "measured"))
      || !controller.root.isConnected || controller.pointerActive() || escOverlayOpen()) return null;
  const host = [...controller.hosts.values()].find((member) => requireFlow
    ? member.node === frame : member.node.contains(node));
  if (!host || (requireFlow ? !visibleHost(host.node)
    : !host.node.isConnected || Boolean(host.node.closest("[hidden], [inert]"))
      || !(node instanceof HTMLElement) || !visibleHost(node))) return null;
  const dialog = node.closest("[role='dialog'], [role='alertdialog']");
  if (dialog && dialog !== host.node) return null;
  return { controller, host };
}

export function paneEventTarget(event: KeyboardEvent, dispatcherConsumed = false): PaneTarget | null {
  if ((event.defaultPrevented && !dispatcherConsumed) || event.isComposing
      || event.getModifierState("AltGraph") || event.target !== document.activeElement
      || !(event.target instanceof Element) || editing(event.target)
      || event.target.closest("[data-panel-title]")) return null;
  return admittedController(event.target)?.host.target ?? null;
}

export function legacyPaneEventTarget(event: KeyboardEvent, dispatcherConsumed = false): PaneTarget | null {
  if ((event.defaultPrevented && !dispatcherConsumed) || event.repeat || event.isComposing
      || event.getModifierState("AltGraph") || event.target !== document.activeElement
      || !(event.target instanceof Element) || editing(event.target)
      || event.target.closest("[data-panel-title]")) return null;
  const admitted = admittedController(event.target, false);
  return admitted && !admitted.controller.flow.arrangement ? admitted.host.target : null;
}

export function focusAdjacentPane(event: KeyboardEvent, direction: -1 | 1 | "up" | "down", dispatcherConsumed = false): boolean {
  const target = paneEventTarget(event, dispatcherConsumed);
  if (!target || !(event.target instanceof Element)) return false;
  const admitted = admittedController(event.target);
  if (!admitted || admitted.controller.flow.zoom) return false;
  const geometry = admitted.controller.flow.geometry;
  const tiled = admitted.controller.flow.arrangement === "tiled" && geometry.kind === "measured";
  // SPR-01 M2 (R6): up/down are spatial and exist only in tiled mode; in the
  // horizontal flow there is nothing above or below — not consumed.
  if (direction === "up" || direction === "down") {
    if (!tiled) return false;
  }
  const next = direction === "up" || direction === "down"
    ? spatialPaneNeighbor2D(geometry.kind === "measured" ? geometry.placements : [], target, direction)
    : tiled
      ? spatialPaneNeighbor(geometry.placements, target, direction)
      : adjacentPane(useWorkspace.getState().paneOrder, target, direction);
  if (!next) return false;
  const host = admitted.controller.hosts.get(paneKey(next));
  if (!host || !visibleHost(host.node)) return false;
  host.node.focus({ preventScroll: true });
  if (document.activeElement !== host.node) return false;
  useWorkspace.getState().setPaneFocus(next);
  admitted.controller.reveal(next);
  return true;
}

export function reorderActivePane(event: KeyboardEvent, direction: -1 | 1, dispatcherConsumed = false): boolean {
  const target = paneEventTarget(event, dispatcherConsumed);
  return target ? useWorkspace.getState().reorderPane(target, direction) : false;
}

export function toggleActivePaneZoom(event: KeyboardEvent, dispatcherConsumed = false): boolean {
  if (event.repeat) return false;
  const target = paneEventTarget(event, dispatcherConsumed);
  if (!target || !(event.target instanceof Element)) return false;
  return togglePaneHostZoom(target, event.target);
}

/** Local frame and pointer controls use the same admitted host as the key row. */
export function togglePaneHostZoom(target: PaneTarget, node: Element): boolean {
  const admitted = admittedController(node);
  if (!admitted || !samePane(admitted.host.target, target)) return false;
  admitted.controller.rememberScroll();
  if (samePane(useWorkspace.getState().paneZoom, target)) return admitted.controller.restoreZoom();
  return useWorkspace.getState().togglePaneZoom(target);
}

export function togglePaneArrangementAt(event: KeyboardEvent, dispatcherConsumed = false): boolean {
  if (event.repeat || (event.defaultPrevented && !dispatcherConsumed) || event.isComposing
      || event.getModifierState("AltGraph") || event.target !== document.activeElement
      || !(event.target instanceof Element) || editing(event.target)
      || event.target.closest("[data-panel-title]") || escOverlayOpen()) return false;
  const root = event.target.closest("[data-pane-flow-root]");
  const controller = root ? controllers.get(root) : null;
  if (!controller?.flow.desktop || controller.pointerActive() || !controller.root.isConnected) return false;
  const width = controller.root.clientWidth;
  const height = controller.root.clientHeight;
  if (![width, height].every(Number.isFinite) || width <= 2 * PANE_GAP || height <= 2 * PANE_GAP) return false;
  const host = event.target.closest("[data-pane-host], [data-pane], [data-cockpit-content], [data-workspace-window]");
  if (!host || !(host instanceof HTMLElement) || !visibleHost(host)
      || event.target.closest("[aria-modal='true'], [role='alertdialog']")) return false;
  const dialog = event.target.closest("[role='dialog']");
  if (dialog && dialog !== event.target.closest("[data-workspace-window]")) return false;
  controller.rememberScroll();
  return useWorkspace.getState().togglePaneArrangement();
}

/** An admitted open/reopen or an actual window-to-window cycle may receive
 * focus. A stale focusedId/z value cannot pull focus out of the core host. */
export function focusConnectedPaneHost(node: HTMLElement, target: PaneTarget): boolean {
  const admitted = admittedController(node);
  const active = document.activeElement;
  if (!admitted || !samePane(admitted.host.target, target) || !(active instanceof Element)
      || editing(active) || active.closest("[aria-modal='true'], [role='alertdialog']")) return false;
  const previousWindow = active.closest("[data-workspace-window]");
  const fromWindow = previousWindow instanceof HTMLElement && visibleHost(previousWindow)
    && [...admitted.controller.hosts.values()].some((host) => host.node === previousWindow);
  if (!samePane(useWorkspace.getState().paneFocus, target) && !fromWindow) return false;
  node.focus({ preventScroll: true });
  if (document.activeElement !== node) return false;
  useWorkspace.getState().setPaneFocus(target);
  admitted.controller.reveal(target);
  return true;
}

export function usePaneFlowFrame(target: PaneTarget) {
  const flow = useContext(FlowContext);
  const nodeRef = useRef<HTMLElement | null>(null);
  const attachmentRef = useRef<FrameAttachment | null>(null);
  const key = paneKey(target);
  const register = flow?.register;
  const ref = useMemo(() => {
    let owned: FrameAttachment | null = null;
    return (node: HTMLElement | null) => {
      const previous = owned;
      owned = null;
      if (previous) {
        previous.lease?.retire();
        if (attachmentRef.current === previous) {
          attachmentRef.current = null;
          nodeRef.current = null;
        }
      }
      if (node) {
        owned = { node, lease: register?.(target, node) ?? null };
        attachmentRef.current = owned;
        nodeRef.current = owned.node;
      }
    };
    // Target identity is its kind/id key, not the caller's object allocation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, register]);
  const active = Boolean(flow?.arrangement);
  const placement = flow?.geometry.kind === "measured"
    ? flow.geometry.placements.find((member) => samePane(member.target, target)) : null;
  const hidden = active && !placement;
  useLayoutEffect(() => {
    const node = nodeRef.current;
    if (!node) return;
    const previous = node.inert;
    node.inert = previous || hidden;
    return () => { node.inert = previous; };
  }, [hidden]);
  const style: CSSProperties | undefined = active && placement ? {
    position: "absolute", left: placement.rect.x, top: placement.rect.y,
    width: placement.rect.width, height: placement.rect.height, borderRadius: 0,
  } : undefined;
  const restoreZoom = useCallback((event?: KeyboardEvent) => {
    const attachment = attachmentRef.current;
    if (!attachment?.lease?.isCurrent()) return false;
    const root = nodeRef.current?.closest("[data-pane-flow-root]");
    const controller = root ? controllers.get(root) : null;
    const host = attachment.lease.record;
    if (!controller || controller.hosts.get(paneKey(host.target)) !== host
        || host.node !== attachment.node || attachment.node !== nodeRef.current) return false;
    if (event && (event.defaultPrevented || event.repeat || event.isComposing
        || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey || event.getModifierState("AltGraph")
        || event.target !== document.activeElement || !(event.target instanceof HTMLElement)
        || event.target.closest("[data-pane-flow-root]") !== root || !visibleHost(event.target)
        || editing(event.target) || escOverlayOpen())) return false;
    return controller?.restoreZoom() ?? false;
  }, []);
  return { ref, active, hidden, style, arrangement: flow?.arrangement ?? null,
    focused: active && samePane(flow?.focused ?? null, target),
    zoomed: active && samePane(flow?.zoom ?? null, target), hostKey: active ? key : undefined, restoreZoom };
}

export function PaneFlowLayout({ children }: { children: ReactNode }) {
  const arrangement = useWorkspace((s) => s.paneArrangement);
  const order = useWorkspace((s) => s.paneOrder);
  const tiles = useWorkspace((s) => s.paneTiles);
  const zoom = useWorkspace((s) => s.paneZoom);
  const focused = useWorkspace((s) => s.paneFocus);
  const tier = useViewportTier();
  const effective = tier === "sm" || arrangement === "legacy" ? null : arrangement;
  const rootRef = useRef<HTMLDivElement | null>(null);
  const hosts = useRef(new Map<string, Host>());
  const captures = useRef(new Map<number, Element>());
  const horizontalScroll = useRef(0);
  const restoreFocus = useRef<Host | null>(null);
  const previousMode = useRef<{ arrangement: typeof effective; zoom: PaneTarget | null }>({ arrangement: null, zoom: null });
  const [bounds, setBounds] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const measure = () => {
      const width = root.clientWidth;
      const height = root.clientHeight;
      setBounds((previous) => previous.width === width && previous.height === height ? previous : { width, height });
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    return () => observer.disconnect();
  }, []);

  const register = useCallback((target: PaneTarget, node: HTMLElement) =>
    installPaneHostLease(hosts.current, paneKey(target), { target, node }), []);
  const geometry = useMemo(() => effective ? paneGeometry({ ...bounds, arrangement: effective, order, tiles, zoom })
    : { kind: "unmeasured" } satisfies PaneGeometry, [bounds, effective, order, tiles, zoom]);
  const flow: Flow = useMemo(() => ({ desktop: tier !== "sm", arrangement: effective, geometry, zoom, focused, register }),
    [tier, effective, geometry, zoom, focused, register]);

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const restoringZoom = !zoom && previousMode.current.arrangement === effective
      && (previousMode.current.zoom !== null || restoreFocus.current !== null);
    let restoringFocus = false;
    const pointerActive = () => {
      for (const [id, node] of captures.current) {
        if (node.isConnected && root.contains(node) && node.hasPointerCapture(id)) return true;
        captures.current.delete(id);
      }
      return false;
    };
    const reveal = (target: PaneTarget) => {
      if (restoringFocus || flow.arrangement !== "horizontal" || flow.geometry.kind !== "measured") return false;
      const placement = flow.geometry.placements.find((member) => samePane(member.target, target));
      if (!placement) return false;
      const left = revealPane({ rect: placement.rect, viewportWidth: root.clientWidth,
        extentWidth: flow.geometry.width, scrollLeft: root.scrollLeft });
      if (left === null) return false;
      root.scrollLeft = left;
      return true;
    };
    const rememberScroll = () => {
      if (flow.arrangement === "horizontal" && !flow.zoom && flow.geometry.kind === "measured") {
        horizontalScroll.current = root.scrollLeft;
      }
    };
    const restoreZoom = () => {
      const target = useWorkspace.getState().paneZoom;
      if (!flow.desktop || !flow.arrangement || flow.geometry.kind !== "measured"
          || !target || !root.isConnected || pointerActive() || escOverlayOpen()
          || !flow.geometry.placements.some((member) => samePane(member.target, target))) return false;
      restoreFocus.current = hosts.current.get(paneKey(target)) ?? null;
      return useWorkspace.getState().restorePaneZoom();
    };
    const controllerLease = installPaneHostLease(controllers, root,
      { root, flow, hosts: hosts.current, pointerActive, reveal, rememberScroll, restoreZoom });
    if (effective === "horizontal" && !zoom && geometry.kind === "measured"
        && (previousMode.current.arrangement !== effective || previousMode.current.zoom !== null)) {
      root.scrollLeft = Math.max(0, Math.min(horizontalScroll.current, geometry.width - root.clientWidth));
    }
    previousMode.current = { arrangement: effective, zoom };
    if (!zoom && restoreFocus.current) {
      const pending = restoreFocus.current;
      restoreFocus.current = null;
      const current = hosts.current.get(paneKey(pending.target));
      if (current?.node === pending.node && visibleHost(current.node)) {
        // Restore focus through the existing admission guards without revealing over the saved view.
        restoringFocus = restoringZoom;
        try {
          if (focusConnectedPaneHost(current.node, current.target) && restoringZoom && !samePane(focused, current.target)) {
            // Keep the restoration guard through the render that acknowledges this focus change.
            restoreFocus.current = current;
          }
        } finally { restoringFocus = false; }
      }
    }
    if (!restoringZoom && focused) {
      const host = hosts.current.get(paneKey(focused));
      if (host && visibleHost(host.node) && host.node.contains(document.activeElement)) reveal(focused);
    }
    return () => { controllerLease.retire(); };
  }, [effective, geometry, zoom, flow, focused]);

  return (
    <FlowContext.Provider value={flow}>
      <div ref={rootRef} data-pane-flow-root data-windows-layer data-pane-arrangement={effective ?? "legacy"}
        data-pane-measurement={geometry.kind}
        className={effective ? "relative h-full w-full overflow-x-auto overflow-y-hidden" : "relative h-full w-full"}
        onGotPointerCaptureCapture={(event) => {
          if (event.target instanceof Element) captures.current.set(event.pointerId, event.target);
        }}
        onLostPointerCaptureCapture={(event) => { captures.current.delete(event.pointerId); }}
        onScroll={() => {
          const current = useWorkspace.getState();
          if (effective === "horizontal" && !current.paneZoom && current.paneArrangement === "horizontal"
              && geometry.kind === "measured" && rootRef.current) horizontalScroll.current = rootRef.current.scrollLeft;
        }}
        onFocusCapture={(event) => {
          if (!(event.target instanceof Element)) return;
          const frame = event.target.closest("[data-pane-host]");
          const host = [...hosts.current.values()].find((member) => member.node === frame);
          if (host && visibleHost(host.node)) useWorkspace.getState().setPaneFocus(host.target);
        }}
      >
        <div className="relative h-full w-full" style={effective && geometry.kind === "measured"
          ? { width: geometry.width, height: geometry.height } : undefined}>
          {children}
        </div>
      </div>
    </FlowContext.Provider>
  );
}

/** A layer rendered alone retains its old coordinate origin. */
export function useSharedPaneOrigin(): boolean { return useContext(FlowContext) !== null; }
