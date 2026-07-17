/**
 * Workspace popout — S9 WP-9.4.
 *
 * Opens a named panel in its own OS-level browser window via
 * `window.open("/_panel/<panelId>", …)`. Cross-window sync rides on
 * BroadcastChannel("antiek-workspace"):
 *
 *   main → popout    "popout-init"      panel descriptor
 *   main → popout    "popout-close"     please close (operator closed in main)
 *   popout → main    "popout-ready"     hand-off acknowledged
 *   popout → main    "popout-bye"       window closing — re-add to main
 *
 * Browser support: BroadcastChannel works in every modern browser. If
 * undefined, popout opens but cannot sync; main shows a toast and the
 * popout will need to be manually re-instated when closed.
 */

import { toast } from "../components/lemon/LemonToast";
import type { PanelDescriptor } from "./panel.types";
import { useWorkspace } from "./WorkspaceStore";

const CHANNEL_NAME = "antiek-workspace";

type Msg =
  | { kind: "popout-init"; panelId: string; descriptor: PanelDescriptor }
  | { kind: "popout-close"; panelId: string }
  | { kind: "popout-ready"; panelId: string }
  | { kind: "popout-consumed"; panelId: string; path: string }
  | { kind: "popout-consumed-ack"; panelId: string }
  | { kind: "popout-bye"; panelId: string; rect?: { x: number; y: number; width: number; height: number } };

function makeChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") return null;
  return new BroadcastChannel(CHANNEL_NAME);
}

/** Open a panel in its own OS window. Removes it from the main-window
 *  in-tab arrays + records its descriptor for handoff to the popout. */
export function openPopoutFor(panelId: string): void {
  const ws = useWorkspace.getState();
  const panel = ws.panels[panelId];
  if (!panel) return;

  const channel = makeChannel();
  if (!channel) {
    toast.warn("Popout sync is unavailable in this browser; window state will not roundtrip.");
  }

  // Open the OS window first so the user-gesture-required popup
  // permission applies. The popout's main payload is the panel id;
  // the descriptor is shipped over BroadcastChannel after handoff.
  const width = Math.max(420, panel.rect.width + 40);
  const height = Math.max(280, panel.rect.height + 80);
  const win = window.open(
    `/_panel/${encodeURIComponent(panelId)}`,
    `antiek_popout_${panelId}`,
    `popup,width=${width},height=${height},left=120,top=120`,
  );
  if (!win) {
    toast.err("Popup blocked. Allow popups for this site, then try again.");
    channel?.close();
    return;
  }

  // Move the panel into "popout" mode in the main workspace store —
  // the panel descriptor remains in `panels` but it's removed from
  // every in-tab dock/floating array. PanelLayoutPanel returns null
  // for mode=popout, so it disappears from main rendering.
  ws.setMode(panelId, "popout");

  if (channel) {
    // Send the descriptor when popout signals it's ready.
    const onMessage = (e: MessageEvent<Msg>) => {
      const m = e.data;
      if (!m) return;
      if (m.kind === "popout-ready" && m.panelId === panelId) {
        channel.postMessage({
          kind: "popout-init",
          panelId,
          descriptor: panel,
        } satisfies Msg);
      } else if (m.kind === "popout-bye" && m.panelId === panelId) {
        // Operator closed the popout window. Move the panel back to
        // floating in the main window at its last known rect (if the
        // popout reported one) or its previous rect.
        const ws2 = useWorkspace.getState();
        if (!ws2.panels[panelId]) return;
        if (m.rect) ws2.setRect(panelId, m.rect);
        ws2.setMode(panelId, "floating");
        toast.info(`${panel.title} re-docked from popout.`);
        channel.removeEventListener("message", onMessage);
        channel.close();
      } else if (m.kind === "popout-consumed" && m.panelId === panelId) {
        // The popout deliberately handed its content to the main product view.
        // Consume the exact descriptor instead of re-docking it on unload.
        useWorkspace.getState().close(panelId);
        window.history.pushState({}, "", m.path);
        window.dispatchEvent(new PopStateEvent("popstate"));
        channel.postMessage({ kind: "popout-consumed-ack", panelId } satisfies Msg);
        channel.removeEventListener("message", onMessage);
        channel.close();
      }
    };
    channel.addEventListener("message", onMessage);
  }
}

/**
 * Hand a popout-owned panel into the main product view. The main tab consumes
 * the exact descriptor; the OS popout then closes instead of navigating itself
 * and leaving a hidden `popout` descriptor behind.
 */
export function handoffPopoutToMain(panelId: string, path: string): void {
  const opener = window.opener;
  const channel = makeChannel();
  if (opener && !opener.closed && channel) {
    let settled = false;
    let fallbackTimer: number | undefined;
    const closePopout = () => {
      if (settled) return;
      settled = true;
      if (fallbackTimer !== undefined) window.clearTimeout(fallbackTimer);
      channel.close();
      window.close();
    };
    channel.addEventListener("message", (event: MessageEvent<Msg>) => {
      if (event.data?.kind === "popout-consumed-ack" && event.data.panelId === panelId) {
        closePopout();
      }
    });
    channel.postMessage({ kind: "popout-consumed", panelId, path } satisfies Msg);
    // If the main tab disappears between the opener check and delivery, retain
    // the only usable window and navigate it. Its beforeunload then re-docks the
    // exact descriptor in any surviving main tab; never close without an ACK.
    fallbackTimer = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      channel.close();
      window.location.assign(path);
    }, 1000);
    return;
  }
  // Honest standalone fallback: keep the only live window open and navigate it.
  channel?.close();
  window.location.assign(path);
}

/** Called by the popout window. Hands back the panel + tells main to
 *  re-add it on close. Returns the panel descriptor once main responds. */
export async function receivePopoutPanel(
  panelId: string,
): Promise<PanelDescriptor | null> {
  const channel = makeChannel();
  if (!channel) return null;

  return new Promise<PanelDescriptor | null>((resolve) => {
    let resolved = false;
    const onMessage = (e: MessageEvent<Msg>) => {
      const m = e.data;
      if (!m) return;
      if (m.kind === "popout-init" && m.panelId === panelId) {
        resolved = true;
        channel.removeEventListener("message", onMessage);
        resolve(m.descriptor);
      }
    };
    channel.addEventListener("message", onMessage);
    channel.postMessage({ kind: "popout-ready", panelId } satisfies Msg);

    // Hand-off must complete within 2s; otherwise we have no main window
    // (popout reloaded standalone, or the main tab closed first).
    setTimeout(() => {
      if (!resolved) {
        channel.removeEventListener("message", onMessage);
        channel.close();
        resolve(null);
      }
    }, 2000);
  });
}

/** Send "I'm closing" before the popout window unloads. */
export function farewellPopout(
  panelId: string,
  rect?: { x: number; y: number; width: number; height: number },
): void {
  const channel = makeChannel();
  if (!channel) return;
  channel.postMessage({ kind: "popout-bye", panelId, rect } satisfies Msg);
  // Give the post time to flush before close
  channel.close();
}
