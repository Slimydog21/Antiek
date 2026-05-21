// SPR-06 / M1 — Import progress indicator.
//
// =============================================================
// IMPORTANT — Real backend phases, not synthetic (per rigor #3):
// =============================================================
//
// The sprint HTML page named five phases (fetch, extract, chunk,
// embed, ready). The SPR-03 backend pipeline (services/ingestion/
// pipeline.py) does NOT emit five granular phase updates: it
// writes the job row at three observable moments —
//
//   1. status: "running"  (immediately after create_job; no
//      content_type yet → user-visible as "fetching")
//   2. status: "running" + content_type: "<pdf|html|...>"
//      (after content-type detection succeeds → user-visible as
//      "extracting", because by the time content_type lands the
//      next step is extract → chunk → embed → write, lumped
//      together as one substrate transaction)
//   3. status: "succeeded" / "failed"
//
// The "five phases" in the spec corresponded to internal pipeline
// stages that are NOT individually observable to a polling client
// today. Rather than fake a five-step UI with synthetic timers
// (the cardinal consumer-UX sin per rigor #3), this component
// surfaces the three real signals as four user-visible states:
//
//   pending   → "Queued"           (job row exists, not picked up)
//   fetching  → "Fetching content" (running, no content_type yet)
//   ingesting → "Extracting and chunking" (running, content_type known)
//   ready / failed → terminal
//
// If a later sprint expands the pipeline to emit granular phase
// updates (job row gains a `phase` column, pipeline writes
// `phase="fetch" / "extract" / "chunk" / "embed"`), this component
// reads it and shows the full five-step bar without API changes.
// The contract upgrade is in the IngestJob.metadata key
// "current_phase" (the only metadata key this component looks at
// today; absent → fall through to coarse mapping).
// =============================================================

import type { IngestContentType, IngestJob, IngestJobStatus } from
  "../../../api/library/types";

/** User-visible phase label. Mapped from the real job state, not a
 * synthetic timer. */
export type ImportPhase =
  | "pending"
  | "fetching"
  | "extracting"
  | "ready"
  | "failed";

export interface ImportProgressInput {
  status: IngestJobStatus;
  content_type: IngestContentType | null;
  /** If the future pipeline lands granular phases, read them here.
   * Today, always undefined. */
  phaseHint?: string | null;
}

/** Map the raw IngestJob fields to a user-visible phase. Honest
 * about the granularity actually available. */
export function deriveImportPhase(input: ImportProgressInput): ImportPhase {
  if (input.status === "succeeded") return "ready";
  if (input.status === "failed") return "failed";
  if (input.status === "pending") return "pending";
  // status === "running"
  if (input.phaseHint === "fetch") return "fetching";
  if (input.phaseHint === "extract" || input.phaseHint === "chunk" || input.phaseHint === "embed") {
    return "extracting";
  }
  // No granular hint — content_type arrival is our "fetch finished" signal.
  if (input.content_type) return "extracting";
  return "fetching";
}

const PHASE_LABEL: Record<ImportPhase, string> = {
  pending: "Queued",
  fetching: "Fetching content",
  extracting: "Extracting and chunking",
  ready: "Ready",
  failed: "Failed",
};

const PHASE_DETAIL: Record<ImportPhase, string> = {
  pending: "Waiting for the worker to pick this up.",
  fetching: "Reaching out to the source URL.",
  extracting: "Reading the document body and indexing it.",
  ready: "Imported. Click the card to start reading.",
  failed: "We couldn't import this one. See the error below.",
};

/** Step order for the visual progress bar. `failed` is rendered
 * separately so it doesn't share a track with the success path. */
const ORDERED_PHASES: ImportPhase[] = ["pending", "fetching", "extracting", "ready"];

export interface ImportProgressProps {
  /** The most recent job row from `getIngestJob`. `null` while we
   * haven't yet received the first poll response. */
  job: IngestJob | null;
  /** Optional override for tests / Storybook. */
  initialStatus?: IngestJobStatus;
}

/** Compact inline progress indicator. Rendered next to / under the
 * URL paste bar. */
export function ImportProgress({ job, initialStatus }: ImportProgressProps) {
  const status: IngestJobStatus =
    job?.status ?? initialStatus ?? "pending";
  const contentType: IngestContentType | null = job?.content_type ?? null;
  const phaseHint = job?.metadata?.["current_phase"] as string | undefined | null;

  const phase = deriveImportPhase({
    status,
    content_type: contentType,
    phaseHint: phaseHint ?? null,
  });

  const isFailed = phase === "failed";
  const failureMessage = job?.error
    ? humanizeError(job.error, job.error_detail ?? null)
    : null;

  return (
    <div
      className="border-edge border-sun rounded-hog bg-ice-0 dark:bg-charcoal-2 px-4 py-3 shadow-z1 dark:shadow-z1-night"
      data-testid="import-progress"
      data-phase={phase}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <p className="font-mono text-[12px] font-semibold uppercase tracking-wider text-ink dark:text-bright">
          {PHASE_LABEL[phase]}
        </p>
        {contentType && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            {contentType}
          </span>
        )}
      </div>

      {!isFailed && (
        <div className="flex items-center gap-1.5" aria-hidden="true">
          {ORDERED_PHASES.map((p) => {
            const reached = orderedIndex(phase) >= orderedIndex(p);
            return (
              <div
                key={p}
                data-phase-step={p}
                data-reached={reached}
                className={
                  "h-1.5 flex-1 rounded-full " +
                  (reached
                    ? "bg-sun"
                    : "bg-ice-3 dark:bg-charcoal-1")
                }
              />
            );
          })}
        </div>
      )}

      <p className="text-[12px] text-shadow-2 dark:text-starlight mt-2">
        {PHASE_DETAIL[phase]}
      </p>

      {isFailed && failureMessage && (
        <p className="text-[12px] text-emperor mt-2 font-mono" data-testid="import-progress-error">
          {failureMessage}
        </p>
      )}
    </div>
  );
}

function orderedIndex(p: ImportPhase): number {
  if (p === "failed") return -1;
  return ORDERED_PHASES.indexOf(p);
}

/** Map raw backend error codes (substrate-internal) to consumer-
 * facing copy. Anything we don't recognise falls through to the raw
 * string — intentional, so we don't lie about what happened. */
export function humanizeError(code: string, detail: string | null): string {
  if (code === "domain_banned") {
    return "The site is rate-limiting us. Try again in a few minutes.";
  }
  if (code === "robots_disallowed") {
    return "The site asked crawlers not to index this URL.";
  }
  if (code === "low_word_count") {
    return "We extracted very little text. The page may be JS-only or paywalled.";
  }
  if (code.startsWith("http_4")) {
    return `The server rejected the request (${code.replace("http_", "HTTP ")}). Check the URL.`;
  }
  if (code.startsWith("http_5")) {
    return `The source server had an error (${code.replace("http_", "HTTP ")}). Try again later.`;
  }
  if (code === "extraction_failed") {
    return "We couldn't parse the content. Detail: " + (detail ?? code);
  }
  if (code === "content_type_detection_failed") {
    return "We couldn't determine what kind of document this URL is.";
  }
  if (code === "poll_timeout") {
    return "Import is taking longer than expected; it may still finish in the background.";
  }
  return `Import failed: ${code}${detail ? ` — ${detail}` : ""}`;
}

export default ImportProgress;
