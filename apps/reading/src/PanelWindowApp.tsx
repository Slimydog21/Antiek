import { Suspense, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { LemonToastViewport } from "./components/lemon/LemonToast";
import { PanelRegistry } from "./workspace/PanelRegistry";
import {
  disablePersistence,
  enablePersistence,
} from "./workspace/WorkspaceStore";
import { farewellPopout, receivePopoutPanel } from "./workspace/popout";
import type { PanelDescriptor } from "./workspace/panel.types";

/**
 * The popout window app. Renders at `/_panel/:panelId` when the
 * operator hits "Pop out window" on a panel's kebab.
 *
 * Lifecycle:
 *   1. Mount: dispatch a popout-ready BroadcastChannel message.
 *      Main responds with the panel descriptor.
 *   2. While alive: render the panel's kind via PanelRegistry, taking
 *      the full window.
 *   3. On unload: dispatch popout-bye with the current window rect so
 *      main can re-instate at the right size.
 *
 * No AppShell, no NavRail, no dock zones — the OS window IS the
 * frame, and this app just renders the panel's content. Toast viewport
 * is mounted in case the inner panel emits toasts.
 *
 * Persistence is disabled in popout windows so two parallel writers
 * don't fight over localStorage (the main tab is the one that persists).
 *
 * A hand-off that does not complete ends on "This panel couldn't be
 * opened." with a Close action (A-15). receivePopoutPanel already gives up
 * after 2 s (workspace/popout.ts) and resolves null; HANDOFF_DEADLINE_MS is
 * the backstop for a handshake that never settles at all. 10 s is five times
 * the handshake's own 2 s budget, so a slow main tab that answers late still
 * wins, and a window opened with nothing to receive from cannot spin forever.
 */
const HANDOFF_DEADLINE_MS = 10_000;

export default function PanelWindowApp() {
  const params = useParams<{ panelId?: string }>();
  const panelId = params.panelId ? decodeURIComponent(params.panelId) : null;
  const [descriptor, setDescriptor] = useState<PanelDescriptor | null>(null);
  const [failed, setFailed] = useState<boolean>(false);

  useEffect(() => {
    disablePersistence();
    return () => enablePersistence();
  }, []);

  useEffect(() => {
    if (!panelId) {
      setFailed(true);
      return;
    }
    let cancelled = false;
    const deadline = window.setTimeout(() => {
      if (!cancelled) setFailed(true);
    }, HANDOFF_DEADLINE_MS);
    void (async () => {
      let d: PanelDescriptor | null = null;
      try {
        d = await receivePopoutPanel(panelId);
      } catch (e: unknown) {
        console.warn("[PanelWindowApp] hand-off failed", e);
      }
      if (cancelled) return;
      window.clearTimeout(deadline);
      if (!d) {
        console.warn(`[PanelWindowApp] no hand-off for panel ${panelId}`);
        setFailed(true);
        return;
      }
      setDescriptor(d);
    })();
    return () => {
      cancelled = true;
      window.clearTimeout(deadline);
    };
  }, [panelId]);

  // Tell main we're leaving — before unload.
  useEffect(() => {
    if (!panelId || !descriptor) return;
    const onBeforeUnload = () => {
      farewellPopout(panelId, {
        x: window.screenX,
        y: window.screenY,
        width: window.innerWidth,
        height: window.innerHeight,
      });
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [panelId, descriptor]);

  // S9 acceptance polish — popout's OS title bar reads
  // "antiek · popout · <panel.title>" so the operator can identify
  // the popped-out panel from the OS window switcher.
  useEffect(() => {
    if (!descriptor) return;
    const prev = document.title;
    document.title = `antiek · popout · ${descriptor.title}`;
    return () => {
      document.title = prev;
    };
  }, [descriptor]);

  if (failed && !descriptor) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-ice-2 dark:bg-space-2 text-ink dark:text-bright p-8">
        <div role="alert" className="max-w-md text-center space-y-3">
          <h1 className="text-xl font-bold">This panel couldn't be opened.</h1>
          <p className="text-sm text-shadow-1 dark:text-moonlight">
            Pop it out again from the main Antiek window.
          </p>
          <button
            type="button"
            onClick={() => window.close()}
            className="px-3 py-1.5 rounded-md border border-rule dark:border-charcoal-1 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  if (!descriptor) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-ice-2 dark:bg-space-2 text-shadow-1 dark:text-moonlight">
        <span className="font-mono text-sm">handing off panel…</span>
      </div>
    );
  }

  const Renderer = PanelRegistry[descriptor.kind];

  return (
    <div className="h-screen w-screen flex flex-col bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright">
      <header className="h-9 shrink-0 px-3 flex items-center justify-between border-b-edge border-sun bg-ice-1 dark:bg-charcoal-1">
        <span className="font-mono text-xs font-semibold truncate">
          {descriptor.title}
        </span>
        <span className="font-mono text-xxs text-ink-mute dark:text-moonlight">
          popout · close window to re-dock
        </span>
      </header>
      <div className="flex-1 min-h-0 overflow-auto">
        <Suspense
          fallback={
            <div className="p-4 text-sm text-shadow-1 dark:text-moonlight italic">
              Loading…
            </div>
          }
        >
          <Renderer {...descriptor.props} />
        </Suspense>
      </div>
      <LemonToastViewport />
    </div>
  );
}
