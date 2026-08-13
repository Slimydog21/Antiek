import { useEffect, useState } from "react";

import { notifyShellFailure } from "../../werner/shellExperienceSignals";

/**
 * LemonToast — tiny pub-sub toast queue + viewport renderer.
 *
 *   toast.ok("Investigation saved");
 *   toast.warn("Popups blocked");
 *   toast.err("Failed to save");
 *   toast.info("Generating thumbnail…");
 *
 * Mount <LemonToastViewport /> once at app root (AppShell). Toasts auto-dismiss
 * after `ttl` ms (default 4000). The queue is an in-module store with a tiny
 * subscriber pattern — no zustand dep, ~30 LoC.
 */
type Kind = "ok" | "warn" | "err" | "info";

/** A navigation target for a toast (herdr transfer, P0-4): clicking the
 *  toast jumps to the surface that produced it — the same deep-link idea as
 *  herdr's toast-to-pane focus, expressed for a web SPA. `panelId` focuses a
 *  workspace panel after the route lands (panel focus is a no-op when the
 *  panel isn't in the layout). */
export interface ToastTarget {
  path: string;
  panelId?: string;
}

export interface ToastOptions {
  ttl?: number;
  /** When set, the toast becomes a navigation affordance. */
  target?: ToastTarget;
}

type Item = { id: number; kind: Kind; msg: string; ttl: number; target?: ToastTarget };

let _nextId = 1;
let _items: Item[] = [];
const _listeners = new Set<(s: Item[]) => void>();

/** The app shell registers its router navigate here (AppShell is inside the
 *  router; this module stays dependency-free so PanelWindowApp popouts can
 *  mount the viewport without a router and never crash). The navigator
 *  receives the full ToastTarget so the shell can focus a panel after the
 *  route lands. */
let _navigate: ((target: ToastTarget) => void) | null = null;

export function setToastNavigator(
  fn: ((target: ToastTarget) => void) | null,
): void {
  _navigate = fn;
}

/** Per-kind default TTLs (pre-P0-4 contract: ok 4s, warn 6s, err 8s, info
 *  4s). A single default would have silently halved warn/err. */
const DEFAULT_TTL: Record<Kind, number> = {
  ok: 4000,
  warn: 6000,
  err: 8000,
  info: 4000,
};

function emit(kind: Kind, msg: string, opts: ToastOptions = {}) {
  if (kind === "err") notifyShellFailure();
  const item: Item = {
    id: _nextId++,
    kind,
    msg,
    ttl: opts.ttl ?? DEFAULT_TTL[kind],
    target: opts.target,
  };
  _items = [..._items, item];
  _listeners.forEach((l) => l(_items));
  setTimeout(() => dismiss(item.id), item.ttl);
  return item.id;
}

function dismiss(id: number) {
  _items = _items.filter((it) => it.id !== id);
  _listeners.forEach((l) => l(_items));
}

/** Navigate to a toast's target. No-op when no navigator is registered
 *  (popout windows, tests) — a toast click must never crash. */
function goTo(itemId: number, target: ToastTarget) {
  dismiss(itemId);
  _navigate?.(target);
}

export const toast = {
  ok: (msg: string, opts: number | ToastOptions = {}) =>
    emit("ok", msg, typeof opts === "number" ? { ttl: opts } : opts),
  warn: (msg: string, opts: number | ToastOptions = {}) =>
    emit("warn", msg, typeof opts === "number" ? { ttl: opts } : opts),
  err: (msg: string, opts: number | ToastOptions = {}) =>
    emit("err", msg, typeof opts === "number" ? { ttl: opts } : opts),
  info: (msg: string, opts: number | ToastOptions = {}) =>
    emit("info", msg, typeof opts === "number" ? { ttl: opts } : opts),
  dismiss,
  /** Register the app router navigate (AppShell). Tests can inject a spy. */
  setNavigator: setToastNavigator,
};

function useToasts(): Item[] {
  const [items, setItems] = useState<Item[]>(_items);
  useEffect(() => {
    _listeners.add(setItems);
    return () => {
      _listeners.delete(setItems);
    };
  }, []);
  return items;
}

const kindStyles: Record<Kind, string> = {
  ok:   "bg-aurora text-ink border-ink",
  warn: "bg-sun text-ink border-ink",
  err:  "bg-emperor text-ice-1 border-ink",
  info: "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright border-sun",
};

const kindLabels: Record<Kind, string> = {
  ok: "✓", warn: "!", err: "✕", info: "ⓘ",
};

export function LemonToastViewport() {
  const items = useToasts();
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed top-4 right-4 z-[200] flex flex-col gap-2 pointer-events-none"
    >
      {items.map((it) => (
        <div
          key={it.id}
          className={
            "pointer-events-auto min-w-[260px] max-w-[420px] " +
            "border-edge rounded-hog shadow-z2 dark:shadow-z2-night " +
            "px-3 py-2 flex items-center gap-3 font-sans text-[13.5px] " +
            kindStyles[it.kind]
          }
        >
          <span aria-hidden="true" className="font-mono font-bold">{kindLabels[it.kind]}</span>
          {it.target ? (
            <button
              type="button"
              onClick={() => goTo(it.id, it.target!)}
              className="flex-1 min-w-0 text-left underline decoration-1 underline-offset-2 hover:opacity-80"
              title={`Open ${it.target.path}`}
            >
              {it.msg}
            </button>
          ) : (
            <span className="flex-1">{it.msg}</span>
          )}
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => dismiss(it.id)}
            className="leading-none text-ink/60 hover:text-ink"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

export default toast;
