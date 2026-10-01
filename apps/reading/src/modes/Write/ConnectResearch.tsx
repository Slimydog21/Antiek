import { useEffect, useState } from "react";

import ModelUsagePicker from "../../components/ai/ModelUsagePicker";
import { useOwnerModelChoice } from "../../hooks/useOwnerModelChoice";
import {
  listInvestigations,
  type InvestigationSummary,
  type StartInvestigationRequest,
} from "../../lib/api";

export type WritingStartChoice =
  | { kind: "empty" }
  | { kind: "research"; investigationId: string; label: string }
  | { kind: "new-research"; request: StartInvestigationRequest };

export interface ConnectResearchProps {
  /** The host admits and sequences all writes for this explicit choice. */
  onConnect: (choice: WritingStartChoice) => void;
  pieceTitle: string;
  disabled?: boolean;
  /** From AutoNotebook `/write?investigation=` — same connectExisting path. */
  preferredInvestigationId?: string | null;
  /** A successful research launch is reused if creating its piece failed. */
  startedResearch?: Extract<WritingStartChoice, { kind: "research" }> | null;
}

export default function ConnectResearch({
  onConnect,
  pieceTitle,
  disabled,
  preferredInvestigationId,
  startedResearch,
}: ConnectResearchProps) {
  const [projects, setProjects] = useState<InvestigationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const model = useOwnerModelChoice("connect");

  useEffect(() => {
    let cancelled = false;
    listInvestigations({ limit: 50 })
      .then((r) => {
        if (!cancelled) setProjects(r.investigations);
      })
      .catch(() => {
        // A failed list is shown plainly — the writer can still start fresh.
        if (!cancelled) setError("Couldn't load your research projects.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function connectExisting(p: InvestigationSummary) {
    if (disabled) return;
    onConnect({
      kind: "research",
      investigationId: p.investigation_id,
      label: p.question?.trim() || "a research project",
    });
  }

  function startResearch() {
    if (disabled) return;
    if (startedResearch) {
      onConnect(startedResearch);
      return;
    }
    onConnect({
      kind: "new-research",
      request: {
        question: pieceTitle.trim() || "Untitled piece",
        context: "Research requested by the writer before starting a piece.",
        ...model.launchFields(pieceTitle.trim() || "Untitled piece"),
      },
    });
  }

  return (
    <div data-testid="connect-research" className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-ink dark:text-bright">
          Research is optional
        </h2>
        <p className="mt-0.5 text-xs text-ink-mute dark:text-moonlight">
          Start with a blank piece, or bring an outline from existing research.
        </p>
      </div>

      {error && (
        <p className="text-xs text-emperor" role="alert">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={() => { if (!disabled) onConnect({ kind: "empty" }); }}
        disabled={disabled}
        className="w-full rounded border border-rule px-3 py-2 text-left text-sm hover:border-sun-deep disabled:opacity-60 dark:border-charcoal-1"
      >
        <span className="font-medium text-ink dark:text-bright">Start empty</span>
        <span className="block text-xs text-ink-mute dark:text-moonlight">
          Create a blank piece. No research starts.
        </span>
      </button>

      {!startedResearch && <fieldset disabled={disabled} className="flex items-center gap-2">
        <legend className="text-xxs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Model for new research
        </legend>
        <ModelUsagePicker
          models={model.models}
          value={model.selectedRowId}
          onChange={model.select}
          includeDefault
          defaultLabel="Default (house route)"
          triggerLabel={model.triggerLabel}
          triggerAriaLabel="Model for new research"
          size="sm"
        />
        {model.state === "error" && (
          <span className="text-xxs font-mono text-emperor" aria-live="polite">
            Your models couldn't load. Default is still available.
          </span>
        )}
      </fieldset>}

      <button
        type="button"
        onClick={startResearch}
        disabled={disabled}
        className="w-full rounded border border-dashed border-rule px-3 py-2 text-left text-sm hover:border-sun-deep disabled:opacity-60 dark:border-charcoal-1"
      >
        <span className="font-medium text-ink dark:text-bright">
          {startedResearch ? "Create piece with started research" : "Start research first"}
        </span>
        <span className="block text-xs text-ink-mute dark:text-moonlight">
          {startedResearch
            ? "Your research has started. Use it without starting another run."
            : "This starts research with the selected model and can incur charges."}
        </span>
      </button>

      {loading ? (
        <p className="text-xs italic text-ink-mute dark:text-moonlight">
          Loading your research projects…
        </p>
      ) : projects.length > 0 ? (
        <>
          {preferredInvestigationId ? (
            <p
              className="text-xs text-ink-soft"
              data-testid="connect-research-preferred"
            >
              From your notebook. Choose its research below to bring the
              available outline into this piece.
            </p>
          ) : null}
          <ul className="max-h-56 space-y-1 overflow-y-auto">
          {([...projects].sort((a, b) => {
              const pref = preferredInvestigationId ?? "";
              if (!pref) return 0;
              if (a.investigation_id === pref) return -1;
              if (b.investigation_id === pref) return 1;
              return 0;
            })).map((p) => (
            <li key={p.investigation_id}>
              <button
                type="button"
                onClick={() => void connectExisting(p)}
                disabled={disabled}
                className={`w-full rounded border px-3 py-2 text-left hover:border-sun-deep disabled:opacity-60 dark:bg-charcoal-2 ${preferredInvestigationId === p.investigation_id ? "border-sun-deep bg-sun/10" : "border-rule bg-ice-0 dark:border-charcoal-1"}`}
              >
                <span className="block truncate font-serif text-sm text-ink dark:text-bright">
                  {p.question?.trim() || "(untitled research)"}
                </span>
                <span className="text-xxs uppercase tracking-wide text-ink-mute dark:text-moonlight">
                  {p.status}
                  {p.spawned_by_daemon ? " · found by the loop" : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
        </>

      ) : (
        <p className="text-xs italic text-ink-mute dark:text-moonlight">
          No research projects yet. You can still start empty.
        </p>
      )}
    </div>
  );
}
