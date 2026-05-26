import LemonButton from "../components/lemon/LemonButton";

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
 * Honest about the credential-gated reality: in production the common
 * failure is "an id came back, then the run aborted because no model
 * provider is configured." A reason-less failure therefore says, plainly,
 * that the engine returned no result and the provider may be unconfigured —
 * not a spinning `…` and not a generic "something went wrong."
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
  className?: string;
};

export default function AIActionFailure({
  title,
  reason,
  onRetry,
  retryLabel = "Try again",
  className,
}: Props) {
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
        {title} — the engine returned no result. This usually means the model
        provider isn&rsquo;t configured. Try again, or check provider keys.
        {reason ? (
          <span className="block mt-1 text-ink-mute dark:text-moonlight not-italic">
            Engine: {reason}
          </span>
        ) : null}
      </p>
      <div>
        <LemonButton variant="secondary" size="sm" onClick={onRetry}>
          {retryLabel}
        </LemonButton>
      </div>
    </div>
  );
}
