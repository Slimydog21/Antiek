import { Suspense, lazy, useEffect, useRef, useState } from "react";

/**
 * CommandPalette — the ⌘K shell (PostHog Wedge 3, master-spec §5.6 + §4.5).
 *
 * Mounted once at the App root. It owns only what must exist before the
 * palette is ever opened: the open state, the ⌘K / Ctrl+K shortcut, the
 * "antiek:palette:toggle" event the NavRail Search door and the workspace
 * shortcuts dispatch, Esc to close, and giving focus back to the element
 * that opened it. The palette itself (its route index, ranking, workspace
 * actions and driver picker) lives in CommandPalette.impl.tsx and loads on
 * demand, the way ModelUsagePicker does: nothing a reader needs before
 * pressing ⌘K rides in the entry chunk. The browser fetches it when idle,
 * so the first ⌘K still opens at once.
 */
const Panel = lazy(() => import("./CommandPalette.impl"));

type IdleWindow = Window & {
  requestIdleCallback?: (cb: () => void) => number;
  cancelIdleCallback?: (id: number) => void;
};

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  // The element that had focus when the palette opened; closing gives it back.
  const openerRef = useRef<Element | null>(null);

  const toggle = () =>
    setOpen((v) => {
      if (!v) openerRef.current = document.activeElement;
      return !v;
    });

  useEffect(() => {
    // S8: the workspace shortcuts module (src/workspace/shortcuts.ts) owns
    // the ⌘K binding and dispatches "antiek:palette:toggle"; the in-component
    // ⌘K fallback keeps the palette working without AppShell (Storybook).
    const onToggle = () => toggle();
    window.addEventListener("antiek:palette:toggle" as keyof WindowEventMap, onToggle as EventListener);
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggle();
        return;
      }
      if (e.key === "Escape" && open) {
        e.preventDefault();
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("antiek:palette:toggle" as keyof WindowEventMap, onToggle as EventListener);
      window.removeEventListener("keydown", handler);
    };
  }, [open]);

  useEffect(() => {
    if (open) return;
    const opener = openerRef.current;
    openerRef.current = null;
    const active = document.activeElement;
    // Only when focus has nowhere better to be (the palette just unmounted
    // under it); a route change that removed the opener leaves it alone.
    if (opener instanceof HTMLElement && opener.isConnected && (!active || active === document.body)) {
      opener.focus({ preventScroll: true });
    }
  }, [open]);

  useEffect(() => {
    const w = window as IdleWindow;
    if (!w.requestIdleCallback) return;
    const id = w.requestIdleCallback(() => void import("./CommandPalette.impl"));
    return () => w.cancelIdleCallback?.(id);
  }, []);

  if (!open) return null;
  return (
    <Suspense fallback={null}>
      <Panel onClose={() => setOpen(false)} />
    </Suspense>
  );
}
