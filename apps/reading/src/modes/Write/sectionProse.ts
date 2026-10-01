import type { JSONContent } from "@tiptap/core";
import { ApiError, updateSectionProse } from "../../lib/api";
import { generateSection, type GenerationResult } from "./writeApi";
import { getSectionProseOwner, subscribeSectionProseOwner } from "./sectionProseOwner";
import { useTabTrees } from "../../workspace/tabTreeStore";
export { setSectionProseOwner, suspendSectionProseDispatch } from "./sectionProseOwner";

type SaveState =
  | { status: "idle" | "pending" | "saved" | "paused" }
  | { status: "error"; message: string };
type GenerationState =
  | { status: "idle" | "generating" }
  | { status: "result"; result: GenerationResult }
  | { status: "error"; reason: string | null };

interface ProseSnapshot {
  available: boolean;
  dispatchAllowed: boolean;
  draft: string | null;
  document: JSONContent | null;
  saved: string | null;
  provenance: Record<string, string[]>;
  revision: number;
  save: SaveState;
  generation: GenerationState;
}

const DEBOUNCE_MS = 800;
const CLEAN_CACHE_LIMIT = 32;
const sections = new Map<string, SectionProse>();
let ownerEpoch = getSectionProseOwner().epoch;
subscribeSectionProseOwner(() => {
  const next = getSectionProseOwner();
  if (next.epoch !== ownerEpoch) {
    ownerEpoch = next.epoch;
    for (const section of sections.values()) section.dispose();
    sections.clear();
  } else {
    for (const section of sections.values()) {
      if (next.suspended) section.pause();
      else section.resume();
    }
  }
});
useTabTrees.subscribe((next, previous) => {
  if (next.contextEpoch === previous.contextEpoch && next.projectId === previous.projectId) return;
  for (const section of sections.values()) section.dispose();
  sections.clear();
});

function trimCleanCache(): void {
  const idle = [...sections].filter(([, section]) => section.evictable);
  for (const [key] of idle.slice(0, Math.max(0, idle.length - CLEAN_CACHE_LIMIT))) {
    sections.delete(key);
    // A clean handle can still be finishing a React unsubscribe/subscribe.
  }
}

export function sectionProse(
  deliverableId: string,
  sectionId: string,
  prose: string | null,
  provenance: Record<string, string[]>,
): SectionProse {
  const key = JSON.stringify([deliverableId, sectionId]);
  const existing = sections.get(key);
  if (existing) {
    sections.delete(key);
    sections.set(key, existing);
    return existing;
  }
  const session = new SectionProse(key, deliverableId, sectionId, prose, provenance);
  if (getSectionProseOwner().owner === null) session.dispose();
  else sections.set(key, session);
  return session;
}

/** Revoke absent sessions before React can flush their final unsubscribe. */
export function reconcileDeliverableProse(deliverableId: string, sectionIds: readonly string[]): void {
  const admitted = new Set(sectionIds);
  for (const [key, section] of sections) {
    if (section.deliverableId !== deliverableId || admitted.has(section.sectionId)) continue;
    section.dispose();
    sections.delete(key);
  }
}

export function discardDeliverableProse(deliverableId: string): void {
  for (const [key, section] of sections) {
    if (section.deliverableId !== deliverableId) continue;
    section.dispose();
    sections.delete(key);
  }
}

/** One owner/section mutation lifetime, shared by every mounted view of that section. */
class SectionProse {
  private snapshot: ProseSnapshot;
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private saving: Promise<boolean> | null = null;
  private locallyChanged = false;
  // null keeps the existing owner-only policy for consumers without a
  // scoped detail view. Outline enrolls its sessions in detail validation.
  private scopedAuthorization: boolean | null = null;
  private readonly epoch = ownerEpoch;
  private readonly contextEpoch = useTabTrees.getState().contextEpoch;
  private readonly projectId = useTabTrees.getState().projectId;

  constructor(private readonly key: string, readonly deliverableId: string, readonly sectionId: string, prose: string | null, provenance: Record<string, string[]>) {
    this.snapshot = {
      available: true, dispatchAllowed: getSectionProseOwner().owner !== null && !getSectionProseOwner().suspended, draft: prose, document: null, saved: prose, provenance, revision: 0,
      save: { status: "idle" }, generation: { status: "idle" },
    };
  }

  getSnapshot = (): ProseSnapshot => this.snapshot;

  private current(): boolean {
    const tabs = useTabTrees.getState();
    return this.snapshot.available && this.epoch === getSectionProseOwner().epoch && getSectionProseOwner().owner !== null &&
      tabs.contextEpoch === this.contextEpoch && tabs.projectId === this.projectId;
  }

  private canDispatch(): boolean { return this.current() && !getSectionProseOwner().suspended && this.scopedAuthorization !== false; }

  setScopedAuthorization(authorized: boolean): void {
    if (this.scopedAuthorization === authorized) return;
    this.scopedAuthorization = authorized;
    if (authorized) this.resume();
    else this.pause();
  }

  pause(): void {
    if (this.scopedAuthorization !== null) this.scopedAuthorization = false;
    this.clearTimer();
    this.publish({ dispatchAllowed: false, ...(this.snapshot.draft !== this.snapshot.saved ? { save: { status: "paused" } } : {}) });
  }

  resume(): void {
    if (!this.current()) return;
    this.publish({ dispatchAllowed: this.canDispatch() });
    void (this.saving ?? Promise.resolve()).then(() => {
      if (this.canDispatch() && this.snapshot.draft !== this.snapshot.saved) void this.flush();
    });
  }

  subscribe = (listener: () => void): (() => void) => {
    if (!this.current()) this.dispose();
    if (this.current() && !sections.has(this.key)) sections.set(this.key, this);
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) {
        if (this.timer !== null) void this.flush();
        trimCleanCache();
      }
    };
  };

  get evictable(): boolean {
    return this.listeners.size === 0 && this.saving === null && this.timer === null &&
      this.snapshot.generation.status !== "generating" && this.snapshot.draft === this.snapshot.saved;
  }

  private publish(patch: Partial<ProseSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener();
  }

  private clearTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  dispose(): void {
    this.clearTimer();
    this.publish({ available: false, dispatchAllowed: false, draft: null, document: null, saved: null, provenance: {}, generation: { status: "idle" }, save: { status: "idle" } });
  }

  seed(prose: string | null, provenance: Record<string, string[]>): void {
    if (!this.current() || this.locallyChanged) return;
    if (prose === this.snapshot.saved && provenance === this.snapshot.provenance) return;
    this.publish({ draft: prose, saved: prose, provenance });
  }

  edit = (text: string, document: JSONContent | null): void => {
    if (!this.current() || this.snapshot.generation.status === "generating") return;
    this.locallyChanged = true;
    this.publish({ draft: text, document, save: { status: this.canDispatch() ? "pending" : "paused" } });
    this.clearTimer();
    if (this.canDispatch()) this.timer = setTimeout(() => { this.timer = null; void this.flush(); }, DEBOUNCE_MS);
  };

  flush = (): Promise<boolean> => {
    this.clearTimer();
    if (!this.canDispatch()) return Promise.resolve(false);
    if (this.saving) return this.saving;
    const run = this.saveLatest();
    this.saving = run;
    void run.finally(() => { this.saving = null; trimCleanCache(); });
    return run;
  };

  private async saveLatest(): Promise<boolean> {
    while (this.current() && this.snapshot.draft !== this.snapshot.saved) {
      if (!this.canDispatch()) { this.publish({ save: { status: "paused" } }); return false; }
      const text = this.snapshot.draft;
      if (text === null) return true;
      if (text.length === 0) {
        this.publish({ save: { status: "error", message: "An empty draft cannot be saved yet. Your edit is kept here." } });
        return false;
      }
      const original = this.snapshot.saved;
      this.publish({ save: { status: "pending" } });
      try {
        await updateSectionProse(this.sectionId, {
          prose_text: text, original_text: original ?? undefined, promote_to_graph: false,
        });
      } catch (error) {
        if (!this.current()) return false;
        const message = error instanceof ApiError ? `HTTP ${error.status}` : error instanceof Error ? error.message : String(error);
        this.publish({ save: { status: "error", message } });
        return false;
      }
      if (!this.current()) return false;
      this.publish({ saved: text, save: { status: this.snapshot.draft === text ? "saved" : "pending" } });
    }
    if (this.current() && this.snapshot.save.status === "pending") this.publish({ save: { status: "saved" } });
    return this.current();
  }

  generate = async (): Promise<void> => {
    if (!this.canDispatch() || this.snapshot.generation.status === "generating") return;
    this.publish({ generation: { status: "generating" } });
    try {
      if (!(await this.flush()) || !this.canDispatch()) return;
      const result = await generateSection(this.sectionId);
      if (!this.current()) return;
      if (result.status === "generated" && result.prose_text) {
        this.locallyChanged = true;
        this.publish({
          draft: result.prose_text, document: null, saved: result.prose_text,
          provenance: result.prose_provenance ?? {}, revision: this.snapshot.revision + 1,
          save: { status: "idle" }, generation: { status: "result", result },
        });
      } else this.publish({ generation: { status: "result", result } });
    } catch (error) {
      if (!this.current()) return;
      const reason = error instanceof ApiError && error.status === 503 ? null : String(error);
      this.publish({ generation: { status: "error", reason } });
    } finally {
      if (this.current() && this.getSnapshot().generation.status === "generating") this.publish({ generation: { status: "idle" } });
      trimCleanCache();
    }
  };
}
