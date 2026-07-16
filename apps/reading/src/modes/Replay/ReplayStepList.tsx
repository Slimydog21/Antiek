import { useMemo } from "react";

import { orderTrajectoryEvents } from "../../components/TrajectoryReplay";
import { useReplay } from "./ReplayContext";

const SIGNIFICANT_ACTIONS = new Set([
  "decompose.delivered",
  "evidence.retrieve.delivered",
  "parameter_extract.delivered",
  "connector.delivered",
  "synthesize.delivered",
  "investigation.completed",
  "investigation.failed",
]);

export default function ReplayStepList({ investigationId }: { investigationId?: string }) {
  const { events, loading, error } = useReplay();
  const steps = useMemo(
    () => orderTrajectoryEvents(events).filter((event) => SIGNIFICANT_ACTIONS.has(event.action_type)),
    [events],
  );

  return (
    <section className="replay-steps" aria-labelledby="replay-step-heading">
      <header className="replay-steps__header">
        <div>
          <p className="replay-eyebrow">Investigation map</p>
          <h2 id="replay-step-heading">Signal stops</h2>
        </div>
        <span className="replay-count" aria-label={`${steps.length} significant events`}>{steps.length}</span>
      </header>
      {!investigationId && <p className="replay-muted">No investigation in this route.</p>}
      {loading && <p className="replay-muted" role="status">Loading signal stops…</p>}
      {error && <p className="replay-error" role="alert">{error}</p>}
      {!loading && !error && investigationId && steps.length === 0 && (
        <p className="replay-muted">Significant events will appear here as the investigation unfolds.</p>
      )}
      {steps.length > 0 && <ol className="replay-steps__list">
        {steps.map((step, index) => (
          <li key={step.event_id || index}>
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent("antiek:replay:goto", { detail: { eventId: step.event_id } }))}
              title={step.action_type}
            >
              <span className="replay-step__index">{String(index + 1).padStart(2, "0")}</span>
              <span className="replay-step__copy">
                <strong>{prettifyAction(step.action_type)}</strong>
                <small>{step.emitted_at ?? "Time not recorded"}</small>
              </span>
              {step.phase !== null && step.phase !== undefined && <span className="replay-step__phase">P{step.phase}</span>}
            </button>
          </li>
        ))}
      </ol>}
    </section>
  );
}

function prettifyAction(action: string): string {
  return action.replace(/\.delivered$/, "").replace(/[._]/g, " ");
}
