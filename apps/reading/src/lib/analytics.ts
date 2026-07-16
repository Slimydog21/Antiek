import type { Properties } from "posthog-js";

import { posthog, posthogEnabled } from "./posthogClient";

/** Sentinel for events that carry no properties. */
type EmptyProps = Record<string, never>;

/**
 * Canonical Antiek analytics taxonomy — the single typed home for every
 * product event.
 *
 * Call sites use `track(event, props)` instead of `posthog.capture("string",
 * {...})` so that:
 *   - event names cannot drift or be misspelled (an off-taxonomy name is a
 *     compile error),
 *   - each event's property shape is type-checked at the call site,
 *   - telemetry is a no-op without a project token (CI / Storybook / local
 *     without keys),
 *   - every event still passes through the §9.0 content firewall in
 *     posthogClient (before_send).
 *
 * Naming convention: `<object>_<action>`, snake_case, past-tense verbs for
 * completed actions. This file — together with the identify/reset effect in
 * auth.tsx (person model) — is the ONLY place posthog's capture surface is
 * called.
 */
export type AnalyticsEvents = {
  // Research — investigation entry + deep-research cascade funnel
  investigation_started: {
    question_length: number;
    has_parent: boolean;
    has_spawn_context: boolean;
  };
  deep_research_cascade_created: { problem_length: number };
  deep_research_plan_approved: EmptyProps;
  deep_research_cascade_launched: { session_id: string };
  deep_research_canvas_opened: {
    investigation_id: string;
    source: "werner_broadcast" | "terminal_card";
    outcome: "done";
  };
  brainstorm_question_launched: EmptyProps;

  // Read
  reading_research_spun: {
    document_id: string;
    page_index: number;
    has_passage: boolean;
  };

  // Write — notebook
  notebook_block_appended: { block_type: string };
  notebook_block_deleted: EmptyProps;

  // Speak
  speak_project_created: EmptyProps;
  speak_draft_assembled: { project_id: string; will_be_public: boolean };
  speak_share_link_created: { project_id: string };
  speak_invite_sent: { project_id: string };
  voice_note_ingested: EmptyProps;

  // Account + commerce funnel
  login_requested: EmptyProps;
  login_link_sent: EmptyProps;
  passkey_login_started: EmptyProps;
  passkey_login_succeeded: EmptyProps;
  passkey_registered: EmptyProps;
  pricing_viewed: EmptyProps;
  billing_viewed: EmptyProps;
};

export type AnalyticsEvent = keyof AnalyticsEvents;

/**
 * Emit a typed product event. Properties are required for events that define
 * them and forbidden for those that don't — the variadic tuple enforces both
 * at the call site. No-op when analytics is disabled.
 */
export function track<E extends AnalyticsEvent>(
  event: E,
  ...rest: AnalyticsEvents[E] extends EmptyProps ? [] : [AnalyticsEvents[E]]
): void {
  if (!posthogEnabled) return;
  posthog.capture(event, rest[0] as Properties | undefined);
}

/**
 * Report a caught exception to PostHog error tracking. Same
 * no-op-without-token discipline as track(). Use for genuinely unexpected
 * failures, not for expected control flow.
 */
export function trackException(error: unknown): void {
  if (!posthogEnabled) return;
  posthog.captureException(
    error instanceof Error ? error : new Error(String(error)),
  );
}
