import LemonButton from "../components/lemon/LemonButton";
import {
  FAILURE_HEADLINES,
  FAILURE_RETRYABLE_DEFAULT,
  type FailureCode,
} from "../lib/api";

import { emitWernerExperience } from "../werner/reactionBus";
/**
 * AIActionFailure — the one honest-failure surface every AI action shares.
 *
 * Generalized from StartResearch's inline `investigation.failed` handling
 * (PR #10): when an AI action aborts — start a research, draft a piece,
 * assemble a biography, talk to a book — the user sees the same sentence
 * everywhere: what happened, why if the engine said why, and a "Try again"
 * that re-runs the action. It is presentational: it renders `role="alert"`
 * and calls `onRetry`; it NEVER navigates. The caller owns the route, so a
 * failure can never strand the user on a dead page.
 *
 * Honest about the credential-gated reality, and honest in two branches:
 *  - REASON ABSENT — the common production case is "an id came back, then
 *    the run aborted with nothing to say." That plausibly means no model
 *    provider is configured, so we say exactly that ("the engine returned
 *    no result … the model provider isn't configured") — not a spinning
 *    `…` and not a generic "something went wrong."
 *  - REASON PRESENT — the engine told us what went wrong, so we lead
 *    generically ("the engine reported a problem") and show the real reason
 *    framed below. We do NOT assert a specific cause (no-provider) when the
 *    engine's own reason explains it — that would put a likely-wrong guess
 *    directly above the contradicting truth.
 */
type Props = {
  /** What was being attempted, in the user's words ("The research didn't complete"). */
  title: string;
  /**
   * The engine's diagnostic reason, when the failure event carried one.
   * Framed (labelled "Engine:"), not shown raw-as-prose, because it's a
   * diagnostic. Omit / null for the common no-provider case.
   */
  reason?: string | null;
  /** Re-run the action. The caller re-runs in place; this never navigates. */
  onRetry: () => void;
  /** Label for the retry control. Defaults to "Try again". */
  retryLabel?: string;
  /**
   * Machine-readable failure code from docs/decisions/drw-plan-failure-contract.md.
   * When set, renders the canonical headline for that code (DRW and future callers).
   * When omitted, legacy reason / no-reason branches are unchanged.
   */
  code?: FailureCode;
  /** When `code` is set, controls retry affordance (defaults from contract). */
  retryable?: boolean;
  className?: string;
};

export default function AIActionFailure({
  title,
  reason,
  onRetry,
  retryLabel = "Try again",
  code,
  retryable,
  className,
}: Props) {
  const showRetry =
    code === undefined
      ? true
      : (retryable ?? FAILURE_RETRYABLE_DEFAULT[code]);

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={
        className
          ? `text-xs font-mono text-emperor flex flex-col gap-2 ${className}`
          : "text-xs font-mono text-emperor flex flex-col gap-2"
      }
    >
      <p className="leading-relaxed">
        {code ? (
          <>
            {title} — {FAILURE_HEADLINES[code]}
            {code === "unknown" && reason ? (
              <span className="block mt-1 text-ink-mute dark:text-moonlight not-italic">
                Engine: {reason}
              </span>
            ) : null}
          </>
        ) : reason ? (
          <>
            {title} — the engine reported a problem. Try again.
            <span className="block mt-1 text-ink-mute dark:text-moonlight not-italic">
              Engine: {reason}
            </span>
          </>
        ) : (
          <>
            {title} — the engine returned no result. This usually means the
            model provider isn&rsquo;t configured. Try again, or check
            provider keys.
          </>
        )}
      </p>
      {showRetry ? (
        <div>
          <LemonButton variant="secondary" size="sm" onClick={() => { emitWernerExperience("highlight"); onRetry(); }}>
            {retryLabel}
          </LemonButton>
        </div>
      ) : null}
    </div>
  );
}
