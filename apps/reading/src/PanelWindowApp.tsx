import { Suspense, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { LemonToastViewport } from "./components/lemon/LemonToast";
import { PanelRegistry } from "./workspace/PanelRegistry";
import {
  disablePersistence,
  enablePersistence,
} from "./workspace/WorkspaceStore";
import { farewellPopout, handoffPopoutToMain, receivePopoutPanel } from "./workspace/popout";
import type { PanelDescriptor } from "./workspace/panel.types";
import {
  PanelInstanceProvider,
  PanelMainViewHandoffProvider,
} from "./workspace/panelInstanceContext";

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
 */
export default function PanelWindowApp() {
  const params = useParams<{ panelId?: string }>();
  const panelId = params.panelId ? decodeURIComponent(params.panelId) : null;
  const [descriptor, setDescriptor] = useState<PanelDescriptor | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    disablePersistence();
    return () => enablePersistence();
  }, []);

  useEffect(() => {
    if (!panelId) {
      setError("No panel id in URL.");
      return;
    }
    let cancelled = false;
    void (async () => {
      const d = await receivePopoutPanel(panelId);
      if (cancelled) return;
      if (!d) {
        setError(
          "Could not hand off this panel from the main window. " +
            "BroadcastChannel may be unsupported or the main tab may have closed.",
        );
        return;
      }
      setDescriptor(d);
    })();
    return () => {
      cancelled = true;
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

  if (error) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-ice-2 dark:bg-space-2 text-ink dark:text-bright p-8">
        <div className="max-w-md text-center">
          <h1 className="text-xl font-bold mb-2">Panel hand-off failed</h1>
          <p className="text-sm text-shadow-1 dark:text-moonlight">{error}</p>
          <p className="text-xs font-mono text-ink-mute dark:text-moonlight mt-4">
            panel id: {panelId}
          </p>
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
        <span className="font-mono text-[12px] font-semibold truncate">
          {descriptor.title}
        </span>
        <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
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
          <PanelInstanceProvider value={descriptor.id}>
            <PanelMainViewHandoffProvider
              value={(path) => handoffPopoutToMain(descriptor.id, path)}
            >
              <Renderer {...descriptor.props} />
            </PanelMainViewHandoffProvider>
          </PanelInstanceProvider>
        </Suspense>
      </div>
      <LemonToastViewport />
    </div>
  );
}
