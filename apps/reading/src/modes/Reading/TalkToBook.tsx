import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LemonButton, LemonSelect } from "../../components/lemon";
import {
  askBook,
  BookModelOperationNotFoundError,
  cancelBookModelOperation,
  getBookModelOperation,
  judgeBookAnswer,
  reconcileBookModelOperation,
  SelectedBookModelUnavailableError,
} from "../../api/books";
import type { BookCitation, BookModelReceipt, UserModelChoice } from "../../api/books";
import { fetchUserModels } from "../../api/settingsModels";
import type { UserModelRow } from "../../api/settingsModels";
import ReadAloud from "../../components/voice/ReadAloud";
import { useTalkThread } from "./useTalkThread";
import type { TalkMessage } from "./useTalkThread";

type RoutableUserModel = UserModelRow & { route_eligible?: boolean };

const modelKey = (providerId: string, modelId: string) => `${providerId}\u0000${modelId}`;
const isRouteEligible = (model: UserModelRow) =>
  (model as RoutableUserModel).route_eligible === true;

/**
 * TalkToBook — the floating bookmark: a book-level MULTI-TURN conversation
 * (Read SPR-08 M2).
 *
 * This is the NEW book-level surface (the SPR-04 selection FloatMenu Dialogue
 * stays ONE-SHOT — it is NOT converted). A persistent conversation that:
 *   • remembers earlier turns and sends the recent tail as context each turn
 *     (multi-turn, backed by `POST /books/{id}/ask`);
 *   • CITES page-level locations — clicking a citation jumps the SPR-07 reader
 *     to that page (reuses the reader's `setPageIndex` via `onJumpToPage`);
 *   • BRANCHES into a "what about that?" tangent off any turn;
 *   • persists per-book in SESSION state (the floating bookmark) so it survives
 *     page navigation (`useTalkThread` → sessionStorage, the usePosition
 *     precedent — NOT substrate truth);
 *   • reads any answer aloud via the SPR-14 shared TTS service (`ReadAloud`).
 *
 * §9.0: a withheld region can never be cited — the backend search gate keeps a
 * withheld body out of the model context and the citation set, so this surface
 * never receives one. An ungrounded answer (no extractable text / withheld) is
 * labelled honestly.
 *
 * APPROXIMATE PAGES: a citation whose page did not resolve to a `Page N` marker
 * is shown as "open the book", NEVER a fabricated page number (no false
 * precision — rigor #1).
 */

export interface TalkToBookProps {
  documentId: string;
  title: string | null;
  /** Jump the reader to a page (the reader passes its windowForTocPage +
   * setPageIndex composition). Reuses the EXISTING page navigation, not a
   * parallel one. */
  onJumpToPage: (pageIndex: number) => void;
}

export default function TalkToBook({ documentId, title, onJumpToPage }: TalkToBookProps) {
  const thread = useTalkThread(documentId);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<UserModelRow[]>([]);
  const [modelsState, setModelsState] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const [modelChoice, setModelChoice] = useState<UserModelChoice | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const modelRequestRef = useRef(0);
  const selectorRef = useRef<HTMLDivElement>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);

  const turnCount = thread.messages.length;
  const branchCount = thread.state.branches.length;
  const unresolvedOperations = thread.state.branches
    .flatMap((branch) => branch.messages)
    .filter((message) =>
      Boolean(message.operation_id && message.model_operation_state) &&
      message.model_operation_state !== "settled" &&
      message.model_operation_state !== "cancelled",
    );
  const selectedDispatchBlocked = unresolvedOperations.length > 0;
  const setModelOperationState = thread.setModelOperationState;
  const markModelOperationNotFound = thread.markModelOperationNotFound;
  const abandonMissingModelOperation = thread.abandonMissingModelOperation;
  const failTurn = thread.failTurn;

  const refreshModels = useCallback(async () => {
    const request = ++modelRequestRef.current;
    setModelsState("loading");
    try {
      const inventory = await fetchUserModels();
      if (request !== modelRequestRef.current) return;
      setModels(inventory.models);
      setModelsState("ready");
    } catch {
      if (request === modelRequestRef.current) setModelsState("failed");
    }
  }, []);

  const checkOperation = useCallback(async (
    message: TalkMessage,
    action: "status" | "reconcile" | "cancel" = "status",
  ) => {
    if (!message.operation_id) return;
    setOperationError(null);
    try {
      const status = action === "reconcile"
        ? await reconcileBookModelOperation(message.operation_id)
        : action === "cancel"
          ? await cancelBookModelOperation(message.operation_id)
          : await getBookModelOperation(message.operation_id);
      setModelOperationState(message.id, status.state);
      if (status.state === "cancelled") {
        failTurn(message.id);
        setModelChoice(null);
        void refreshModels();
      }
    } catch (statusError) {
      if (action === "status" && statusError instanceof BookModelOperationNotFoundError) {
        markModelOperationNotFound(message.id);
        setOperationError(
          "The server did not find this operation. Check again before considering abandonment.",
        );
      } else {
        setOperationError(action === "cancel"
          ? "This operation could not be released. Check its status before retrying."
          : "Operation status is temporarily unavailable. Do not retry the selected model yet.");
      }
    }
  }, [failTurn, markModelOperationNotFound, refreshModels, setModelOperationState]);

  const abandonMissingOperation = useCallback((message: TalkMessage) => {
    if ((message.operation_not_found_checks ?? 0) < 2) return;
    if (!window.confirm(
      "The server repeatedly reported that this operation does not exist. Abandon this unsent request?",
    )) return;
    abandonMissingModelOperation(message.id);
    setModelChoice(null);
    setOperationError(null);
    void refreshModels();
    window.setTimeout(() => questionRef.current?.focus(), 0);
  }, [abandonMissingModelOperation, refreshModels]);

  useEffect(() => {
    if (!open) return;
    void refreshModels();
    questionRef.current?.focus();
    return () => {
      modelRequestRef.current += 1;
    };
  }, [open, documentId, refreshModels]);

  const unresolvedKey = unresolvedOperations
    .map((message) => `${message.id}:${message.model_operation_state}`)
    .join("|");
  useEffect(() => {
    if (!open || unresolvedOperations.length === 0) return;
    const poll = () => {
      for (const message of unresolvedOperations) void checkOperation(message);
    };
    poll();
    const timer = window.setInterval(poll, 5000);
    return () => window.clearInterval(timer);
  // The compact key prevents a fresh interval for unrelated thread renders.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, unresolvedKey, checkOperation]);

  const selectedModel = modelChoice
    ? models.find(
        (model) => model.id === modelChoice.provider_id && model.model_id === modelChoice.model_id,
      )
    : null;
  const selectedModelEligible = selectedModel ? isRouteEligible(selectedModel) : modelChoice === null;
  const modelOptions = useMemo(() => {
    const options = [
      { value: "default", label: "Default · deep tier" },
      ...models.map((model) => {
        const eligible = isRouteEligible(model);
        return {
          value: modelKey(model.id, model.model_id),
          label: eligible
            ? `${model.display_name} · ${model.model_id}`
            : `${model.display_name} · unavailable`,
          disabled: !eligible,
        };
      }),
    ];
    if (modelChoice && !selectedModel) {
      options.push({
        value: modelKey(modelChoice.provider_id, modelChoice.model_id),
        label: `${modelChoice.model_id} · no longer available`,
        disabled: true,
      });
    }
    return options;
  }, [models, modelChoice, selectedModel]);

  const selectModel = (value: string) => {
    if (value === "default") {
      setModelChoice(null);
      return;
    }
    const model = models.find((row) => modelKey(row.id, row.model_id) === value);
    if (!model || !isRouteEligible(model)) return;
    setModelChoice({ authority: "user_model", provider_id: model.id, model_id: model.model_id });
  };

  const ask = useCallback(async () => {
    const q = draft.trim();
    if (!q || pending) return;
    setError(null);
    setDraft("");
    // The recent tail of the active branch is the multi-turn context. Only
    // completed turns are carried (a pending/failed turn has no answer yet).
    const history = thread.messages
      .filter((m): m is TalkMessage & { answer: string } => m.answer !== null)
      .map((m) => ({ question: m.question, answer: m.answer }));
    const operationId = modelChoice ? `talk-${crypto.randomUUID()}` : undefined;
    const messageId = thread.startTurn(q, operationId, modelChoice ?? undefined);
    setPending(true);
    try {
      if (!selectedModelEligible) {
        throw new Error("That model is no longer available. Choose another model or use Default.");
      }
      const res = modelChoice && operationId
        ? await askBook(documentId, q, {
            history,
            researchTier: "deep",
            modelChoice,
            operationId,
          })
        : await askBook(documentId, q, { history, researchTier: "deep" });
      thread.completeTurn(
        messageId,
        res.answer,
        res.citations,
        res.grounded,
        res.answer_id,
        res.capture_status,
        res.model_receipt,
      );
    } catch (e: unknown) {
      if (e instanceof SelectedBookModelUnavailableError) {
        thread.failTurn(messageId);
        setModelChoice(null);
        setModels([]);
        void refreshModels();
        window.setTimeout(() => {
          selectorRef.current?.querySelector("button")?.focus();
        }, 0);
      } else if (modelChoice) {
        thread.setModelOperationState(messageId, "unknown");
      } else {
        thread.failTurn(messageId);
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  }, [draft, pending, thread, documentId, modelChoice, selectedModelEligible, refreshModels]);

  if (!open) {
    return (
      <button
        type="button"
        data-testid="talk-to-book-bookmark"
        onClick={() => setOpen(true)}
        title="Talk to this book"
        className="fixed bottom-6 right-6 z-30 flex min-h-11 items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-serif text-white shadow-lg hover:opacity-90"
      >
        Talk to this book
        {turnCount > 0 && (
          <span className="rounded-full bg-white/25 px-1.5 text-[11px] font-mono" data-testid="talk-turn-count">
            {turnCount}
          </span>
        )}
      </button>
    );
  }

  return (
    <aside
      data-testid="talk-to-book"
      className="fixed bottom-3 left-3 right-3 z-30 flex max-h-[75vh] flex-col rounded-lg border border-rule bg-ice-0 shadow-2xl dark:border-charcoal-1 dark:bg-charcoal-2 sm:bottom-6 sm:left-auto sm:right-6 sm:w-96"
      aria-label="Talk to this book"
    >
      <header className="flex items-center justify-between gap-2 border-b border-rule dark:border-charcoal-1 px-3 py-2">
        <span className="text-[13px] font-serif text-ink dark:text-bright truncate">
          Talk to “{title ?? "this book"}”
        </span>
        <div className="flex items-center gap-2 shrink-0">
          {turnCount > 0 && (
            <button
              type="button"
              onClick={thread.reset}
              disabled={selectedDispatchBlocked}
              className="min-h-11 px-2 text-[11px] font-mono text-shadow-1 hover:underline disabled:cursor-not-allowed disabled:opacity-50 dark:text-moonlight sm:min-h-0 sm:px-0"
              title={selectedDispatchBlocked
                ? "Resolve the pending model operation before clearing"
                : "Clear the conversation"}
            >
              clear
            </button>
          )}
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="min-h-11 min-w-11 text-[13px] font-mono text-ink hover:opacity-70 dark:text-bright sm:min-h-0 sm:min-w-0"
          >
            ✕
          </button>
        </div>
      </header>

      {/* Branch picker — the multi-turn thread can fork a tangent; the bookmark
          carries the active branch and lets the reader return to the trunk. */}
      {branchCount > 1 && (
        <div className="flex items-center gap-1.5 border-b border-rule dark:border-charcoal-1 px-3 py-1.5 overflow-x-auto" data-testid="talk-branches">
          {thread.state.branches.map((b, i) => (
            <button
              key={b.branch_id}
              type="button"
              onClick={() => thread.setActiveBranch(b.branch_id)}
              aria-pressed={b.branch_id === thread.activeBranchId}
              className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-mono ${
                b.branch_id === thread.activeBranchId
                  ? "bg-ink text-white"
                  : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4"
              }`}
            >
              {b.forked_from === null ? "main" : `tangent ${i}`}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2 flex flex-col gap-3">
        {thread.messages.length === 0 && (
          <p className="text-[13px] text-shadow-1 dark:text-moonlight italic">
            Ask anything about this book. Answers cite the pages they come from —
            click a citation to jump there.
          </p>
        )}
        {thread.messages.map((m) => (
          <div key={m.id}>
            <TalkMessageView
              message={m}
              modelReceipt={m.model_receipt}
              onJumpToPage={onJumpToPage}
              onBranch={() => thread.branchFrom(m.id)}
              onJudged={(verdict) => thread.setJudgment(m.id, verdict)}
              documentId={documentId}
            />
            {m.answer === null && m.operation_id && m.model_operation_state && (
              <div className="mt-2 rounded-md border border-sun-deep/40 bg-sun/10 p-2" role="status" aria-live="polite">
                <p className="text-[12px] text-ink dark:text-bright">
                  {m.model_operation_state === "prepared"
                    ? "This model request is reserved but not sent. Release it before retrying."
                    : m.model_operation_state === "settlement_pending"
                      ? "The provider call completed, but settlement is pending. Reconcile it; do not retry."
                      : m.model_operation_state === "settled"
                        ? "The operation settled, but its answer response was lost. An administrator may need to recover the answer."
                        : "The provider outcome is not confirmed. Do not retry this selected-model request."}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <LemonButton size="sm" className="min-h-11 sm:min-h-7" onClick={() => void checkOperation(m)}>
                    Check status
                  </LemonButton>
                  {m.model_operation_state === "prepared" ? (
                    <LemonButton size="sm" className="min-h-11 sm:min-h-7" onClick={() => void checkOperation(m, "cancel")}>
                      Release reservation
                    </LemonButton>
                  ) : m.model_operation_state !== "settled" && (
                    <LemonButton size="sm" className="min-h-11 sm:min-h-7" onClick={() => void checkOperation(m, "reconcile")}>
                      Reconcile
                    </LemonButton>
                  )}
                  {(m.operation_not_found_checks ?? 0) >= 2 &&
                    (m.model_operation_state === "unknown" || m.model_operation_state === "requesting") && (
                    <LemonButton
                      size="sm"
                      variant="danger"
                      className="min-h-11 sm:min-h-7"
                      onClick={() => abandonMissingOperation(m)}
                    >
                      Abandon unsent request
                    </LemonButton>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {pending && (
          <p className="text-[12px] text-shadow-1 dark:text-moonlight italic" role="status">
            Reading the book…
          </p>
        )}
        {error && (
          <p className="text-[13px] text-emperor" role="alert">
            {error}
          </p>
        )}
        {operationError && (
          <p className="text-[13px] text-emperor" role="alert">{operationError}</p>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask();
        }}
        className="flex flex-col gap-2 border-t border-rule px-3 py-2 dark:border-charcoal-1"
      >
        <div ref={selectorRef}>
          <label className="mb-1 block text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            Model for this answer
          </label>
          <LemonSelect<string>
            value={modelChoice ? modelKey(modelChoice.provider_id, modelChoice.model_id) : "default"}
            onChange={selectModel}
            options={modelOptions}
            sizing="sm"
            fullWidth
            className="[&_button]:min-h-11 sm:[&_button]:min-h-7"
            aria-label="Model for this answer"
          />
          <p className="mt-1 text-[10px] font-mono text-shadow-1 dark:text-moonlight" aria-live="polite">
            {modelsState === "loading" && "Loading your models…"}
            {modelsState === "failed" && "Your models couldn’t load. Default is still available."}
            {modelChoice && selectedModelEligible && `Requested: ${selectedModel?.display_name} · ${modelChoice.model_id}`}
            {modelChoice && !selectedModelEligible && "This selection is unavailable. Choose another model or Default."}
            {!modelChoice && modelsState !== "loading" && "Uses the established deep research tier."}
            {modelChoice && selectedDispatchBlocked && "Resolve the pending model operation before starting another."}
          </p>
        </div>
        <div className="flex items-end gap-2">
          <textarea
            ref={questionRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about this book…"
            aria-label="Question for this book"
            rows={2}
            className="min-w-0 flex-1 resize-none rounded-md border border-rule bg-ice-1 px-2 py-1.5 text-[13px] text-ink outline-none dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void ask();
              }
            }}
          />
          <LemonButton className="min-h-11 sm:min-h-7" type="submit" size="sm" variant="primary" disabled={pending || !draft.trim() || !selectedModelEligible || Boolean(modelChoice && selectedDispatchBlocked)}>
            Ask
          </LemonButton>
        </div>
      </form>
    </aside>
  );
}

function TalkMessageView({
  message,
  modelReceipt,
  onJumpToPage,
  onBranch,
  onJudged,
  documentId,
}: {
  message: TalkMessage;
  modelReceipt?: BookModelReceipt | null;
  onJumpToPage: (pageIndex: number) => void;
  onBranch: () => void;
  onJudged: (verdict: "good" | "bad") => void;
  documentId: string;
}) {
  const [judging, setJudging] = useState<"good" | "bad" | null>(null);
  const [judgmentError, setJudgmentError] = useState(false);

  const judge = async (verdict: "good" | "bad") => {
    if (!message.answer_id || judging || message.judgment) return;
    setJudging(verdict);
    setJudgmentError(false);
    try {
      await judgeBookAnswer(documentId, message.answer_id, verdict);
      onJudged(verdict);
    } catch {
      setJudgmentError(true);
    } finally {
      setJudging(null);
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      {/* The reader's question — visibly user-sourced. */}
      <p className="text-[13px] font-serif text-ink dark:text-bright">
        <span className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-0.5">
          you
        </span>
        {message.question}
      </p>
      {message.answer !== null && (
        <div className="rounded-md bg-ice-2 dark:bg-charcoal-1 px-2.5 py-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-0.5">
            the book
          </span>
          <p className="text-[13px] text-ink dark:text-bright whitespace-pre-wrap leading-relaxed">
            {message.answer}
          </p>

          {modelReceipt?.actual_provider_id && modelReceipt.actual_model_id && (
            <p className="mt-1 text-[10px] font-mono text-shadow-1 dark:text-moonlight" data-testid="talk-model-receipt">
              Used {modelReceipt.actual_provider_id} · {modelReceipt.actual_model_id}
            </p>
          )}

          {message.answer_id && (
            <div className="mt-2 flex items-center gap-2" aria-label="Rate this answer">
              {message.judgment ? (
                <span className="text-[11px] font-mono text-shadow-1 dark:text-moonlight" role="status">
                  Marked {message.judgment}
                </span>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => void judge("good")}
                    disabled={judging !== null}
                    className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright disabled:opacity-50"
                    aria-label="Mark answer good"
                  >
                    {judging === "good" ? "Saving…" : "Good"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void judge("bad")}
                    disabled={judging !== null}
                    className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:text-emperor disabled:opacity-50"
                    aria-label="Mark answer bad"
                  >
                    {judging === "bad" ? "Saving…" : "Bad"}
                  </button>
                </>
              )}
              {judgmentError && (
                <span className="text-[11px] text-emperor" role="alert">Couldn’t save judgment.</span>
              )}
            </div>
          )}
          {message.capture_unavailable && (
            <p className="mt-2 text-[11px] text-sun-deep dark:text-sun" role="status">
              Answer delivered, but rating is unavailable because its evidence record could not be saved.
            </p>
          )}

          {!message.grounded && (
            <p className="mt-1 text-[12px] text-sun-deep dark:text-sun italic">
              No readable passages backed this — it isn’t grounded in the book’s text.
            </p>
          )}

          {/* Page-level citations → jump into the SPR-07 reader. An unresolved
              page is shown honestly as "open the book", never a fake page. */}
          {message.citations.length > 0 && (
            <ul className="mt-1.5 flex flex-wrap gap-1" aria-label="Citations">
              {message.citations.map((c) => (
                <CitationChip key={c.chunk_id} citation={c} onJumpToPage={onJumpToPage} />
              ))}
            </ul>
          )}

          <div className="mt-2 flex items-center gap-2">
            {/* TTS via the SPR-14 shared service — reads THIS answer aloud. The
                answer is model-generated prose with no withheld §9.0 chunk
                (the gate already excluded any), so no chunkId guard is needed
                here; ReadAloud still labels it model-sourced. */}
            <ReadAloud text={message.answer} label="🔊 Read aloud" />
            <button
              type="button"
              onClick={onBranch}
              className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
              title="Explore a tangent from here"
            >
              ↳ what about that?
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CitationChip({
  citation,
  onJumpToPage,
}: {
  citation: BookCitation;
  onJumpToPage: (pageIndex: number) => void;
}) {
  const resolved = citation.page_resolved && citation.page_index !== null;
  if (resolved) {
    return (
      <li>
        <button
          type="button"
          onClick={() => onJumpToPage(citation.page_index as number)}
          title={citation.snippet}
          className="rounded bg-aurora/15 text-aurora-deep dark:text-aurora px-1.5 py-0.5 text-[11px] font-mono hover:bg-aurora/25"
        >
          p.{(citation.page_index as number) + 1}
        </button>
      </li>
    );
  }
  // Unresolved page — honest label, no jump (we don't invent a page).
  return (
    <li>
      <span
        title={citation.snippet}
        className="rounded bg-ice-3 dark:bg-charcoal-1 text-shadow-1 dark:text-moonlight px-1.5 py-0.5 text-[11px] font-mono italic"
      >
        in the book (page not pinpointed)
      </span>
    </li>
  );
}
