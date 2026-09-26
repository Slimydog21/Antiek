/**
 * ReformatFlow — the reformat prompt on the island's expanded card
 * (reformat-provenance SPR-02). The prompt calls the reformat route and the
 * engagement stays in the card; it does NOT ride the spawn flow. A generation
 * is not an investigation, so nothing is linked to the island's anchor (the
 * anchor keeps its own thread) and no id pretends to be a thread (LB-4a).
 *
 * ASK-TO-OPEN: when the generation completes, the card ASKS to open the
 * derived document — the operator confirms (never auto-opened) and the
 * derived document opens BESIDE the source as the ONE reader window for
 * its id, with the reformat origin (the generation). Declining opens
 * nothing, and the card keeps the way back: while it is provisional the
 * derivative is not in the library.
 *
 * Every failure says what happened (the model unavailable, the source too
 * long, rights that refuse a derivative), never a generic "didn't start".
 */
import { useState } from "react";

import { ApiError } from "../../../lib/api";
import { openWindow, readerWindowId } from "../../../components/windows/openWindow";
import { toast } from "../../../components/lemon/LemonToast";
import LemonButton from "../../../components/lemon/LemonButton";
import LemonTextarea from "../../../components/lemon/LemonTextarea";
import { postReformat } from "../../../api/reformat";
import type { ReformatMode, ReformatResponse } from "../../../api/reformat";

export interface ReformatFlowProps {
  documentId: string;
  /** The island's anchor. The reformat reads the whole source and is not
   *  linked to the anchor, which keeps its own thread. */
  anchorId: string;
  /** The island's passage quote (the operator's reading context) — null on
   *  a metadata-only anchor. */
  passageQuote: string | null;
  onClose: () => void;
}

type Phase = "composing" | "busy" | "ask" | "done" | "error";

/** What the operator reads when the reformat route refuses. */
export function reformatFailureMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "The reformat couldn't reach the server. Nothing was generated.";
  const detail = (() => {
    try {
      const parsed = JSON.parse(e.body) as { detail?: unknown };
      return typeof parsed.detail === "string" ? parsed.detail : "";
    } catch {
      return "";
    }
  })();
  if (e.status === 503) return "The reformat model isn't available right now. Nothing was generated.";
  if (e.status === 404) return "This book isn't yours to reformat, or it no longer exists.";
  if (e.status === 422) {
    if (detail.startsWith("source_too_long")) {
      return "This source is too long to reformat in one go. Reformat a part of it instead.";
    }
    if (detail.startsWith("derived_source_unsupported")) {
      return "A reformatted version can't be reformatted again yet. Reformat the original.";
    }
    if (detail.includes("not served")) {
      return "This source can't be read in full, so there's nothing to reformat.";
    }
    return "The reformat couldn't be made from this source. Nothing was saved.";
  }
  return `The reformat failed (HTTP ${e.status}). Nothing was saved.`;
}

export default function ReformatFlow({
  documentId,
  passageQuote: _passageQuote,
  onClose,
}: ReformatFlowProps) {
  const [phase, setPhase] = useState<Phase>("composing");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<ReformatMode>("time_window");
  const [result, setResult] = useState<ReformatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function launch() {
    const q = prompt.trim();
    if (q.length < 3) {
      setError("Say what you want the reformat to do first.");
      return;
    }
    setPhase("busy");
    setError(null);
    try {
      setResult(await postReformat(documentId, { prompt: q, mode }));
      setPhase("ask");
    } catch (e) {
      const message = reformatFailureMessage(e);
      setError(message);
      setPhase("error");
      toast.warn(message);
    }
  }

  function openDerived() {
    if (!result) return;
    openWindow(
      "reader",
      {
        documentId: result.derived_document_id,
        origin: { from: "reformat", id: result.generation_id },
      },
      { id: readerWindowId(result.derived_document_id), title: "Reformatted source" },
    );
    setPhase("done");
  }

  if (phase === "ask" && result) {
    return (
      <div data-reformat-ask className="mb-2 border-t border-hairline pt-2">
        <p className="text-shadow-1 dark:text-moonlight mb-1.5" role="status">
          Your reformatted version is ready — open it beside this book?
        </p>
        <div className="flex items-center gap-2">
          <LemonButton variant="primary" size="sm" onClick={openDerived}>
            Open it
          </LemonButton>
          <button
            type="button"
            onClick={() => setPhase("done")}
            className="text-shadow-1 hover:text-ink dark:hover:text-bright"
            title="It stays here in this card; it isn't in the library while it's provisional"
          >
            Not now
          </button>
        </div>
      </div>
    );
  }

  if (phase === "done") {
    return (
      <div data-reformat-done className="mb-2 border-t border-hairline pt-2">
        <p className="text-shadow-1 dark:text-moonlight mb-1.5" role="status">
          {result
            ? "Reformatted. It isn't in the library while it's provisional; open it from here."
            : "Closed."}
        </p>
        <div className="flex items-center gap-2">
          {result ? (
            <button
              type="button"
              onClick={openDerived}
              className="text-sun-deep underline-offset-2 hover:underline dark:text-sun"
            >
              Open the reformatted version
            </button>
          ) : null}
          <button
            type="button"
            onClick={onClose}
            className="text-shadow-1 hover:text-ink dark:hover:text-bright"
          >
            Done
          </button>
        </div>
      </div>
    );
  }

  return (
    <div data-reformat-flow className="mb-2 border-t border-hairline pt-2">
      <label className="text-xxs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-1">
        Reformat this book
      </label>
      <div className="mb-1.5 flex items-center gap-2 text-xxs font-mono text-shadow-1 dark:text-moonlight">
        <button
          type="button"
          onClick={() => setMode("time_window")}
          aria-pressed={mode === "time_window"}
          className={mode === "time_window" ? "text-sun-deep dark:text-sun underline" : ""}
        >
          read in a time window
        </button>
        <button
          type="button"
          onClick={() => setMode("themes")}
          aria-pressed={mode === "themes"}
          className={mode === "themes" ? "text-sun-deep dark:text-sun underline" : ""}
        >
          around themes &amp; questions
        </button>
      </div>
      <LemonTextarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={phase === "busy"}
        minRows={2}
        maxRows={6}
        aria-label="What should the reformat do?"
      />
      {error && (
        <p className="mt-1 text-xxs font-mono text-emperor" role="alert">
          {error}
        </p>
      )}
      <div className="flex items-center justify-end gap-2 mt-2">
        <button
          type="button"
          onClick={onClose}
          className="text-shadow-1 hover:text-ink dark:hover:text-bright"
        >
          Cancel
        </button>
        <LemonButton
          variant="primary"
          size="sm"
          onClick={() => void launch()}
          disabled={phase === "busy" || prompt.trim().length < 3}
        >
          {phase === "busy" ? "Reformatting…" : "Reformat"}
        </LemonButton>
      </div>
    </div>
  );
}
