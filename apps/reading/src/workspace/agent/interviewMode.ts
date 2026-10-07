/**
 * interviewMode.ts — the project-creation interview (SPR-07 M8; refs
 * patterns 18/20). The same pane with a HIDDEN first turn ("Begin the
 * interview."), one question at a time, options as cards from a fenced
 * `@@options` JSON block, and a confirm-only `project_seed` action that
 * hands {title, prompt, sources} to SPR-03's intake by a window event —
 * never submitProject (the intake owns the paid POST; handoff F6).
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

export const PROJECT_INTAKE_SEED_EVENT = "antiek:project-intake:seed";

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

/** The ONLY hand-off: one CustomEvent the intake subscribes to. */
export function dispatchProjectSeed(seed: ProjectSeed): void {
  window.dispatchEvent(new CustomEvent(PROJECT_INTAKE_SEED_EVENT, { detail: seed }));
}
