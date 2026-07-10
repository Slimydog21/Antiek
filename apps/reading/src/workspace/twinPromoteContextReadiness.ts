/**
 * Residual (aum): pure twin promote→context CTA readiness.
 *
 * Recursive note-taker promote path: gate CTA by hydrated substrate + kind
 * filter so empty / wrong-leg promote is disabled honestly.
 *
 * twins not yet hydrated (unknown) → allow CTA (server may hold notes).
 * After hydrate: all → non-empty; insight → has insights; question → has questions.
 *
 * Parity twinSubstrateReadiness (arq) · arx inline gate · never invents notes.
 */

import type { TwinSubstrateReadiness } from "./twinSubstrateReadiness";

export type TwinPromoteKindFilter = "all" | "insight" | "question";

export type TwinPromoteContextReadiness = {
  /** twins payload received (null = unknown / not hydrated). */
  twins_hydrated: boolean;
  promote_kinds: TwinPromoteKindFilter;
  has_insights: boolean;
  has_questions: boolean;
  empty: boolean;
  /** True when Promote to context CTA should be enabled (ignoring busy). */
  promote_ready: boolean;
  summary: string;
  disabled_title: string;
};

function normalizePromoteKinds(
  kinds: string | null | undefined,
): TwinPromoteKindFilter {
  const k = String(kinds || "")
    .trim()
    .toLowerCase();
  if (k === "insight") return "insight";
  if (k === "question") return "question";
  return "all";
}

/**
 * Compute promote→context CTA readiness.
 * opts.twins_hydrated false → allow (unknown substrate).
 * opts.substrate from twinSubstrateReadiness after hydrate.
 */
export function twinPromoteContextReadiness(opts: {
  /** False when twins === null (not yet loaded). */
  twins_hydrated: boolean;
  promote_kinds?: string | null;
  substrate?: Pick<
    TwinSubstrateReadiness,
    "empty" | "has_insights" | "has_questions"
  > | null;
}): TwinPromoteContextReadiness {
  const promote_kinds = normalizePromoteKinds(opts.promote_kinds);
  const empty = Boolean(opts.substrate?.empty);
  const has_insights = Boolean(opts.substrate?.has_insights);
  const has_questions = Boolean(opts.substrate?.has_questions);
  const twins_hydrated = Boolean(opts.twins_hydrated);

  let promote_ready: boolean;
  if (!twins_hydrated) {
    // Unknown substrate — allow CTA; server may hold notes offline.
    promote_ready = true;
  } else if (promote_kinds === "all") {
    promote_ready = !empty;
  } else if (promote_kinds === "insight") {
    promote_ready = has_insights;
  } else {
    promote_ready = has_questions;
  }

  let summary: string;
  let disabled_title: string;
  if (!twins_hydrated) {
    summary = "substrate unknown · promote allowed (server may hold notes)";
    disabled_title = "Promote twins into research context";
  } else if (promote_ready) {
    if (promote_kinds === "all") {
      summary = "substrate non-empty · promote all kinds ready";
      disabled_title = "Promote twins into research context";
    } else if (promote_kinds === "insight") {
      summary = "insights present · promote insight ready";
      disabled_title = "Promote insight twins into research context";
    } else {
      summary = "questions present · promote question ready";
      disabled_title = "Promote question twins into research context";
    }
  } else if (empty) {
    summary = "empty twin substrate · promote disabled";
    disabled_title =
      "Empty twin substrate · seed or record notes before promote";
  } else if (promote_kinds === "insight") {
    summary = "no insights leg · promote insight disabled";
    disabled_title =
      "No insight twins to promote · record insights or switch kind";
  } else {
    summary = "no questions leg · promote question disabled";
    disabled_title =
      "No question twins to promote · record questions or switch kind";
  }

  return {
    twins_hydrated,
    promote_kinds,
    has_insights,
    has_questions,
    empty,
    promote_ready,
    summary,
    disabled_title,
  };
}
