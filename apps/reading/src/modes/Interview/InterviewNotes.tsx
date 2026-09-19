import { useEffect, useRef, useState } from "react";

import { ApiError, getInterviewMargin, putInterviewMargin, type InterviewMarginShape } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import {
  hasLegacyInterviewNote,
  readRecoveryMargin,
  removeRecoveryMargin,
  writeRecoveryMargin,
  type InterviewMarginRecovery,
} from "./recoveryMargin";

type Props = { interviewId?: string; autosaveDelayMs?: number };
type SaveState = "loading" | "idle" | "saving" | "saved" | "offline" | "conflict" | "http-error" | "unavailable";

const mutationKey = () =>
  globalThis.crypto?.randomUUID?.() ?? `margin-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export default function InterviewNotes({ interviewId, autosaveDelayMs = 1200 }: Props) {
  const { sessionGeneration } = useAuth();
  const [text, setText] = useState("");
  const [state, setState] = useState<SaveState>("loading");
  const [recovery, setRecovery] = useState<InterviewMarginRecovery | null>(null);
  const [legacyPresent, setLegacyPresent] = useState(false);
  const [reviewOnly, setReviewOnly] = useState(false);
  const baseline = useRef<InterviewMarginShape | null>(null);
  const lastAttemptBody = useRef<string | null>(null);
  const context = useRef({ interviewId, sessionGeneration });
  const saveChain = useRef(Promise.resolve());
  context.current = { interviewId, sessionGeneration };

  useEffect(() => {
    baseline.current = null;
    lastAttemptBody.current = null;
    setText("");
    setRecovery(null);
    setReviewOnly(false);
    setLegacyPresent(Boolean(interviewId && hasLegacyInterviewNote(interviewId)));
    if (!interviewId) { setState("unavailable"); return; }
    const request = { interviewId, sessionGeneration };
    const abort = new AbortController();
    setState("loading");
    void getInterviewMargin(interviewId, abort.signal).then((margin) => {
      if (context.current.interviewId !== request.interviewId ||
          context.current.sessionGeneration !== request.sessionGeneration) return;
      baseline.current = margin;
      setText(margin.body);
      setRecovery(readRecoveryMargin(margin.recovery_scope, margin.account_scope, interviewId));
      setState("idle");
    }).catch((error: unknown) => {
      if ((error as { name?: string }).name === "AbortError") return;
      if (context.current.interviewId === request.interviewId &&
          context.current.sessionGeneration === request.sessionGeneration) setState("unavailable");
    });
    return () => abort.abort();
  }, [interviewId, sessionGeneration]);

  useEffect(() => {
    const current = baseline.current;
    if (!interviewId || !current || reviewOnly || text === current.body ||
        text === lastAttemptBody.current || state === "loading" || state === "unavailable") return;
    const timer = window.setTimeout(() => {
      const saveContext = { interviewId, sessionGeneration };
      const body = text;
      lastAttemptBody.current = body;
      saveChain.current = saveChain.current.then(async () => {
        const base = baseline.current;
        if (!base || context.current.interviewId !== saveContext.interviewId ||
            context.current.sessionGeneration !== saveContext.sessionGeneration) return;
        if (body === base.body) return;
        setState("saving");
        try {
          const saved = await putInterviewMargin(interviewId, {
            schema_version: 1, base_revision: base.revision, mutation_key: mutationKey(), body,
          });
          if (context.current.interviewId !== saveContext.interviewId ||
              context.current.sessionGeneration !== saveContext.sessionGeneration) return;
          baseline.current = saved;
          removeRecoveryMargin(saved.recovery_scope);
          setRecovery(null);
          setState("saved");
        } catch (error: unknown) {
          if (context.current.interviewId !== saveContext.interviewId ||
              context.current.sessionGeneration !== saveContext.sessionGeneration) return;
          if (error instanceof ApiError) {
            setState(error.status === 409 ? "conflict" : "http-error");
            return;
          }
          writeRecoveryMargin(base.recovery_scope, {
            schema_version: 1, account_scope: base.account_scope,
            interview_id: interviewId, base_revision: base.revision,
            base_content_sha256: base.content_sha256, body, saved_at: new Date().toISOString(),
          });
          setState("offline");
        }
      });
    }, autosaveDelayMs);
    return () => window.clearTimeout(timer);
  }, [autosaveDelayMs, interviewId, reviewOnly, sessionGeneration, state, text]);

  if (!interviewId) return <div className="h-full p-3 text-xs italic">No interview loaded.</div>;
  const writable = baseline.current !== null && state !== "loading" && state !== "unavailable";
  return (
    <div className="h-full flex flex-col bg-ice-0 dark:bg-charcoal-2" data-interview-margin data-hydrated={baseline.current ? "true" : "false"}>
      <header className="px-3 py-2 flex items-center justify-between border-b border-rule dark:border-charcoal-1">
        <h3 className="text-xs font-mono uppercase tracking-wider">Notes · operator margin</h3>
        <span className="text-[10px] font-mono">{
          state === "saving" ? "saving…" : state === "saved" ? "saved" :
          state === "offline" ? "recovery saved locally" : state === "conflict" ? "conflict — reload" :
          state === "http-error" ? "save failed — retry" :
          state === "unavailable" ? "save unavailable" : ""
        }</span>
      </header>
      {legacyPresent && <p className="px-3 py-1 text-[10px]">Legacy unscoped note detected; its bytes were not read.</p>}
      {recovery && <button type="button" onClick={() => { setText(recovery.body); setReviewOnly(true); }} className="m-2 text-xs underline">Review local recovery draft</button>}
      {reviewOnly && <p className="px-3 text-[10px]">Recovery review only. Edit to create a new canonical save.</p>}
      {state === "http-error" && <button type="button" onClick={() => {
        lastAttemptBody.current = null; setState("idle");
      }} className="m-2 text-xs underline">Retry save</button>}
      <textarea
        value={text}
        disabled={!writable}
        onChange={(event) => { setText(event.target.value); if (reviewOnly) setReviewOnly(false); }}
        placeholder="Body-language cues, emphasis, follow-ups…"
        className="flex-1 w-full p-3 font-serif text-[14px] bg-transparent outline-none resize-none disabled:opacity-60"
      />
      <footer className="px-3 py-2 border-t text-[10px] font-mono">Account-private, revisioned server margin.</footer>
    </div>
  );
}
