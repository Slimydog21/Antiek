/**
 * PromptCard — one generated cascade prompt with copy / signal /
 * paste-back. Self-contained state machine; failures route to an
 * inline error, never silently swallowed.
 */

import type { ReactNode } from "react";
import { useState } from "react";
import {
  LemonButton, LemonCard, LemonTag, LemonTextarea, toast,
} from "../../components/lemon";
import type { GapPromptPayload } from "./api_client";
import type { PasteBackResult, SignalType } from "./hooks";
import { SOURCE_VISUAL } from "./types";

type CardState =
  | { kind: "collapsed" }
  | { kind: "expanded" }
  | { kind: "paste_open" }
  | { kind: "submitting" }
  | { kind: "answered"; result: PasteBackResult };

export interface PromptCardProps {
  prompt: GapPromptPayload;
  currentSignal?: SignalType;
  signalError?: Error;
  onSignal: (promptId: string, signalType: SignalType) => Promise<void> | void;
  onPasteBack: (prompt: GapPromptPayload, rawText: string) => Promise<PasteBackResult>;
  className?: string;
}

export function PromptCard({
  prompt, currentSignal, signalError, onSignal, onPasteBack, className,
}: PromptCardProps) {
  const [state, setState] = useState<CardState>({ kind: "collapsed" });
  const [draft, setDraft] = useState<string>("");
  const [pasteError, setPasteError] = useState<Error | null>(null);

  const providerVisual = SOURCE_VISUAL[prompt.target_provider];

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(prompt.prompt_text);
      toast.ok("Prompt copied — paste into your LLM");
    } catch {
      toast.warn("Clipboard unavailable; expand to copy manually");
      setState({ kind: "expanded" });
    }
  };

  const handleSignal = async (kind: SignalType) => {
    try {
      await onSignal(prompt.prompt_id, kind);
    } catch {
      // useSignals already rolled back + recorded the error.
    }
  };

  const submitPasteBack = async () => {
    if (!draft.trim()) {
      setPasteError(new Error("Paste the answer text before submitting."));
      return;
    }
    setState({ kind: "submitting" });
    setPasteError(null);
    try {
      const result = await onPasteBack(prompt, draft);
      setState({ kind: "answered", result });
      setDraft("");
    } catch (e) {
      setPasteError(e as Error);
      setState({ kind: "paste_open" });
    }
  };

  const header: ReactNode = (
    <div className="flex items-center gap-2">
      <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright">
        #{prompt.order_index}
      </span>
      <LemonTag colour={providerVisual.tagColour}>{providerVisual.label}</LemonTag>
      {prompt.depends_on_prior_order_index !== null && (
        <LemonTag colour="muted">depends on #{prompt.depends_on_prior_order_index}</LemonTag>
      )}
      <div className="ml-auto flex items-center gap-1">
        <LemonButton
          size="sm"
          variant={currentSignal === "would_run" ? "primary" : "secondary"}
          onClick={() => handleSignal("would_run")}
          aria-pressed={currentSignal === "would_run"}
          aria-label="Mark this prompt as 'would run'"
        >
          👍
        </LemonButton>
        <LemonButton
          size="sm"
          variant={currentSignal === "skip" ? "danger" : "secondary"}
          onClick={() => handleSignal("skip")}
          aria-pressed={currentSignal === "skip"}
          aria-label="Mark this prompt as 'skip'"
        >
          👎
        </LemonButton>
      </div>
    </div>
  );

  const expectedShape: ReactNode = prompt.expected_output_shape && (
    <div className="text-xs text-shadow-2 dark:text-moonlight italic">
      Expect: {prompt.expected_output_shape}
    </div>
  );
  const rationale: ReactNode = prompt.rationale && (
    <div className="text-xs text-shadow-2 dark:text-moonlight">
      <span className="font-bold">Why:</span> {prompt.rationale}
    </div>
  );
  const signalErrorBanner: ReactNode = signalError && (
    <div className="text-xs text-emperor">Signal save failed: {signalError.message}</div>
  );

  const rootClasses = ["w-full", className ?? ""].filter(Boolean).join(" ");

  if (state.kind === "collapsed") {
    return (
      <div className={rootClasses}>
        <LemonCard
          elevation="z1" colour="card" title={header}
          footer={
            <div className="flex gap-2">
              <LemonButton size="sm" variant="secondary"
                onClick={() => setState({ kind: "expanded" })}>Expand</LemonButton>
              <LemonButton size="sm" variant="primary" onClick={copyToClipboard}>Copy prompt</LemonButton>
            </div>
          }
        >
          <div className="text-sm text-ink dark:text-bright truncate">{prompt.prompt_text}</div>
          {signalErrorBanner}
        </LemonCard>
      </div>
    );
  }

  if (state.kind === "answered") {
    return (
      <div className={rootClasses}>
        <LemonCard elevation="z2" colour="aurora" title={header}>
          <div className="text-sm font-medium">Answer recorded.</div>
          <div className="text-xs text-shadow-2">
            New paste <code>{state.result.document_id.slice(0, 22)}…</code>{" "}
            extracted {state.result.insights_count} insight
            {state.result.insights_count === 1 ? "" : "s"} and{" "}
            {state.result.open_questions_count} open question
            {state.result.open_questions_count === 1 ? "" : "s"}.
          </div>
          <div className="mt-2 flex gap-2">
            <LemonButton size="sm" variant="secondary"
              onClick={() => setState({ kind: "collapsed" })}>Collapse</LemonButton>
          </div>
        </LemonCard>
      </div>
    );
  }

  const pasteOpen = state.kind === "paste_open";
  const submitting = state.kind === "submitting";

  return (
    <div className={rootClasses}>
      <LemonCard elevation="z2" colour="card" title={header}>
        <div className="flex flex-col gap-2">
          {expectedShape}
          {rationale}
          {signalErrorBanner}
          <div className="text-sm whitespace-pre-wrap text-ink dark:text-bright p-2 bg-ice-3 dark:bg-charcoal-1 border-l-2 border-sun-deep">
            {prompt.prompt_text}
          </div>
          {pasteOpen || submitting ? (
            <div className="flex flex-col gap-2">
              <LemonTextarea
                placeholder={`Paste the ${providerVisual.label} answer here. We'll ingest it, extract insights + open questions, and link it back to this prompt.`}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={8}
                disabled={submitting}
                aria-label="Paste-back textarea"
              />
              {pasteError && <div className="text-xs text-emperor">{pasteError.message}</div>}
              <div className="flex gap-2">
                <LemonButton size="sm" variant="primary" onClick={submitPasteBack} disabled={submitting}>
                  {submitting ? "Submitting…" : "Submit answer"}
                </LemonButton>
                <LemonButton size="sm" variant="secondary"
                  onClick={() => { setState({ kind: "expanded" }); setPasteError(null); }}
                  disabled={submitting}>Cancel</LemonButton>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <LemonButton size="sm" variant="primary" onClick={copyToClipboard}>Copy prompt</LemonButton>
              <LemonButton size="sm" variant="secondary"
                onClick={() => setState({ kind: "paste_open" })}>Paste answer back</LemonButton>
              <LemonButton size="sm" variant="secondary"
                onClick={() => setState({ kind: "collapsed" })}>Collapse</LemonButton>
            </div>
          )}
        </div>
      </LemonCard>
    </div>
  );
}
