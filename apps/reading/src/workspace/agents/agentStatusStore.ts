/**
 * agents/agentStatusStore.ts — SPR-10 M1/M2/M4: the raw-only SIDECAR store.
 * LAZY module (imports companionStore, treeStore, zustand).
 *
 * It stores observations and debounce state, nothing derived: membership
 * and rollups come from the context tree (`collectRuns` over
 * `useContextTree`) at read time, seen state from workspace/seen.ts, the
 * active view from companionStore. It never calls `publishTree` and never
 * writes `AgentNode.status`; `RUN_STATES` (contracts/tree.ts:219) stays
 * closed and this store needs no new state in it.
 *
 * Sources call `observe(summaries, watched, now)` (the list poller) or
 * `setNeedsInput(runId, flag)` (the SPR-B seam). A push source replaces
 * pollingAdapter.ts by calling the same two.
 */
import { useMemo } from "react";
import { create } from "zustand";

import { useSeenVersion } from "../../hooks/useSeenVersion";
import { subscribeWorkspaceOwner } from "../../lib/accountWorkspaceOwner";
import type { InvestigationSummary } from "../../lib/api";
import { useCompanion } from "../companionStore";
import { companionVisible } from "../companionVisibility";
import type { ContextTree } from "../contracts/tree";
import { useContextTree, useContextTreeStore } from "../contracts/treeStore";
import { lastSeenAt, markSeen } from "../seen";
import {
  attentionOf,
  collectRuns,
  phaseOf,
  rollup,
  toastFor,
  type AgentStatus,
  type Attention,
  type RawObservation,
  type RunEntry,
  type Transition,
} from "./agentStatus";
import { debounceStep, inStartupGrace, type DebounceState } from "./debounce";

export interface StatusClock {
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export const realClock: StatusClock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => window.setTimeout(fn, ms),
  clearTimeout: (h) => window.clearTimeout(h as number),
};

export interface TransitionEvent {
  runId: string;
  entry: RunEntry;
  prev: AgentStatus | undefined;
  next: AgentStatus;
  transition: Transition;
}

interface AgentStatusState {
  epoch: number;
  startedAt: number | null;
  raw: ReadonlyMap<string, RawObservation>;
  pending: ReadonlyMap<string, DebounceState>;
  changeSeq: number;
  /** The latest list snapshot a source handed to `observe` (confirm re-reads). */
  snapshot: readonly InvestigationSummary[];
  start: (clock: StatusClock) => void;
  stop: () => void;
  observe: (summaries: readonly InvestigationSummary[], watched: ReadonlySet<string>, now: number) => void;
  setNeedsInput: (runId: string, flag: boolean) => void;
  markFocused: (runId: string) => void;
  reset: () => void;
}

const EMPTY_RAW: ReadonlyMap<string, RawObservation> = new Map();
const EMPTY_PENDING: ReadonlyMap<string, DebounceState> = new Map();

// Module-level plumbing (not state): the clock, confirm timers, listeners.
let clock: StatusClock = realClock;
let running = false;
let companionUnsub: (() => void) | null = null;
const confirmTimers = new Map<string, unknown>();
const transitionListeners = new Set<(t: TransitionEvent) => void>();
const resetListeners = new Set<() => void>();

export function subscribeTransitions(l: (t: TransitionEvent) => void): () => void {
  transitionListeners.add(l);
  return () => { transitionListeners.delete(l); };
}

export function subscribeReset(l: () => void): () => void {
  resetListeners.add(l);
  return () => { resetListeners.delete(l); };
}

// ---------------------------------------------------------------------------
// Entries: derived from the tree, cached per tree identity
// ---------------------------------------------------------------------------

const runsCache = new WeakMap<ContextTree, ReadonlyMap<string, RunEntry>>();

/** collectRuns, identity-stable per tree object. */
export function runsOf(tree: ContextTree): ReadonlyMap<string, RunEntry> {
  const hit = runsCache.get(tree);
  if (hit) return hit;
  const built = collectRuns(tree);
  runsCache.set(tree, built);
  return built;
}

function currentRuns(): ReadonlyMap<string, RunEntry> {
  return runsOf(useContextTreeStore.getState().tree);
}

function isActiveView(entry: RunEntry): boolean {
  return companionVisible() && useCompanion.getState().activeTabId === entry.viewId;
}

function obsOf(s: InvestigationSummary, at: number, needsInput: true | undefined): RawObservation {
  return {
    status: s.status,
    completedAt: s.completed_at,
    since: s.completed_at ?? s.started_at,
    title: s.question,
    observedAt: at,
    ...(needsInput ? { needsInput: true } : {}),
  };
}

function rawDiffers(a: RawObservation, b: RawObservation): boolean {
  return a.status !== b.status || a.completedAt !== b.completedAt || a.since !== b.since || a.title !== b.title || a.needsInput !== b.needsInput;
}

function clearConfirm(id: string): void {
  const h = confirmTimers.get(id);
  if (h !== undefined) {
    clock.clearTimeout(h);
    confirmTimers.delete(id);
  }
}

function clearAllConfirms(): void {
  for (const id of [...confirmTimers.keys()]) clearConfirm(id);
}

export const useAgentStatusStore = create<AgentStatusState>()((set, get) => {
  function emitTransition(id: string, before: RawObservation | undefined, after: RawObservation, at: number): void {
    const entry = currentRuns().get(id);
    if (!entry) return;
    const lastSeen = entry.investigationId !== undefined ? lastSeenAt(entry.investigationId) : null;
    const prev = before ? attentionOf(before, lastSeen).state : undefined;
    const next = attentionOf(after, lastSeen).state;
    const startedAt = get().startedAt ?? at;
    const transition = toastFor(prev, next, { isActiveView: isActiveView(entry), inStartupGrace: inStartupGrace(startedAt, at) });
    const ev: TransitionEvent = { runId: id, entry, prev, next, transition };
    for (const l of [...transitionListeners]) l(ev);
  }

  function commitRaw(id: string, obs: RawObservation, at: number): void {
    const before = get().raw.get(id);
    const raw = new Map(get().raw);
    raw.set(id, obs);
    set((s) => ({ raw, changeSeq: s.changeSeq + 1 }));
    emitTransition(id, before, obs, at);
  }

  function applyObservation(id: string, obs: RawObservation, source: "poll" | "confirm", at: number): void {
    const state = get().pending.get(id);
    const r = debounceStep(state, { phase: phaseOf(obs.status).phase, at, source });
    const pending = new Map(get().pending);
    pending.set(id, r.next);
    set({ pending });
    if (r.commit !== null) {
      commitRaw(id, obs, at);
    } else if (state?.kind === "settled" && r.next.kind === "settled") {
      // Same phase: refresh the observation silently when a field moved
      // (a title landing, a completed_at), still through the one commit path.
      const prev = get().raw.get(id);
      if (prev && rawDiffers(prev, obs)) commitRaw(id, obs, at);
    }
    clearConfirm(id);
    if (r.confirmAt !== null) {
      const delay = Math.max(0, r.confirmAt - at);
      const epoch = get().epoch;
      const handle = clock.setTimeout(() => {
        confirmTimers.delete(id);
        if (get().epoch !== epoch) return;
        const s = get().snapshot.find((x) => x.investigation_id === id);
        if (!s) return;
        const now = clock.now();
        applyObservation(id, obsOf(s, now, get().raw.get(id)?.needsInput), "confirm", now);
      }, delay);
      confirmTimers.set(id, handle);
    }
  }

  function runOfView(viewId: string): string | undefined {
    for (const e of currentRuns().values()) if (e.viewId === viewId) return e.runId;
    const t = useCompanion.getState().tabs.find((x) => x.id === viewId);
    return t?.kind === "research-thread" ? t.investigationId : undefined;
  }

  return {
    epoch: 0,
    startedAt: null,
    raw: EMPTY_RAW,
    pending: EMPTY_PENDING,
    changeSeq: 0,
    snapshot: [],

    start: (c) => {
      clock = c;
      if (running) return;
      running = true;
      set({ startedAt: clock.now() });
      // Seen-on-focus (graft 1): a tab activated while the window has focus
      // and the companion is on screen is marked seen. No window `focus`
      // listener by design (handoff §6.10).
      companionUnsub = useCompanion.subscribe((s, prev) => {
        if (s.activeTabId === prev.activeTabId || !s.activeTabId) return;
        if (!document.hasFocus() || !companionVisible()) return;
        const runId = runOfView(s.activeTabId);
        if (runId !== undefined) get().markFocused(runId);
      });
    },

    stop: () => {
      clearAllConfirms();
      companionUnsub?.();
      companionUnsub = null;
      running = false;
    },

    observe: (summaries, watched, now) => {
      set({ snapshot: summaries });
      const byId = new Map<string, InvestigationSummary>();
      for (const s of summaries) byId.set(s.investigation_id, s);
      for (const id of watched) {
        const s = byId.get(id);
        // Absent from the window: keep the previous raw (never regress).
        if (!s) continue;
        applyObservation(id, obsOf(s, now, get().raw.get(id)?.needsInput), "poll", now);
      }
    },

    setNeedsInput: (runId, flag) => {
      const at = clock.now();
      const prev = get().raw.get(runId);
      const entry = currentRuns().get(runId);
      const base: RawObservation = prev ?? {
        status: entry?.treeState,
        completedAt: null,
        since: entry?.treeSince ?? null,
        title: entry?.title ?? null,
        observedAt: at,
      };
      const { needsInput: _drop, ...rest } = base;
      void _drop;
      const next: RawObservation = { ...rest, observedAt: at, ...(flag ? { needsInput: true } : {}) };
      commitRaw(runId, next, at);
    },

    markFocused: (runId) => {
      const entry = currentRuns().get(runId);
      const fromTab = useCompanion.getState().tabs.some((t) => t.kind === "research-thread" && t.investigationId === runId);
      const investigationId = entry?.investigationId ?? (fromTab ? runId : undefined);
      if (investigationId) markSeen(investigationId);
    },

    reset: () => {
      clearAllConfirms();
      set((s) => ({
        epoch: s.epoch + 1,
        startedAt: running ? clock.now() : null,
        raw: EMPTY_RAW,
        pending: EMPTY_PENDING,
        snapshot: [],
        changeSeq: s.changeSeq + 1,
      }));
      for (const l of [...resetListeners]) l();
    },
  };
});

// Owner epoch: mirrors preBackend.ts:299-301.
subscribeWorkspaceOwner(() => useAgentStatusStore.getState().reset());

// ---------------------------------------------------------------------------
// Read hooks (everything derived at read time)
// ---------------------------------------------------------------------------

export function attentionFor(entry: RunEntry | undefined, raw: RawObservation | undefined): Attention {
  const lastSeen = entry?.investigationId !== undefined ? lastSeenAt(entry.investigationId) : null;
  const absent = entry?.kind === "dialogue" ? "no-run" : "outside-window";
  if (raw) return attentionOf(raw, lastSeen, absent);
  if (entry?.treeState !== undefined) {
    const finished = phaseOf(entry.treeState).phase === "finished";
    return attentionOf(
      { status: entry.treeState, completedAt: finished ? entry.treeSince ?? null : null, since: entry.treeSince ?? null, title: entry.title, observedAt: 0 },
      lastSeen,
      absent,
    );
  }
  return attentionOf(undefined, lastSeen, absent);
}

export function useRunEntries(): ReadonlyMap<string, RunEntry> {
  return useContextTree(runsOf);
}

/** Precedence: store raw > tree state > undefined (no-run / outside-window). */
export function useAgentAttention(runId: string): Attention {
  const entries = useRunEntries();
  const raw = useAgentStatusStore((s) => s.raw.get(runId));
  useSeenVersion();
  return attentionFor(entries.get(runId), raw);
}

function rollupOver(entries: Iterable<RunEntry>, raw: ReadonlyMap<string, RawObservation>): AgentStatus | null {
  const xs: AgentStatus[] = [];
  for (const e of entries) xs.push(attentionFor(e, raw.get(e.runId)).state);
  return rollup(xs);
}

/** Max over entries whose groupPath contains the project (linked agents
 *  sit on their own investigation node, so the path walk is mandatory). */
export function useProjectAttention(projectId: string): AgentStatus | null {
  const entries = useRunEntries();
  const raw = useAgentStatusStore((s) => s.raw);
  useSeenVersion();
  return rollupOver([...entries.values()].filter((e) => e.groupPath.includes(projectId)), raw);
}

export function useWorkspaceAttention(): AgentStatus | null {
  const entries = useRunEntries();
  const raw = useAgentStatusStore((s) => s.raw);
  useSeenVersion();
  return rollupOver(entries.values(), raw);
}

const EMPTY_WATCHED: ReadonlySet<string> = new Set();

/** The research entries' investigation ids (what the poller watches). */
export function useWatchedIds(): ReadonlySet<string> {
  const entries = useRunEntries();
  return useMemo(() => {
    const out = new Set<string>();
    for (const e of entries.values()) if (e.kind === "research-thread" && e.investigationId !== undefined) out.add(e.investigationId);
    return out.size ? out : EMPTY_WATCHED;
  }, [entries]);
}
