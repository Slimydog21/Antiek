// SPR-06 / M1 — URL paste bar (header on the Library page).
//
// Primary affordance: a single text input that accepts a URL, POSTs
// it to /api/library/ingest (via the SPR-03 client wrapper), and
// renders an ImportProgress block until the job reaches a terminal
// state. Drag-and-drop PDFs land on the same input.
//
// On success the parent component (`LibraryGrid`) re-fetches the
// document list so the new card appears. We don't try to optimistically
// merge — the source of truth for what's on the card (cover, paywall
// flag, title, source_uri) is the substrate, and a re-fetch is
// cheaper than reproducing the substrate's rules client-side.
//
// Behavior events: emits `document_opened` when the user clicks the
// "Open" affordance on the just-imported job. The closed taxonomy
// does NOT yet include `document_imported` — the spec text referenced
// it but substrate/behavior/taxonomy.py only carries `document_opened`,
// `document_closed`, etc. Adding `document_imported` requires a
// taxonomy migration + schema file + version bump, which is out of
// scope for a UI surface sprint. Surfaced in the handoff.

import { useCallback, useEffect, useRef, useState } from "react";

import { LemonButton, LemonInput, toast } from "../../components/lemon";
import {
  IngestError,
  getIngestJob,
  postIngest,
} from "../../../api/library/ingest";
import type { IngestJob } from "../../../api/library/types";

import { ImportProgress, humanizeError } from "./ImportProgress";

export interface UrlPasteBarProps {
  /** Operator user id. Same value the auth context already carries —
   * pulled by the parent so this component stays storybook-renderable. */
  userId: string;
  /** Called when an import has reached a terminal state (success or
   * failure). Parent uses this to re-fetch the document list and
   * surface a toast. The `document_id` will be set on success only. */
  onImportTerminal?: (job: IngestJob) => void;
  /** Optional URL prefill — used by the empty-state quick-import
   * affordance ("paste a URL or try one of these"). */
  prefillUrl?: string;
}

type FlowState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "polling"; jobId: string; lastJob: IngestJob | null }
  | { kind: "terminal"; job: IngestJob };

/** Validate the URL minimally so the user gets immediate feedback for
 * obvious typos before the network round-trip. The backend does its
 * own stricter validation. */
function shallowValidateUrl(raw: string): { ok: true } | { ok: false; msg: string } {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { ok: false, msg: "Paste a URL or drop a file." };
  }
  // Accept bare domains the user pastes without scheme — we'll prefix
  // https:// at submit time. That's a forgiving UX choice that matches
  // browser address-bar behavior.
  if (!/^https?:\/\//i.test(trimmed) && !/^[a-z0-9.-]+\.[a-z]{2,}/i.test(trimmed)) {
    return { ok: false, msg: "That doesn't look like a URL." };
  }
  return { ok: true };
}

function normaliseUrl(raw: string): string {
  const trimmed = raw.trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

export function UrlPasteBar({ userId, onImportTerminal, prefillUrl }: UrlPasteBarProps) {
  const [value, setValue] = useState<string>(prefillUrl ?? "");
  const [flow, setFlow] = useState<FlowState>({ kind: "idle" });
  const [validationError, setValidationError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState<boolean>(false);
  const pollAbort = useRef<{ cancelled: boolean }>({ cancelled: false });

  // If parent passes a prefill (empty-state quick link), pre-populate
  // the input but don't auto-submit; the user clicked the link, but
  // they should still see and confirm the URL.
  useEffect(() => {
    if (prefillUrl !== undefined) {
      setValue(prefillUrl);
      setValidationError(null);
    }
  }, [prefillUrl]);

  // Cancel any in-flight polling on unmount.
  useEffect(() => {
    const localAbort = pollAbort.current;
    return () => {
      localAbort.cancelled = true;
    };
  }, []);

  const handleTerminal = useCallback(
    (job: IngestJob) => {
      setFlow({ kind: "terminal", job });
      onImportTerminal?.(job);
      if (job.status === "succeeded") {
        toast.ok(
          job.metadata?.["paywalled"]
            ? "Imported (partial — paywall detected)"
            : "Imported. Click the card to start reading.",
        );
      } else {
        toast.err(humanizeError(job.error ?? "unknown_failure", job.error_detail ?? null));
      }
    },
    [onImportTerminal],
  );

  const submit = useCallback(
    async (urlToSubmit: string) => {
      const validation = shallowValidateUrl(urlToSubmit);
      if (!validation.ok) {
        setValidationError(validation.msg);
        return;
      }
      setValidationError(null);
      setFlow({ kind: "submitting" });
      pollAbort.current = { cancelled: false };
      const localAbort = pollAbort.current;
      try {
        const resp = await postIngest({
          url: normaliseUrl(urlToSubmit),
          user_id: userId,
        });

        // Synchronous-fast path: backend returned terminal status
        // already. (Happens when the doc is cached and the pipeline
        // short-circuits.) We still build a synthetic IngestJob row
        // so the rest of the flow is uniform.
        if (resp.status === "succeeded" || resp.status === "failed") {
          const syntheticJob: IngestJob = {
            job_id: resp.job_id,
            url: urlToSubmit,
            user_id: userId,
            investigation_id: "__operator__",
            status: resp.status,
            content_type: resp.content_type,
            document_id: resp.document_id,
            error: resp.error,
            error_detail: null,
            attempts: 1,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            metadata: { paywalled: !!resp.paywalled },
          };
          handleTerminal(syntheticJob);
          return;
        }

        // Otherwise we poll. We re-implement pollUntilTerminal inline
        // because we want each tick to update React state for the
        // ImportProgress indicator — `pollUntilTerminal`'s `onUpdate`
        // would work too, but keeping the loop inline keeps the
        // cancellation contract obvious.
        setFlow({ kind: "polling", jobId: resp.job_id, lastJob: null });
        const intervalMs = 1500;
        const timeoutMs = 90_000;
        const start = Date.now();
        let lastJob: IngestJob | null = null;
        while (!localAbort.cancelled) {
          try {
            lastJob = await getIngestJob(resp.job_id);
          } catch (e) {
            // One-off transient errors during polling shouldn't kill
            // the flow; just keep trying until timeout. If it's an
            // auth failure we'll eventually time out.
            if (e instanceof IngestError && e.status === 404) {
              toast.err("Job disappeared from the queue.");
              break;
            }
          }
          if (lastJob) {
            setFlow({ kind: "polling", jobId: resp.job_id, lastJob });
            if (lastJob.status === "succeeded" || lastJob.status === "failed") {
              handleTerminal(lastJob);
              return;
            }
          }
          if (Date.now() - start > timeoutMs) {
            const timeoutJob: IngestJob = lastJob ?? {
              job_id: resp.job_id,
              url: urlToSubmit,
              user_id: userId,
              investigation_id: "__operator__",
              status: "failed",
              content_type: null,
              document_id: null,
              error: "poll_timeout",
              error_detail: null,
              attempts: 1,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              metadata: {},
            };
            handleTerminal({
              ...timeoutJob,
              status: "failed",
              error: timeoutJob.error ?? "poll_timeout",
            });
            return;
          }
          await new Promise((r) => setTimeout(r, intervalMs));
        }
      } catch (e: unknown) {
        const code = e instanceof IngestError ? e.code : "unknown";
        const detail =
          e instanceof IngestError
            ? typeof e.detail === "object" && e.detail !== null && "error" in e.detail
              ? String((e.detail as { error?: { message?: string } }).error?.message ?? "")
              : null
            : e instanceof Error
              ? e.message
              : String(e);
        const failedJob: IngestJob = {
          job_id: "local-" + Date.now(),
          url: urlToSubmit,
          user_id: userId,
          investigation_id: "__operator__",
          status: "failed",
          content_type: null,
          document_id: null,
          error: code,
          error_detail: detail,
          attempts: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          metadata: {},
        };
        handleTerminal(failedJob);
      }
    },
    [handleTerminal, userId],
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void submit(value);
  };

  const onDrop = (e: React.DragEvent<HTMLFormElement>) => {
    e.preventDefault();
    setDragOver(false);
    // For now, file drop is dev-affordance: extract the file name as
    // the "URL" so the user gets feedback that drop was received. Real
    // PDF-upload via multipart needs a backend endpoint that doesn't
    // exist on /api/library/ingest yet (the route takes {url, user_id}
    // only). Surfaced in the handoff under "out-of-scope temptations".
    const file = e.dataTransfer.files?.[0];
    if (file) {
      toast.info(
        `Drop received: ${file.name}. PDF upload via multipart is not wired in SPR-06 — paste a URL instead.`,
      );
    } else {
      const text = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
      if (text) {
        setValue(text);
      }
    }
  };

  const onReset = () => {
    setFlow({ kind: "idle" });
    setValue("");
    setValidationError(null);
  };

  const isBusy = flow.kind === "submitting" || flow.kind === "polling";

  return (
    <div className="space-y-3" data-testid="url-paste-bar">
      <form
        onSubmit={onSubmit}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={
          "flex items-center gap-2 " +
          (dragOver ? "ring-2 ring-sun rounded-hog" : "")
        }
        aria-label="Import a URL or PDF"
      >
        <div className="flex-1">
          <LemonInput
            type="url"
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (validationError) setValidationError(null);
            }}
            placeholder="Paste a URL or upload a PDF"
            disabled={isBusy}
            aria-label="URL"
            data-testid="url-paste-input"
          />
        </div>
        <LemonButton
          type="submit"
          variant="primary"
          disabled={isBusy}
          data-testid="url-paste-submit"
        >
          {isBusy ? "Importing…" : "Import"}
        </LemonButton>
        {flow.kind === "terminal" && (
          <LemonButton type="button" variant="tertiary" onClick={onReset}>
            Clear
          </LemonButton>
        )}
      </form>

      {validationError && (
        <p className="text-[12px] text-emperor font-mono" data-testid="url-paste-validation">
          {validationError}
        </p>
      )}

      {flow.kind === "submitting" && (
        <ImportProgress job={null} initialStatus="pending" />
      )}
      {flow.kind === "polling" && (
        <ImportProgress job={flow.lastJob} initialStatus="running" />
      )}
      {flow.kind === "terminal" && (
        <ImportProgress job={flow.job} />
      )}
    </div>
  );
}

export default UrlPasteBar;
