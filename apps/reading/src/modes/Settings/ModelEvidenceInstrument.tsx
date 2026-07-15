import type {
  ModelDecisionCandidate,
  ModelDecisionResponse,
  ModelDecisionTask,
} from "../../api/settings";

/**
 * ModelEvidenceInstrument — sunline evidence rail.
 *
 * Extracted from the Settings decision-tree panel. Renders advisory model
 * evidence with truthful null states: absent measurement renders "Not measured",
 * never an affinity number. A measured pick requires at least two operationally
 * eligible measured candidates from the same report snapshot.
 */

const DECISION_TASKS: Array<{ value: ModelDecisionTask; label: string }> = [
  { value: "deep_research", label: "Deep research" },
  { value: "research_synthesis", label: "Research synthesis" },
  { value: "reading", label: "Reading" },
  { value: "twin_note", label: "Twin note" },
  { value: "writing", label: "Writing" },
  { value: "multimedia", label: "Multimedia" },
  { value: "general", label: "General" },
];

export interface ModelEvidenceInstrumentProps {
  decision: ModelDecisionResponse | null;
  loading: boolean;
  error: string | null;
  onCompare: () => void;
  task: ModelDecisionTask;
  onTaskChange: (task: ModelDecisionTask) => void;
  inputChars: number;
  onInputCharsChange: (value: number) => void;
  outputTokens: number;
  onOutputTokensChange: (value: number) => void;
}

export default function ModelEvidenceInstrument({
  decision,
  loading,
  error,
  onCompare,
  task,
  onTaskChange,
  inputChars,
  onInputCharsChange,
  outputTokens,
  onOutputTokensChange,
}: ModelEvidenceInstrumentProps) {
  return (
    <section aria-labelledby="model-evidence-title" className="space-y-5">
      <div>
        <h2
          id="model-evidence-title"
          className="font-serif text-xl text-ink dark:text-bright"
        >
          Model evidence
        </h2>
        <p className="mt-1 text-sm text-ink-soft dark:text-starlight">
          Advisory comparison from registered providers, the operator budget,
          and measured Antiek-bench evidence when available.
        </p>
      </div>
      <div className="grid gap-3 border-y border-ink/15 py-4 dark:border-bright/15 sm:grid-cols-3">
        <label className="text-xs font-semibold text-ink-soft dark:text-starlight">
          Task
          <select
            value={task}
            onChange={(event) =>
              onTaskChange(event.target.value as ModelDecisionTask)
            }
            className="mt-1 block h-10 w-full border border-ink/20 bg-transparent px-2 text-sm text-ink dark:border-bright/20 dark:text-bright"
          >
            {DECISION_TASKS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-semibold text-ink-soft dark:text-starlight">
          Input characters
          <input
            type="number"
            min={0}
            value={inputChars}
            onChange={(event) =>
              onInputCharsChange(Number(event.target.value) || 0)
            }
            className="mt-1 block h-10 w-full border border-ink/20 bg-transparent px-2 text-sm text-ink dark:border-bright/20 dark:text-bright"
          />
        </label>
        <label className="text-xs font-semibold text-ink-soft dark:text-starlight">
          Output tokens
          <input
            type="number"
            min={0}
            value={outputTokens}
            onChange={(event) =>
              onOutputTokensChange(Number(event.target.value) || 0)
            }
            className="mt-1 block h-10 w-full border border-ink/20 bg-transparent px-2 text-sm text-ink dark:border-bright/20 dark:text-bright"
          />
        </label>
      </div>
      <button
        type="button"
        onClick={onCompare}
        disabled={loading}
        className="rounded border border-ink px-3 py-1.5 font-mono text-sm hover:bg-ink/5 disabled:opacity-50 dark:border-bright dark:hover:bg-bright/10"
      >
        {loading ? "Comparing…" : "Compare models"}
      </button>
      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
      {decision && <EvidenceRail decision={decision} />}
    </section>
  );
}

/* ── Evidence rail: sunline visual contract ───────────────────────────── */

function EvidenceRail({ decision }: { decision: ModelDecisionResponse }) {
  const hasMeasuredPick = decision.recommended_tier !== null;

  return (
    <div className="space-y-4">
      {/* Header: benchmark provenance */}
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-ink/15 pb-3 dark:border-bright/15">
        <p className="text-sm text-ink dark:text-bright">
          {hasMeasuredPick ? "Measured pick: " : "No measured pick"}
          {hasMeasuredPick && <strong>{decision.recommended_tier}</strong>}
        </p>
        <EvidenceStamp decision={decision} />
      </div>

      {/* Candidate evidence rails */}
      <ul className="space-y-2" aria-label="Model route evidence">
        {decision.candidates.map((candidate) => (
          <CandidateRail
            key={`${candidate.tier}:${candidate.provider}:${candidate.model}`}
            candidate={candidate}
            isMeasuredPick={
              hasMeasuredPick &&
              candidate.tier === decision.recommended_tier &&
              candidate.quality_basis === "measured"
            }
          />
        ))}
      </ul>

      {/* Notes */}
      {decision.notes.map((note) => (
        <p
          key={note}
          className="text-xs text-ink-soft dark:text-starlight"
        >
          {note}
        </p>
      ))}
    </div>
  );
}

/* ── Evidence stamp: benchmark provenance ─────────────────────────────── */

function EvidenceStamp({
  decision,
}: {
  decision: ModelDecisionResponse;
}) {
  if (decision.benchmark_status === "measured" && decision.benchmark_generated_at) {
    const generated = new Date(decision.benchmark_generated_at);
    const { week: weekNum, year } = getISOWeek(generated);
    const measuredCount = decision.candidates.filter(
      (candidate) =>
        candidate.quality_basis === "measured" && candidate.operationally_eligible,
    ).length;
    return (
      <p className="font-mono text-xs text-ink-soft dark:text-starlight">
        BENCH · {year}-W{weekNum} · {measuredCount}/{
          decision.benchmark_operational_candidates ??
          decision.candidates.filter((candidate) => candidate.operationally_eligible).length
        } routes measured
      </p>
    );
  }
  return (
    <p className="font-mono text-xs text-ink-soft dark:text-starlight">
      ┄ NOT MEASURED ┄
    </p>
  );
}

/* ── Candidate rail: one per route ────────────────────────────────────── */

function CandidateRail({
  candidate,
  isMeasuredPick,
}: {
  candidate: ModelDecisionCandidate;
  isMeasuredPick: boolean;
}) {
  const statusLabel = !candidate.ready
    ? "Unavailable"
    : candidate.would_exceed_budget === true
      ? "Over budget"
      : candidate.would_exceed_budget === false
        ? "AVAILABLE"
        : "Budget unknown";

  const priceRange =
    candidate.estimated_usd_low != null && candidate.estimated_usd_high != null
      ? `$${candidate.estimated_usd_low.toFixed(3)}–${candidate.estimated_usd_high.toFixed(3)}`
      : null;

  const qualityText =
    candidate.quality_basis === "measured" && candidate.quality_score != null
      ? `BENCH · n=${candidate.benchmark_samples ?? "?"} · ${(candidate.quality_score * 100).toFixed(0)}%`
      : "┄ NOT MEASURED ┄";

  const isAvailable = candidate.operationally_eligible;

  return (
    <li
      className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs"
      aria-label={`${candidate.tier} ${candidate.provider}/${candidate.model}`}
    >
      {/* Status stamp */}
      <span
        className={
          isAvailable
            ? "text-emerald-700 dark:text-emerald-300"
            : "text-amber-700 dark:text-amber-300"
        }
      >
        {statusLabel}
      </span>

      {/* Sunline rail connector */}
      <span className="text-ink/30 dark:text-bright/30" aria-hidden="true">
        ───
      </span>

      {/* Price range */}
      <span className="text-ink dark:text-bright">
        {priceRange ?? "—"}
      </span>

      {/* Rail connector */}
      <span className="text-ink/30 dark:text-bright/30" aria-hidden="true">
        ───
      </span>

      {/* Evidence stamp */}
      <span
        className={
          candidate.quality_basis === "measured"
            ? "text-ink dark:text-bright"
            : "text-ink-soft dark:text-starlight"
        }
      >
        {qualityText}
      </span>

      {/* Measured pick disc or empty */}
      <span aria-hidden="true" className="text-ink/30 dark:text-bright/30">
        ───
      </span>
      {isMeasuredPick ? (
        <span
          className="inline-block h-3 w-3 rounded-full bg-amber-500 dark:bg-amber-400"
          role="img"
          aria-label="Measured pick"
          title="Measured pick"
        />
      ) : (
        <span
          className="inline-block h-3 w-3 rounded-full border border-ink/20 dark:border-bright/20"
          role="img"
          aria-label="No measured pick"
          title="No measured pick"
        />
      )}
    </li>
  );
}

/* ── Helpers ──────────────────────────────────────────────────────────── */

function getISOWeek(date: Date): { week: number; year: number } {
  const d = new Date(
    Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()),
  );
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return {
    week: Math.ceil(((d.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7),
    year: d.getUTCFullYear(),
  };
}
