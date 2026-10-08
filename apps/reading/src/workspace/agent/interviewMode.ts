/**
 * interviewMode.ts — the project-creation interview (SPR-07 M8; refs
 * patterns 18/20). The same pane with a HIDDEN first turn ("Begin the
 * interview."), one question at a time, options as cards from a fenced
 * `@@options` JSON block, and a confirm-only `project_seed` action that
 * hands {title, prompt, sources} to SPR-03's intake through ONE seam,
 * `subscribeProjectSeed` (repair C2; SEAMS.md §1) — never submitProject
 * (the intake owns the paid POST; handoff F6). A seed nobody takes is held
 * in order, and a consumer that throws can neither block the others nor
 * lose the seed (second repair, finding 3).
 *
 * INTERVIEW_SYSTEM_PROMPT duplicates SPR-03's INTERVIEW_PROMPT text until
 * #3749 lands a shared export (F6): one de-dup edit then.
 */
import type { AiAction } from "../../components/ai/aiActions";
import { awaitWorkspaceOwnerSession, isWorkspaceOwnerSession, subscribeWorkspaceOwnerAdmission, workspaceOwnerAdmission, workspaceOwnerSession, type WorkspaceOwnerSession } from "../../lib/accountWorkspaceOwner";

export const INTERVIEW_FIRST_TURN = "Begin the interview.";

export const INTERVIEW_SYSTEM_PROMPT = [
  "You are starting a new research project with the user. Interview them: ask ONE question at a time,",
  "the most useful next question, never a list of questions. Each question may carry an options card:",
  "a fenced block `@@options` ... `@@end` holding JSON {\"question\", \"options\": [..], \"allowCustom\": true}.",
  "Stop as soon as something concrete arrives (a title and a one-paragraph prompt are enough), and then",
  "append exactly one project_seed action {title, prompt, sources?} in the @@actions block. The user",
  "confirms the seed; never assume the project exists.",
].join(" ");

export interface OptionCard {
  question: string;
  options: string[];
  allowCustom: boolean;
}

export interface ProjectSeed {
  title: string;
  prompt: string;
  sources?: string[];
}

const OPTIONS_OPEN = /(?:^|\n)\s*@@options\s*\n/;
const OPTIONS_CLOSE = /\n\s*@@end\s*$/;

/** Splits the prose from a trailing `@@options` card; a malformed card is
 *  dropped (prose stays), never half-rendered. */
export function parseOptionCard(text: string): { prose: string; card: OptionCard | null } {
  const open = text.match(OPTIONS_OPEN);
  if (!open || open.index === undefined) return { prose: text.trim(), card: null };
  const prose = text.slice(0, open.index).trim();
  let body = text.slice(open.index + open[0].length);
  const close = body.match(OPTIONS_CLOSE);
  if (close && close.index !== undefined) body = body.slice(0, close.index);
  try {
    const parsed: unknown = JSON.parse(body.trim());
    if (typeof parsed !== "object" || parsed === null) return { prose, card: null };
    const p = parsed as Record<string, unknown>;
    const options = Array.isArray(p.options) && p.options.every((o) => typeof o === "string") ? (p.options as string[]) : null;
    if (!options || options.length === 0) return { prose, card: null };
    return {
      prose,
      card: { question: typeof p.question === "string" ? p.question : prose, options, allowCustom: p.allowCustom !== false },
    };
  } catch {
    return { prose, card: null };
  }
}

export function seedFromActions(actions: readonly AiAction[]): ProjectSeed | null {
  for (const a of actions) {
    if (a.kind === "project_seed") return { title: a.title, prompt: a.prompt, ...(a.sources ? { sources: a.sources } : {}) };
  }
  return null;
}

export type ProjectSeedConsumer = (seed: ProjectSeed) => void;

interface Registration {
  owner: WorkspaceOwnerSession;
  generation: number;
  consumer: ProjectSeedConsumer;
}
interface OwnedSeed {
  owner: WorkspaceOwnerSession;
  generation: number;
  order: number;
  seed: ProjectSeed;
  attempted: Set<Registration>;
}
interface Broadcast {
  value: OwnedSeed;
  remaining: Registration[];
  delivered: number;
  failed: number;
}

const consumers = new Map<ProjectSeedConsumer, Registration>();
let held: OwnedSeed[] = [];
const broadcasts = new Set<Broadcast>();
const pending = new Set<Registration>();
let generation = 0;
let order = 0;
let draining = false;
let seamOwner = workspaceOwnerSession();
let confirmedOwner: WorkspaceOwnerSession | null = null;

const copyOf = (s: ProjectSeed): ProjectSeed => ({ title: s.title, prompt: s.prompt, ...(s.sources ? { sources: [...s.sources] } : {}) });

function sameLifetime(owner: WorkspaceOwnerSession, capturedGeneration: number): boolean {
  const admission = workspaceOwnerAdmission();
  return owner.subject !== null && owner === admission.session && capturedGeneration === generation
    && admission.state !== "retiring" && admission.state !== "failed";
}
function admitted(owner: WorkspaceOwnerSession, capturedGeneration: number): boolean {
  return sameLifetime(owner, capturedGeneration) && confirmedOwner === owner && isWorkspaceOwnerSession(owner);
}
function current(registration: Registration): boolean {
  return consumers.get(registration.consumer) === registration && admitted(registration.owner, registration.generation);
}

/** Faults are counted without stopping another current consumer. Each callback
 * receives an independent copy, including the mutable sources array. */
function deliver(consumer: ProjectSeedConsumer, seed: ProjectSeed): boolean {
  try {
    consumer(copyOf(seed));
    return true;
  } catch (err) {
    console.error("[antiek/agent] a project-seed consumer threw; the seed is kept for the next intake:", err);
    return false;
  }
}

function deliverBroadcast(broadcast: Broadcast): void {
  const value = broadcast.value;
  while (broadcast.remaining.length > 0 && admitted(value.owner, value.generation)) {
    const registration = broadcast.remaining.shift()!;
    if (!current(registration)) continue;
    value.attempted.add(registration);
    if (deliver(registration.consumer, value.seed)) broadcast.delivered++;
    else broadcast.failed++;
    // A synchronous consumer can replace the owner or reset this seam. The
    // old record must never publish into the replacement queue.
    if (!sameLifetime(value.owner, value.generation)) return;
  }
  if (broadcast.remaining.length === 0 && admitted(value.owner, value.generation)) {
    broadcasts.delete(broadcast);
    if (broadcast.delivered === 0) {
      held.push(value);
      held.sort((a, b) => a.order - b.order);
    }
  }
}

function drainHeld(registration: Registration): void {
  for (const value of [...held]) {
    if (!current(registration)) {
      if (sameLifetime(registration.owner, registration.generation)
          && consumers.get(registration.consumer) === registration) pending.add(registration);
      return;
    }
    if (!held.includes(value) || value.attempted.has(registration)) continue;
    value.attempted.add(registration);
    const taken = deliver(registration.consumer, value.seed);
    if (!sameLifetime(value.owner, value.generation)) return;
    // Removing a completed delivery is local retirement, even if its callback
    // suspended this token. Unattempted/failed entries remain in their order.
    if (taken) held = held.filter((entry) => entry !== value);
  }
}

function flushPending(): void {
  if (draining) return;
  draining = true;
  try {
    for (const broadcast of [...broadcasts]) deliverBroadcast(broadcast);
    while (pending.size > 0 && admitted(seamOwner, generation)) {
      const registration = pending.values().next().value;
      if (!registration) break;
      pending.delete(registration);
      if (current(registration)) drainHeld(registration);
    }
  } finally { draining = false; }
}

function confirmOwner(owner: WorkspaceOwnerSession): void {
  confirmedOwner = null;
  void awaitWorkspaceOwnerSession(owner).then((ok) => {
    if (!ok || !isWorkspaceOwnerSession(owner)) return;
    confirmedOwner = owner;
    flushPending();
  });
}
confirmOwner(seamOwner);
subscribeWorkspaceOwnerAdmission(({ session, state }) => {
  confirmedOwner = null;
  if (session !== seamOwner || session.subject === null || state === "retiring" || state === "failed") {
    resetProjectSeedSeam();
    seamOwner = session;
  }
  confirmOwner(session);
});

/** The intake's consumer contract. Held seeds reach the first current intake
 * once each, in confirmation order. A suspended same-token registration waits
 * for independent confirmation; a retired registration is never renewed. */
export function subscribeProjectSeed(consumer: ProjectSeedConsumer): () => void {
  const owner = workspaceOwnerSession();
  if (!sameLifetime(owner, generation)) return () => {};
  const registration: Registration = { owner, generation, consumer };
  consumers.set(consumer, registration);
  pending.add(registration);
  flushPending();
  return () => {
    pending.delete(registration);
    if (consumers.get(consumer) === registration) consumers.delete(consumer);
  };
}

/** The only hand-off. Counts reflect callbacks actually attempted during this
 * call. A same-token suspension holds remaining deliveries, never replays a
 * completed one. Failed-only seeds stay held for a later current intake. */
export function dispatchProjectSeed(seed: ProjectSeed): { delivered: number; failed: number } {
  const owner = workspaceOwnerSession();
  if (!admitted(owner, generation)) return { delivered: 0, failed: 0 };
  const broadcast: Broadcast = {
    value: { owner, generation, order: ++order, seed: copyOf(seed), attempted: new Set() },
    remaining: [...consumers.values()], delivered: 0, failed: 0,
  };
  broadcasts.add(broadcast);
  deliverBroadcast(broadcast);
  return { delivered: broadcast.delivered, failed: broadcast.failed };
}

/** Test seam and private retirement: invalidate captured in-flight work too. */
export function resetProjectSeedSeam(): void {
  generation++;
  consumers.clear();
  held = [];
  broadcasts.clear();
  pending.clear();
}
