/**
 * ResearchRouteInstrument — extracted route-choice and budget-readout
 * component from StartResearch.
 *
 * SPR-01 visual-proof: the route choice reads like a field instrument,
 * not a settings form. The selected lens receives a left-edge sun
 * registration mark; readiness is an instrument status, not a badge.
 * Budget sits below as calibration evidence.
 *
 * Component boundary: owns presentation + roving-radio keyboard
 * behavior. Does NOT own question, fetching, launch, model/provider
 * IDs, route proof construction, tier fallback, or synthesis.
 * StartResearch remains the state and launch coordinator.
 */

import type { ResearchRouteCandidate, ResearchRoutePreview } from "../../lib/api";

export interface ResearchRouteInstrumentProps {
  preview: ResearchRoutePreview;
  selectedChoiceId: string | null;
  busy: boolean;
  onSelect: (candidate: ResearchRouteCandidate) => void;
}

export default function ResearchRouteInstrument({
  preview,
  selectedChoiceId,
  busy,
  onSelect,
}: ResearchRouteInstrumentProps) {
  const hasReadyRoute = preview.candidates.some((c) => c.ready);
  const hasSelectedReadyRoute = preview.candidates.some(
    (candidate) =>
      candidate.choice_id === selectedChoiceId && candidate.ready,
  );
  const firstReadyChoiceId = preview.candidates.find(
    (candidate) => candidate.ready,
  )?.choice_id;

  function handleKeyDown(event: React.KeyboardEvent, candidateIndex: number) {
    if (
      !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(
        event.key,
      )
    )
      return;
    event.preventDefault();
    if (event.key === "Home" || event.key === "End") {
      const ordered =
        event.key === "Home"
          ? preview.candidates
          : [...preview.candidates].reverse();
      const boundary = ordered.find((row) => row.ready);
      if (boundary) {
        onSelect(boundary);
        document.getElementById(`research-route-${boundary.choice_id}`)?.focus();
      }
      return;
    }
    const direction =
      event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
    for (let step = 1; step <= preview.candidates.length; step += 1) {
      const next =
        preview.candidates[
          (candidateIndex + direction * step + preview.candidates.length) %
            preview.candidates.length
        ];
      if (!next.ready) continue;
      onSelect(next);
      document.getElementById(`research-route-${next.choice_id}`)?.focus();
      break;
    }
  }

  const { budget } = preview;

  return (
    <section aria-labelledby="research-route-label" className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2
          id="research-route-label"
          className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight"
        >
          Research route
        </h2>
        <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
          Synthesis independently pinned
        </span>
      </div>
      <div
        className="grid grid-cols-1 sm:grid-cols-2 gap-2"
        role="radiogroup"
        aria-label="Research route"
      >
        {preview.candidates.map((candidate, candidateIndex) => {
          // A remembered but unavailable choice is not an authorized route.
          const active =
            selectedChoiceId === candidate.choice_id && candidate.ready;
          const keyboardEntry =
            active ||
            (!hasSelectedReadyRoute &&
              candidate.choice_id === firstReadyChoiceId);
          return (
            <button
              key={candidate.choice_id}
              id={`research-route-${candidate.choice_id}`}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={keyboardEntry ? 0 : -1}
              aria-describedby={`${candidate.choice_id}-detail`}
              disabled={busy || !candidate.ready}
              onClick={() => onSelect(candidate)}
              onKeyDown={(event) => handleKeyDown(event, candidateIndex)}
              className={
                "rounded-hog border-2 p-3 text-left " +
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 " +
                "focus-visible:outline-ink dark:focus-visible:outline-bright " +
                "motion-reduce:transition-none disabled:opacity-60 " +
                (active
                  ? "border-ink border-l-[6px] border-l-sun bg-sun/20 shadow-z1 dark:shadow-z1-night"
                  : "border-rule bg-ice-0 dark:bg-charcoal-2")
              }
            >
              <span className="block font-serif text-sm text-ink dark:text-bright">
                {candidate.display_name}
              </span>
              <span className="block font-mono text-[11px] text-ink-mute dark:text-moonlight">
                {candidate.model_policy_label}
              </span>
              <span
                className={
                  "block font-mono text-[10px] mt-1 " +
                  (candidate.ready ? "text-aurora" : "text-emperor")
                }
              >
                {candidate.readiness_label}
              </span>
              <span id={`${candidate.choice_id}-detail`} className="sr-only">
                {candidate.rationale}
              </span>
            </button>
          );
        })}
      </div>
      <details className="text-[11px] text-ink-mute dark:text-moonlight">
        <summary className="cursor-pointer font-mono">
          Route and projection details
        </summary>
        <ul className="mt-1 space-y-1">
          {preview.candidates.map((candidate) => (
            <li key={`${candidate.choice_id}-rationale`}>
              <strong>{candidate.display_name}:</strong> {candidate.rationale}
            </li>
          ))}
        </ul>
        <p className="mt-1">{budget.projection_note}</p>
      </details>
      <div
        aria-label="Daily research budget advisory"
        className="rounded-hog border border-rule dark:border-charcoal-1 px-3 py-2"
      >
        <div className="flex flex-wrap justify-between gap-2 text-[11px] font-mono text-ink-mute dark:text-moonlight">
          <span>Daily ledger · advisory only</span>
          <span>
            {budget.spent_status === "known" && budget.spent_usd != null
              ? `$${budget.spent_usd.toFixed(2)} ${
                  budget.daily_cap_usd == null ? "daemon-tracked" : "spent"
                }`
              : "spend unknown"}
            {budget.daily_cap_usd == null
              ? " · no operator ceiling"
              : ` · $${budget.daily_cap_usd.toFixed(2)} operator ceiling`}
            {" · projection unavailable"}
          </span>
        </div>
        {budget.spent_status === "known" &&
          budget.cap_source != null &&
          budget.spent_usd != null &&
          budget.daily_cap_usd != null &&
          budget.daily_cap_usd > 0 && (
            <div
              data-testid="research-budget-meter"
              className="mt-2 h-1.5 overflow-hidden rounded-full bg-rule/50"
              aria-hidden="true"
            >
              <div
                className="h-full bg-sun-deep motion-reduce:transition-none"
                style={{
                  width: `${Math.min(
                    100,
                    Math.max(
                      0,
                      (budget.spent_usd / budget.daily_cap_usd) * 100,
                    ),
                  )}%`,
                }}
              />
            </div>
          )}
        {budget.notes.map((note) => (
          <p
            key={note}
            className="mt-1 text-[10px] font-mono text-ink-mute dark:text-moonlight"
          >
            {note}
          </p>
        ))}
      </div>
      {!hasReadyRoute && (
        <p role="status" className="text-[11px] font-mono text-emperor">
          Preferred drivers are unavailable. You can still launch through
          Antiek’s configured recovery chain below.
        </p>
      )}
    </section>
  );
}
