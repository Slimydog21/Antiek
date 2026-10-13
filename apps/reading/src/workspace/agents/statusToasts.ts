/**
 * agents/statusToasts.ts — SPR-10 M4: herdr R18 notifications over
 * LemonToast. "needs you" (8 s) on a transition into blocked, "finished"
 * (5 s) on a background completion, never for the active tab, never
 * toast.err (a status is not a shell failure). One visible status toast at
 * a time; a module queue of at most STATUS_TOAST_QUEUE_MAX (8) behind it,
 * one entry per run, the oldest dropped at 9. A run already queued is
 * refreshed by moving it to the tail: the refreshed spec is the newest
 * information, so it is never the "oldest" the next overflow drops. The
 * cap touches only this queue: LemonToast's `_items` and the Undo toasts
 * are untouched.
 * Promotion rides LemonToast's `onDismiss`, so the ✕, the action, the ttl
 * timer and the key all advance the queue the same way.
 */
import { toast } from "../../components/lemon/LemonToast";
import { subscribeReset, subscribeTransitions, type TransitionEvent } from "./agentStatusStore";
import { focusAgent } from "./focusAgent";
import { setStatusToastVisible } from "./statusToastFlag";

export const STATUS_TOAST_QUEUE_MAX = 8;
export const NEEDS_YOU_TTL_MS = 8000;
export const FINISHED_TTL_MS = 5000;

export interface StatusToast {
  runId: string;
  viewId: string;
  viewOpen: boolean;
  investigationId?: string;
  title: string;
  kind: "needs-you" | "finished";
  toastId?: number;
}

let visible: StatusToast | null = null;
let queued: StatusToast[] = [];

function specOf(t: TransitionEvent, kind: StatusToast["kind"]): StatusToast {
  return {
    runId: t.runId,
    viewId: t.entry.viewId,
    viewOpen: t.entry.viewOpen,
    ...(t.entry.investigationId !== undefined ? { investigationId: t.entry.investigationId } : {}),
    title: t.entry.title,
    kind,
  };
}

function onTransition(t: TransitionEvent): void {
  if (t.transition === null) return;
  enqueue(specOf(t, t.transition.kind));
}

/** Subscribe to the store's transitions. Returns the unsubscribe. */
export function installStatusToasts(): () => void {
  return subscribeTransitions(onTransition);
}

function targetOf(spec: StatusToast) {
  return {
    runId: spec.runId,
    viewId: spec.viewId,
    viewOpen: spec.viewOpen,
    ...(spec.investigationId !== undefined ? { investigationId: spec.investigationId } : {}),
    title: spec.title,
    kind: spec.investigationId !== undefined ? ("research-thread" as const) : ("dialogue" as const),
  };
}

function show(spec: StatusToast): void {
  visible = spec;
  setStatusToastVisible(true);
  const opts = {
    ttl: spec.kind === "needs-you" ? NEEDS_YOU_TTL_MS : FINISHED_TTL_MS,
    action: { label: "Open", run: () => { void focusAgent(targetOf(spec)); } },
    onDismiss: () => { if (visible === spec) promote(); },
  };
  spec.toastId = spec.kind === "needs-you"
    ? toast.warn(`${spec.title} needs you`, opts)
    : toast.info(`${spec.title} finished`, opts);
}

function promote(): void {
  visible = null;
  setStatusToastVisible(false);
  const next = queued.shift();
  if (next) show(next);
}

export function enqueue(spec: StatusToast): void {
  if (visible && visible.runId === spec.runId) {
    // A newer spec for the visible run replaces it in place.
    const old = visible;
    visible = null;
    if (old.toastId !== undefined) toast.dismiss(old.toastId);
    show(spec);
    return;
  }
  // One entry per run: a refresh leaves its old slot and joins the tail,
  // so the overflow below drops the run with the oldest information.
  queued = queued.filter((q) => q.runId !== spec.runId);
  queued.push(spec);
  while (queued.length > STATUS_TOAST_QUEUE_MAX) queued.shift();
  if (!visible) promote();
}

/** The agents.gotoToast key: dismiss the visible status toast (promoting
 *  the next) and land on its agent. False when nothing is visible. */
export function focusVisibleStatusToast(): boolean {
  const v = visible;
  if (!v) return false;
  if (v.toastId !== undefined) toast.dismiss(v.toastId);
  else promote();
  void focusAgent(targetOf(v));
  return true;
}

export function resetStatusToasts(): void {
  const v = visible;
  visible = null;
  setStatusToastVisible(false);
  queued = [];
  if (v?.toastId !== undefined) toast.dismiss(v.toastId);
}

/** Dev/test seam: the keymap guard scenario seeds a visible toast. */
export function _seedForGuard(spec: Omit<StatusToast, "toastId">): void {
  enqueue({ ...spec });
}

/** Test accessor. */
export function peek(): { visible: StatusToast | null; queued: readonly StatusToast[] } {
  return { visible, queued: [...queued] };
}

subscribeReset(resetStatusToasts);
