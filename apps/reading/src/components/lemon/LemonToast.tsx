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
type Item = { id: number; kind: Kind; msg: string; ttl: number };

let _nextId = 1;
let _items: Item[] = [];
const _listeners = new Set<(s: Item[]) => void>();

function emit(kind: Kind, msg: string, ttl: number) {
  if (kind === "err") notifyShellFailure();
  const item: Item = { id: _nextId++, kind, msg, ttl };
  _items = [..._items, item];
  _listeners.forEach((l) => l(_items));
  setTimeout(() => dismiss(item.id), ttl);
  return item.id;
}

function dismiss(id: number) {
  _items = _items.filter((it) => it.id !== id);
  _listeners.forEach((l) => l(_items));
}

export const toast = {
  ok: (msg: string, ttl = 4000) => emit("ok", msg, ttl),
  warn: (msg: string, ttl = 6000) => emit("warn", msg, ttl),
  err: (msg: string, ttl = 8000) => emit("err", msg, ttl),
  info: (msg: string, ttl = 4000) => emit("info", msg, ttl),
  dismiss,
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
          <span className="flex-1">{it.msg}</span>
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
