import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { notifyShellFailure } from "../../mascot/shellExperienceSignals";

/**
 * LemonToast — tiny pub-sub toast queue + viewport renderer.
 *
 *   toast.ok("Investigation saved");
 *   toast.warn("Popups blocked");
 *   toast.err("Failed to save");
 *   toast.info("Generating thumbnail…");
 *
 * Mount <LemonToastViewport /> once at app root (AppShell). Toasts auto-dismiss
 * after `ttl` ms (per-kind defaults below). The queue is an in-module store
 * with a tiny subscriber pattern — no zustand dep, ~30 LoC.
 *
 * Reading and reaching (audit M5):
 *   - errors announce assertively (a role="alert" region) and sit at the top
 *     of the stack; everything else is a polite status;
 *   - the countdown pauses while the pointer rests on a toast or focus is in
 *     it, so a toast carrying a link cannot vanish from under the hand
 *     (WCAG 2.2.1);
 *   - the dismiss control is a 24px target drawn in the toast's own text
 *     colour, so it reads wherever the text reads (it was 10.7x14px at 1.08:1
 *     on the night info toast);
 *   - every kind is a pair measured in both themes (controls.contrast.test.ts)
 *     and a floating island: the hard offset shadow on the toast rung.
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

/** Per toast: its pending auto-dismiss, and how long it had left. */
const _timers = new Map<number, { handle: ReturnType<typeof setTimeout> | null; remaining: number; startedAt: number }>();

function schedule(id: number, ms: number) {
  _timers.set(id, { handle: setTimeout(() => dismiss(id), ms), remaining: ms, startedAt: Date.now() });
}

/** Hold the countdown (pointer on the toast, or focus inside it). */
function pause(id: number) {
  const t = _timers.get(id);
  if (!t || t.handle === null) return;
  clearTimeout(t.handle);
  t.remaining = Math.max(0, t.remaining - (Date.now() - t.startedAt));
  t.handle = null;
}

function resume(id: number) {
  const t = _timers.get(id);
  if (!t || t.handle !== null) return;
  schedule(id, t.remaining);
}

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
  schedule(item.id, item.ttl);
  return item.id;
}

function dismiss(id: number) {
  const t = _timers.get(id);
  if (t?.handle) clearTimeout(t.handle);
  _timers.delete(id);
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

/** Face, text and edge per kind. The text colour is also the icon's and the
 *  dismiss control's (they draw in currentColor). Exported for the contrast
 *  test, which resolves each class through tokens.css in both themes. */
export const kindStyles: Record<Kind, string> = {
  ok:   "bg-success text-ice-0 dark:text-ink border-transparent",
  warn: "bg-sun text-ink border-transparent",
  err:  "bg-emperor text-ice-0 border-transparent",
  info: "bg-card text-1 border-rule",
};

/** Kind glyphs, drawn (not typed) so they do not vary by OS font, and so the
 *  error mark is not the same ✕ as the dismiss control beside it. */
const KIND_ICON: Record<Kind, ReactNode> = {
  ok: <path d="M3.5 8.5l3 3 6-7" />,
  warn: (
    <>
      <path d="M8 2.5l6 11H2z" />
      <path d="M8 7v2.5M8 11.6v.1" />
    </>
  ),
  err: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.8v3.6M8 10.9v.1" />
    </>
  ),
  info: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 7.2v3.8M8 5v.1" />
    </>
  ),
};

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      {children}
    </svg>
  );
}

function ToastCard({ it }: { it: Item }) {
  return (
    <div
      onPointerEnter={() => pause(it.id)}
      onPointerLeave={() => resume(it.id)}
      onFocus={() => pause(it.id)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) resume(it.id);
      }}
      className={
        "pointer-events-auto min-w-[260px] max-w-[min(420px,calc(100vw-2rem))] " +
        "border rounded-hog shadow-island " +
        "pl-3 pr-1.5 py-1.5 flex items-center gap-2.5 font-sans text-sm " +
        kindStyles[it.kind]
      }
    >
      <Icon>{KIND_ICON[it.kind]}</Icon>
      {it.target ? (
        <button
          type="button"
          onClick={() => goTo(it.id, it.target!)}
          className="flex-1 min-w-0 py-0.5 text-left underline decoration-1 underline-offset-2"
          title={`Open ${it.target.path}`}
        >
          {it.msg}
        </button>
      ) : (
        <span className="flex-1 py-0.5">{it.msg}</span>
      )}
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => dismiss(it.id)}
        className="shrink-0 inline-flex items-center justify-center w-7 h-7 rounded-hog text-current hover:bg-wash"
      >
        <Icon>
          <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" />
        </Icon>
      </button>
    </div>
  );
}

export function LemonToastViewport() {
  const items = useToasts();
  const errors = items.filter((it) => it.kind === "err");
  const others = items.filter((it) => it.kind !== "err");
  return (
    <div className="fixed top-4 right-4 z-toast flex flex-col gap-2 pointer-events-none">
      {/* Two live regions that are always mounted, so the first toast of
          each kind is announced: errors interrupt, the rest wait their turn. */}
      <div role="alert" aria-live="assertive" className="flex flex-col gap-2">
        {errors.map((it) => (
          <ToastCard key={it.id} it={it} />
        ))}
      </div>
      <div role="status" aria-live="polite" className="flex flex-col gap-2">
        {others.map((it) => (
          <ToastCard key={it.id} it={it} />
        ))}
      </div>
    </div>
  );
}

export default toast;
