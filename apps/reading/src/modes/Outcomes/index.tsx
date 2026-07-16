import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import verdictChamberEnvironment from "../../brand/werner/outcomes/outcomes_verdict_chamber_environment_v1.webp";
import { LemonButton, LemonTextarea } from "../../components/lemon";
import { apiFetch } from "../../lib/api";
import { PanelHost } from "../../workspace/PanelHost";
import "./outcomes-verdict-chamber.css";

export interface OutcomeRow {
  outcome_id: string;
  observer: string;
  observed_at: string;
  thesis_outcomes: { kind: string; note: string }[];
  falsification_outcomes: { kind: string; note: string }[];
  execution_risk_outcomes: { kind: string; note: string }[];
  notes: string | null;
}

export type OutcomeKind = "validated" | "falsified" | "indeterminate";

export interface OutcomeDraft {
  synthesis_id: string;
  observer: "__operator__";
  thesis_outcomes: { kind: "validated"; note: string }[];
  falsification_outcomes: { kind: "falsified"; note: string }[];
  execution_risk_outcomes: { kind: "indeterminate"; note: string }[];
  notes: string | null;
}

export interface OutcomesProps {
  synthesisIdOverride?: string | null;
  loadOutcomes?: (synthesisId: string) => Promise<OutcomeRow[]>;
  recordOutcome?: (draft: OutcomeDraft) => Promise<void>;
  executionEnabled?: boolean;
}

async function loadOutcomesFromApi(synthesisId: string): Promise<OutcomeRow[]> {
  const resp = await apiFetch(`/outcomes/${encodeURIComponent(synthesisId)}`);
  if (!resp.ok) throw new Error(`GET /outcomes failed: HTTP ${resp.status}`);
  const data = (await resp.json()) as { outcomes?: OutcomeRow[] };
  return data.outcomes ?? [];
}

async function recordOutcomeToApi(draft: OutcomeDraft): Promise<void> {
  const resp = await apiFetch("/outcomes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!resp.ok) throw new Error(`POST /outcomes failed: HTTP ${resp.status}`);
}

const CHOICES: Array<{
  kind: OutcomeKind;
  label: string;
  description: string;
}> = [
  {
    kind: "validated",
    label: "Validated",
    description: "The synthesis survived the evidence you reviewed.",
  },
  {
    kind: "falsified",
    label: "Falsified",
    description: "The evidence overturned a load-bearing claim.",
  },
  {
    kind: "indeterminate",
    label: "Indeterminate",
    description: "The available evidence cannot settle the claim yet.",
  },
];

export default function Outcomes({
  synthesisIdOverride,
  loadOutcomes = loadOutcomesFromApi,
  recordOutcome = recordOutcomeToApi,
  executionEnabled = true,
}: OutcomesProps = {}) {
  const { synthesisId: routeSynthesisId } = useParams<{
    synthesisId: string;
  }>();
  const synthesisId =
    synthesisIdOverride === undefined
      ? routeSynthesisId
      : (synthesisIdOverride ?? undefined);
  const [outcomes, setOutcomes] = useState<OutcomeRow[]>([]);
  const [loading, setLoading] = useState(Boolean(synthesisId));
  const [error, setError] = useState<string | null>(null);
  const [draftNote, setDraftNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const loadSequence = useRef(0);
  const activeSynthesis = useRef(synthesisId);
  activeSynthesis.current = synthesisId;

  const reload = useCallback(async () => {
    const sequence = ++loadSequence.current;
    if (!synthesisId) {
      setLoading(false);
      setOutcomes([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const loaded = await loadOutcomes(synthesisId);
      if (
        sequence !== loadSequence.current ||
        activeSynthesis.current !== synthesisId
      )
        return;
      setOutcomes(loaded);
    } catch (caught: unknown) {
      if (
        sequence !== loadSequence.current ||
        activeSynthesis.current !== synthesisId
      )
        return;
      setOutcomes([]);
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (
        sequence === loadSequence.current &&
        activeSynthesis.current === synthesisId
      )
        setLoading(false);
    }
  }, [loadOutcomes, synthesisId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function submit(kind: OutcomeKind) {
    if (!executionEnabled || !synthesisId || submitting) return;
    const note = draftNote.trim() || `Graded ${kind}.`;
    const draft: OutcomeDraft = {
      synthesis_id: synthesisId,
      observer: "__operator__",
      thesis_outcomes:
        kind === "validated" ? [{ kind: "validated", note }] : [],
      falsification_outcomes:
        kind === "falsified" ? [{ kind: "falsified", note }] : [],
      execution_risk_outcomes:
        kind === "indeterminate" ? [{ kind: "indeterminate", note }] : [],
      notes: draftNote || null,
    };
    setSubmitting(true);
    setError(null);
    try {
      await recordOutcome(draft);
      if (activeSynthesis.current === synthesisId) {
        setDraftNote("");
        await reload();
      }
    } catch (caught: unknown) {
      if (activeSynthesis.current === synthesisId)
        setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  }

  const counts = useMemo(
    () => ({
      validated: outcomes.reduce(
        (sum, row) => sum + row.thesis_outcomes.length,
        0,
      ),
      falsified: outcomes.reduce(
        (sum, row) => sum + row.falsification_outcomes.length,
        0,
      ),
      indeterminate: outcomes.reduce(
        (sum, row) => sum + row.execution_risk_outcomes.length,
        0,
      ),
    }),
    [outcomes],
  );

  return (
    <PanelHost>
      <main className="outcomes-verdict-chamber">
        <img
          src={verdictChamberEnvironment}
          alt=""
          aria-hidden="true"
          draggable={false}
          className="outcomes-verdict-chamber__environment"
        />
        <span className="outcomes-verdict-chamber__veil" aria-hidden="true" />

        <div className="outcomes-verdict-chamber__content">
          <header className="outcomes-verdict-chamber__hero">
            <p className="outcomes-verdict-chamber__eyebrow">
              Operator observation
            </p>
            <h1>Verdict chamber</h1>
            <p className="outcomes-verdict-chamber__lede">
              Record what the synthesis earned from the evidence. This
              observation becomes reviewable feedback; it does not rewrite the
              synthesis or make an automatic decision.
            </p>
            <div className="outcomes-verdict-chamber__identity">
              <span>Synthesis</span>
              <code>{synthesisId ?? "No synthesis selected"}</code>
              {synthesisId && (
                <Link to={`/backtest/${encodeURIComponent(synthesisId)}`}>
                  Open backtest report
                </Link>
              )}
            </div>
          </header>

          {error && (
            <p className="outcomes-verdict-chamber__error" role="alert">
              {error}
            </p>
          )}
          {!synthesisId && (
            <p className="outcomes-verdict-chamber__error" role="alert">
              No synthesis is selected. Open this chamber from a synthesis
              outcome record.
            </p>
          )}

          <section
            className="outcomes-verdict-chamber__panel"
            aria-labelledby="outcomes-grade-heading"
          >
            <div className="outcomes-verdict-chamber__section-heading">
              <div>
                <p className="outcomes-verdict-chamber__eyebrow">
                  Pending observation
                </p>
                <h2 id="outcomes-grade-heading">
                  What did the evidence establish?
                </h2>
              </div>
              <span className="outcomes-verdict-chamber__status">
                One operator judgment
              </span>
            </div>
            <LemonTextarea
              value={draftNote}
              onChange={(event) => setDraftNote(event.target.value)}
              placeholder="Brief rationale for future review"
              aria-label="Outcome rationale"
              minRows={2}
              maxRows={5}
              disabled={submitting || !executionEnabled}
            />
            <div className="outcomes-verdict-chamber__choices">
              {CHOICES.map((choice) => (
                <article
                  key={choice.kind}
                  className="outcomes-verdict-chamber__choice"
                >
                  <h3>{choice.label}</h3>
                  <p>{choice.description}</p>
                  <LemonButton
                    type="button"
                    variant="secondary"
                    className="outcomes-verdict-chamber__choice-action"
                    disabled={
                      !executionEnabled || !synthesisId || submitting || loading
                    }
                    onClick={() => void submit(choice.kind)}
                  >
                    {submitting
                      ? "Recording…"
                      : `Record ${choice.label.toLowerCase()}`}
                  </LemonButton>
                </article>
              ))}
            </div>
          </section>

          <section
            className="outcomes-verdict-chamber__counts"
            aria-label="Recorded outcome counts"
          >
            {CHOICES.map((choice) => (
              <div
                key={choice.kind}
                className="outcomes-verdict-chamber__count"
              >
                <strong>{counts[choice.kind]}</strong>
                <span>{choice.label}</span>
              </div>
            ))}
          </section>

          <section
            className="outcomes-verdict-chamber__panel"
            aria-labelledby="outcomes-history-heading"
          >
            <div className="outcomes-verdict-chamber__section-heading">
              <div>
                <p className="outcomes-verdict-chamber__eyebrow">Audit trail</p>
                <h2 id="outcomes-history-heading">Recorded observations</h2>
              </div>
            </div>
            {loading ? (
              <p className="outcomes-verdict-chamber__quiet" role="status">
                Loading recorded observations…
              </p>
            ) : outcomes.length === 0 ? (
              <p className="outcomes-verdict-chamber__quiet">
                No outcomes have been recorded for this synthesis.
              </p>
            ) : (
              <ol className="outcomes-verdict-chamber__history">
                {outcomes.map((row) => (
                  <li key={row.outcome_id}>
                    <p className="outcomes-verdict-chamber__meta">
                      {row.observed_at} · {row.observer}
                    </p>
                    {row.thesis_outcomes.map((item, index) => (
                      <p
                        key={`validated-${index}`}
                        data-recorded-kind="validated"
                      >
                        <strong>Validated</strong> — {item.note}
                      </p>
                    ))}
                    {row.falsification_outcomes.map((item, index) => (
                      <p
                        key={`falsified-${index}`}
                        data-recorded-kind="falsified"
                      >
                        <strong>Falsified</strong> — {item.note}
                      </p>
                    ))}
                    {row.execution_risk_outcomes.map((item, index) => (
                      <p
                        key={`indeterminate-${index}`}
                        data-recorded-kind="indeterminate"
                      >
                        <strong>Indeterminate</strong> — {item.note}
                      </p>
                    ))}
                    {row.notes && (
                      <p className="outcomes-verdict-chamber__note">
                        Rationale: {row.notes}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </main>
    </PanelHost>
  );
}
