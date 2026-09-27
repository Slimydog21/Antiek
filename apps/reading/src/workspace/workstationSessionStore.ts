/**
 * workstationSessionStore — the workstation SESSION client (reading-global
 * SPR-03): this stack's persistence client over api/workstations.ts (the
 * SPR-01 store's API). NAMED to avoid the corpus collision — the corpus's
 * tabTreeStore/workstationStore (the cockpit stack, D6/D2 chrome) is NOT on
 * this branch; THIS store is the persistence + session wiring only
 * (materializing reader tabs into reader windows). The merge seam is the
 * wire types in api/workstations.ts — the corpus's stores bind there.
 *
 * The rules it carries (the spec's SPR-03):
 *   - a reader tab's activation opens/focuses the reader window (the
 *     one-reader-per-document invariant, readerWindowId) — the reader
 *     mounts at the BUS position (useReadingState owns position; this
 *     store never carries a page number);
 *   - a workstation SWITCH tears down the outgoing workstation's open
 *     reader windows and replay-opens the incoming one's open reader tabs
 *     with DEFAULT geometry (position survives — the bus; geometry does
 *     not — windowsStore's session-scoped rule, unchanged);
 *   - a RELOAD restores zero windows (windowsStore's design); the session
 *     restores the container (the last-focused workstation — honestly
 *     PER-DEVICE, localStorage; the same operator may focus differently on
 *     two devices) and marks the URL-matching tab active (else the first);
 *   - the URL NEVER carries a workstation/tab parameter — this store never
 *     writes it (the URL audit is a proof, not a hope).
 */
import { create } from "zustand";

import {
  listWorkstations,
  type Workstation,
  type WorkstationTab,
} from "../api/workstations";
import { readerWindowId } from "../components/windows/openWindow";
import { useWindows } from "./windowsStore";

const FOCUS_KEY = "antiek.workstation.focus";

export interface WorkstationSessionState {
  /** The owner's workstations (SPR-01's server rows). */
  workstations: Workstation[];
  /** The last-focused workstation — honestly per-device (localStorage). */
  focusedWorkstationId: string | null;
  /** The active tab per workstation (null = none). */
  activeTabIdByWorkstation: Record<string, string | null>;
  /** The reader tabs whose windows are open, per workstation (tracked by
   *  tab id — geometry lives in windowsStore, session-scoped, NEVER here). */
  openReaderTabIdsByWorkstation: Record<string, string[]>;
  loaded: boolean;

  loadFromServer: () => Promise<void>;
  activateTab: (workstationId: string, tabId: string) => void;
  hopToTab: (workstationId: string, tabId: string) => void;
  switchWorkstation: (workstationId: string) => void;
  restoreForUrl: (documentId: string | null) => void;
  reset: () => void;
}

function tabOf(ws: Workstation | undefined, tabId: string): WorkstationTab | null {
  return ws?.tabs.find((t) => t.tab_id === tabId) ?? null;
}

export const useWorkstationSession = create<WorkstationSessionState>()((set, get) => ({
  workstations: [],
  focusedWorkstationId: null,
  activeTabIdByWorkstation: {},
  openReaderTabIdsByWorkstation: {},
  loaded: false,

  loadFromServer: async () => {
    const resp = await listWorkstations();
    const focused = (() => {
      try {
        return window.localStorage.getItem(FOCUS_KEY);
      } catch {
        return null;
      }
    })();
    set({
      workstations: resp.workstations,
      focusedWorkstationId:
        focused && resp.workstations.some((w) => w.workstation_id === focused)
          ? focused
          : (resp.workstations[0]?.workstation_id ?? null),
      loaded: true,
    });
  },

  activateTab: (workstationId, tabId) => {
    const ws = get().workstations.find((w) => w.workstation_id === workstationId);
    const tab = tabOf(ws, tabId);
    if (!ws || !tab) return;
    set((s) => ({
      activeTabIdByWorkstation: { ...s.activeTabIdByWorkstation, [workstationId]: tabId },
    }));
    if (tab.surface_kind !== "reader") return; // route/corpus tabs are the
    // corpus's chrome — this store records the activation honestly.
    const documentId = String(tab.surface_payload.documentId ?? "");
    if (!documentId) return;
    // The reader window: focus-instead-of-duplicate by construction; NO rect
    // (default geometry — geometry is session-scoped, never persisted). The
    // reader mounts at the bus position — this store never carries a page.
    openReaderWindow(workstationId, tabId, documentId);
  },

  hopToTab: (workstationId, tabId) => {
    // A hop IS an activation — the tab's surface returns at its bus position.
    get().activateTab(workstationId, tabId);
  },

  switchWorkstation: (workstationId) => {
    const state = get();
    const outgoing = state.focusedWorkstationId;
    if (outgoing === workstationId) return;
    // Tear down the outgoing workstation's open reader windows (the window
    // geometry dies with them — session-scoped, by design).
    if (outgoing) {
      for (const tabId of state.openReaderTabIdsByWorkstation[outgoing] ?? []) {
        const tab = tabOf(
          state.workstations.find((w) => w.workstation_id === outgoing),
          tabId,
        );
        const docId = String(tab?.surface_payload.documentId ?? "");
        if (docId) useWindows.getState().close(readerWindowId(docId));
      }
    }
    try {
      window.localStorage.setItem(FOCUS_KEY, workstationId);
    } catch {
      /* localStorage unavailable (private mode) — focus is best-effort */
    }
    set({ focusedWorkstationId: workstationId });
    // Replay-open the incoming workstation's open reader tabs — at their bus
    // positions (the reader's mount reads the bus), with DEFAULT geometry
    // (no rect anywhere in this call).
    for (const tabId of state.openReaderTabIdsByWorkstation[workstationId] ?? []) {
      const tab = tabOf(
        state.workstations.find((w) => w.workstation_id === workstationId),
        tabId,
      );
      const docId = String(tab?.surface_payload.documentId ?? "");
      if (docId) openReaderWindow(workstationId, tabId, docId);
    }
  },

  restoreForUrl: (documentId) => {
    const state = get();
    const ws = state.workstations.find(
      (w) => w.workstation_id === state.focusedWorkstationId,
    );
    if (!ws) return;
    // The URL-matching reader tab wins; else the workstation's first tab.
    // Either way the tab is marked ACTIVE — a cold /read/:id link renders
    // the surface with the container restored around it. Reader WINDOWS are
    // never re-opened on reload (a reload = zero windows, by design).
    const match = documentId
      ? ws.tabs.find(
          (t) =>
            t.surface_kind === "reader" &&
            String(t.surface_payload.documentId ?? "") === documentId,
        )
      : null;
    const active = match ?? ws.tabs[0] ?? null;
    if (!active) return;
    set((s) => ({
      activeTabIdByWorkstation: { ...s.activeTabIdByWorkstation, [ws.workstation_id]: active.tab_id },
    }));
  },

  reset: () =>
    set({
      workstations: [],
      focusedWorkstationId: null,
      activeTabIdByWorkstation: {},
      openReaderTabIdsByWorkstation: {},
      loaded: false,
    }),
}));

/** Open (or focus) a tab's reader window + record it open on the
 *  workstation. NO rect — the default geometry rule is structural. */
function openReaderWindow(workstationId: string, tabId: string, documentId: string): void {
  useWindows.getState().open(
    "reader",
    { documentId },
    { id: readerWindowId(documentId), title: "Source reader" },
  );
  useWorkstationSession.setState((s) => {
    const open = new Set(s.openReaderTabIdsByWorkstation[workstationId] ?? []);
    open.add(tabId);
    return {
      openReaderTabIdsByWorkstation: {
        ...s.openReaderTabIdsByWorkstation,
        [workstationId]: [...open],
      },
    };
  });
}
