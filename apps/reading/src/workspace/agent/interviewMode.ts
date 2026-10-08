/**
 * interviewMode.ts — the project-creation interview (SPR-07 M8; refs
 * patterns 18/20). The same pane with a HIDDEN first turn ("Begin the
 * interview."), one question at a time, options as cards from a fenced
 * `@@options` JSON block, and a confirm-only `project_seed` action that
 * hands {title, prompt, sources} to SPR-03's intake through ONE seam,
 * `subscribeProjectSeed` (repair C2; SEAMS.md §1) — never submitProject
 * (the intake owns the paid POST; handoff F6).
 *
 * INTERVIEW_SYSTEM_PROMPT duplicates SPR-03's INTERVIEW_PROMPT text until
 * #3749 lands a shared export (F6): one de-dup edit then.
 */
import type { AiAction } from "../../components/ai/aiActions";

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

const consumers = new Set<ProjectSeedConsumer>();
/** A seed confirmed while no intake was mounted: held (latest only) for the
 *  first consumer to subscribe, delivered to it exactly once. */
let pending: ProjectSeed | null = null;

const copyOf = (s: ProjectSeed): ProjectSeed => ({ title: s.title, prompt: s.prompt, ...(s.sources ? { sources: [...s.sources] } : {}) });

/**
 * The intake's ONE consumer path (SPR-03's useProjectIntake calls this in
 * an effect: `useEffect(() => subscribeProjectSeed(applySeed), [applySeed])`).
 * Every consumer receives each dispatched seed exactly once, as its own
 * value copy; a seed confirmed before any consumer existed is handed to
 * the first subscriber, once. Returns the unsubscribe.
 */
export function subscribeProjectSeed(consumer: ProjectSeedConsumer): () => void {
  consumers.add(consumer);
  if (pending !== null) {
    const held = pending;
    pending = null;
    consumer(copyOf(held));
  }
  return () => { consumers.delete(consumer); };
}

/** The ONLY hand-off. `delivered` is how many consumers received it; 0
 *  means no intake is mounted (the seed is held for the first one). */
export function dispatchProjectSeed(seed: ProjectSeed): { delivered: number } {
  const snapshot = copyOf(seed);
  if (consumers.size === 0) {
    pending = snapshot;
    return { delivered: 0 };
  }
  let delivered = 0;
  for (const c of [...consumers]) {
    c(copyOf(snapshot));
    delivered += 1;
  }
  return { delivered };
}

/** Test seam: forget every consumer and any held seed. */
export function resetProjectSeedSeam(): void {
  consumers.clear();
  pending = null;
}
