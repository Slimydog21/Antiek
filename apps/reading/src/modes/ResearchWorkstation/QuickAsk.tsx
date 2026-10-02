import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import LemonSelect from "../../components/lemon/LemonSelect";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import { useAuth } from "../../lib/auth";
import {
  fetchQuickAskModels, fetchQuickAskRecent, QuickAskError, quoteQuickAsk, sendQuickAsk,
  type QuickAskInput, type QuickAskModel, type QuickAskQuote, type QuickAskRecentOperation,
  type QuickAskResult,
} from "../../api/quickAsk";
import type { UserModelChoice } from "../../lib/api";

interface ModelOption {
  key: string;
  label: string;
  choice: UserModelChoice;
}

type Phase =
  | { kind: "editing" }
  | { kind: "quoting" }
  | { kind: "quoted"; quote: QuickAskQuote }
  | { kind: "sending"; quote: QuickAskQuote }
  | { kind: "answered"; result: QuickAskResult }
  | { kind: "unknown"; operationId: string }
  | { kind: "error"; message: string };

const PENDING_SEND_KEY = "antiek.quick-ask.pending-send.session.v1";

function pendingKey(ownerId: string): string {
  return `${PENDING_SEND_KEY}:${encodeURIComponent(ownerId)}`;
}

function pendingSend(ownerId: string): string | null {
  try {
    const value = window.sessionStorage.getItem(pendingKey(ownerId));
    return value && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value)
      ? value : null;
  } catch {
    return null;
  }
}

function preservePendingSend(ownerId: string, operationId: string): boolean {
  try {
    window.sessionStorage.setItem(pendingKey(ownerId), operationId);
    return window.sessionStorage.getItem(pendingKey(ownerId)) === operationId;
  } catch {
    return false;
  }
}

function clearPendingSend(ownerId: string): void {
  try { window.sessionStorage.removeItem(pendingKey(ownerId)); } catch { /* read-only storage */ }
}

function modelOptions(models: QuickAskModel[]): ModelOption[] {
  return models.map((row) => ({
    key: `${row.provider_id}\u0000${row.model_id}`,
    label: `${row.display_name} · ${row.model_id}`,
    choice: { authority: "user_model", provider_id: row.provider_id, model_id: row.model_id },
  }));
}

function failureMessage(error: unknown): string {
  if (!(error instanceof QuickAskError)) return "Quick Ask is unavailable. No automatic retry was made.";
  switch (error.reason) {
    case "signed_owner_required":
      return "Sign in to use your saved model.";
    case "quick_ask_model_unavailable":
      return "That saved model is unavailable. Check its key and current model in Settings.";
    case "quick_ask_quote_changed":
      return "The model or price changed. Get a fresh estimate before sending.";
    case "quick_ask_operation_conflict":
      return "This request ID already belongs to a different question or model. Start a new question.";
    case "quick_ask_request_invalid":
    case "quick_ask_json_required":
      return "Check the question and model, then get a fresh estimate.";
    case "quick_ask_models_unavailable":
      return "Couldn’t check eligible models right now. No model request was sent.";
    case "charge_unknown":
      return "Charge unknown. Check your provider dashboard before making another request. Antiek did not retry.";
    case "quick_ask_unavailable":
      return "Quick Ask is unavailable. No automatic retry was made.";
    default: {
      const exhaustive: never = error.reason;
      return exhaustive;
    }
  }
}

function receiptLabel(result: QuickAskResult): string {
  switch (result.usage_basis) {
    case "provider_reported_tokens_priced_locally":
      return `Provider-reported ${result.input_tokens ?? "?"} input / ${result.output_tokens ?? "?"} output tokens · Antiek-estimated cost $${result.estimated_cost_usd ?? "unknown"}. The provider's final charge is not reconciled.`;
    case "prior_receipt":
      return `Prior answer restored · Antiek-estimated cost $${result.estimated_cost_usd ?? "unknown"}. This is not the provider's final charge. Token counts were not stored; no new model request was sent.`;
    case "charge_unknown":
      return "Answer received, charge unknown. Check your provider dashboard before making another request. Antiek did not retry.";
    default: {
      const exhaustive: never = result.usage_basis;
      return exhaustive;
    }
  }
}

function QuickAskRecent({ refreshSignal }: { refreshSignal: number }) {
  const [recent, setRecent] = useState<QuickAskRecentOperation[]>([]);
  const [recentState, setRecentState] = useState<"loading" | "ready" | "error">("loading");
  const [openedRecentId, setOpenedRecentId] = useState<string | null>(null);
  const revision = useRef(0);
  const openedRecent = recent.find((row) => row.operation_id === openedRecentId) ?? null;

  const loadRecent = useCallback(async () => {
    const started = ++revision.current;
    setRecentState("loading");
    try {
      const operations = await fetchQuickAskRecent();
      if (started !== revision.current) return;
      setRecent(operations);
      setRecentState("ready");
    } catch {
      if (started !== revision.current) return;
      setRecentState("error");
    }
  }, []);

  useEffect(() => {
    void loadRecent();
    return () => { revision.current += 1; };
  }, [loadRecent, refreshSignal]);

  return (
    <section aria-label="Recent Quick Ask receipts" className="border-t border-rule dark:border-charcoal-1 pt-4 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-serif text-base text-ink dark:text-bright">Recent requests</h3>
        <LemonButton variant="secondary" disabled={recentState === "loading"} onClick={() => void loadRecent()}>
          Refresh receipts
        </LemonButton>
      </div>
      <p className="font-serif text-xs text-shadow-1 dark:text-moonlight">
        Up to ten recent receipts from your account. Reading or refreshing them sends no model request.
      </p>
      {recentState === "loading" && <p role="status">Checking recent requests…</p>}
      {recentState === "error" && (
        <p role="status">Recent receipts are unavailable. This does not establish whether a pending request was charged.</p>
      )}
      {recentState === "ready" && recent.length === 0 && (
        <p role="status">No recent request receipt is available. A pending request may still have reached the provider.</p>
      )}
      {recent.length > 0 && (
        <ul className="space-y-2">
          {recent.map((row) => (
            <li key={row.operation_id} className="border border-rule dark:border-charcoal-1 p-3 space-y-1">
              <p className="font-mono text-xs text-shadow-1 dark:text-moonlight">
                {new Date(row.created_at).toLocaleString()} · request {row.operation_id}
              </p>
              {row.status === "answered" ? (
                <LemonButton variant="secondary" onClick={() => setOpenedRecentId(
                  openedRecentId === row.operation_id ? null : row.operation_id,
                )}>
                  {openedRecentId === row.operation_id ? "Hide stored answer" : "View stored answer"}
                </LemonButton>
              ) : (
                <p className="font-serif text-sm text-emperor">
                  Charge unknown; no stored answer is available. Check your provider dashboard before making another request.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      {openedRecent?.status === "answered" && (
        <article aria-label="Stored Quick Ask answer" className="space-y-2 border-l-2 border-rule dark:border-charcoal-1 pl-3">
          <p className="font-serif text-sm text-ink dark:text-bright whitespace-pre-wrap">{openedRecent.result.answer}</p>
          {openedRecent.result.incomplete && (
            <p className="font-serif text-xs text-emperor">This stored answer may be incomplete. No follow-up model request was made.</p>
          )}
          <p className="font-mono text-xs text-shadow-1 dark:text-moonlight">{receiptLabel(openedRecent.result)}</p>
          {openedRecent.result.reported_usage_estimate_exceeds_quote && (
            <p className="font-mono text-xs text-emperor" role="alert">
              The provider-reported usage priced above the quote. The quote was an estimate; check your provider dashboard for the final charge.
            </p>
          )}
        </article>
      )}
    </section>
  );
}

function QuickAskOwner({ ownerId, onPaidRequestInFlight }: {
  ownerId: string;
  onPaidRequestInFlight?: (pending: boolean) => void;
}) {
  const [question, setQuestion] = useState("");
  const [models, setModels] = useState<QuickAskModel[]>([]);
  const [modelsState, setModelsState] = useState<"loading" | "ready" | "error">("loading");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [operationId, setOperationId] = useState(() => crypto.randomUUID());
  const [phase, setPhase] = useState<Phase>(() => {
    const previous = pendingSend(ownerId);
    return previous ? { kind: "unknown", operationId: previous } : { kind: "editing" };
  });
  const [recentRefresh, setRecentRefresh] = useState(0);
  const revision = useRef(0);
  const mounted = useRef(false);

  const options = useMemo(() => modelOptions(models), [models]);
  const selected = options.find((option) => option.key === selectedKey) ?? null;

  useEffect(() => {
    let live = true;
    void fetchQuickAskModels().then(
      (inventory) => {
        if (!live) return;
        setModels(inventory);
        setModelsState("ready");
      },
      () => {
        if (!live) return;
        setModelsState("error");
      },
    );
    return () => { live = false; };
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      onPaidRequestInFlight?.(false);
    };
  }, [onPaidRequestInFlight]);

  const resetQuote = () => {
    revision.current += 1;
    setPhase({ kind: "editing" });
    setOperationId(crypto.randomUUID());
  };

  const input = (): QuickAskInput | null => {
    if (!selected || question.trim().length < 3) return null;
    return { question: question.trim(), operation_id: operationId, model_choice: selected.choice };
  };

  const quote = async () => {
    const request = input();
    if (!request) return;
    const quotedRevision = revision.current;
    setPhase({ kind: "quoting" });
    try {
      const next = await quoteQuickAsk(request);
      if (quotedRevision === revision.current) setPhase({ kind: "quoted", quote: next });
    } catch (error) {
      if (quotedRevision === revision.current) {
        setPhase({ kind: "error", message: failureMessage(error) });
      }
    }
  };

  const send = async (prepared: QuickAskQuote) => {
    const request = input();
    if (!request) return;
    if (!preservePendingSend(ownerId, operationId)) {
      setPhase({ kind: "error", message: "This browser cannot preserve the request ID. No model request was sent." });
      return;
    }
    onPaidRequestInFlight?.(true);
    setPhase({ kind: "sending", quote: prepared });
    try {
      const result = await sendQuickAsk(request, prepared);
      if (mounted.current && result.usage_basis !== "charge_unknown") clearPendingSend(ownerId);
      setPhase({ kind: "answered", result });
    } catch {
      // After POST, even a structured 503 can follow provider I/O. The
      // persisted operation must stay terminal until the owner releases it.
      setPhase({ kind: "unknown", operationId });
    } finally {
      if (mounted.current) setRecentRefresh((value) => value + 1);
      if (mounted.current) onPaidRequestInFlight?.(false);
    }
  };

  const active = phase.kind === "quoting" || phase.kind === "sending";
  const terminal = phase.kind === "answered" || phase.kind === "unknown";

  return (
    <section aria-labelledby="quick-ask-heading" className="space-y-4">
      <div>
        <h2 id="quick-ask-heading" className="font-serif text-xl text-ink dark:text-bright">
          Quick Ask
        </h2>
        <p className="font-serif text-sm text-shadow-1 dark:text-moonlight leading-relaxed">
          One Antiek model request for an exploratory answer. This question-only mode does not search your corpus or run the multi-step research chain.
        </p>
      </div>

      {terminal ? (
        <div className="space-y-3">
          {phase.kind === "answered" && (
            <>
              <article aria-label="Quick Ask answer" className="font-serif text-base leading-relaxed whitespace-pre-wrap text-ink dark:text-bright max-w-prose">
                {phase.result.answer}
              </article>
              {phase.result.incomplete && (
                <p className="text-sm font-serif text-emperor" role="status">
                  This answer may be incomplete: the model stopped at its output limit or filtered the content. Antiek made no follow-up request.
                </p>
              )}
              <p className={phase.result.usage_basis === "charge_unknown"
                ? "text-xs font-mono text-emperor" : "text-xs font-mono text-shadow-1 dark:text-moonlight"} role="status">
                {receiptLabel(phase.result)}
              </p>
              {phase.result.reported_usage_estimate_exceeds_quote && (
                <p className="text-xs font-mono text-emperor" role="alert">
                  The provider-reported usage priced above the quote. The quote was an estimate; check your provider dashboard for the final charge.
                </p>
              )}
              <p className="text-xxs font-mono text-ink-mute dark:text-moonlight break-all">
                {phase.result.provider_id} · {phase.result.model_id} · request {phase.result.operation_id}
              </p>
            </>
          )}
          {phase.kind === "unknown" && (
            <p className="text-sm font-serif text-emperor" role="alert">
              Charge unknown. Check your provider dashboard before making another request. Antiek did not retry. Request {phase.operationId}.
            </p>
          )}
          <LemonButton variant="secondary" onClick={() => {
            clearPendingSend(ownerId);
            setQuestion("");
            resetQuote();
          }}>
            {phase.kind === "unknown" ||
            (phase.kind === "answered" && phase.result.usage_basis === "charge_unknown")
              ? "I checked my provider · new question" : "New question"}
          </LemonButton>
        </div>
      ) : (
        <div className="space-y-3">
          <LemonTextarea
            value={question}
            onChange={(event) => { setQuestion(event.target.value); resetQuote(); }}
            placeholder="What do you want to understand?"
            minRows={3}
            maxRows={8}
            className="font-serif text-base leading-relaxed"
            aria-label="Quick Ask question"
            disabled={phase.kind === "sending"}
          />
          <div className="space-y-1">
            <p className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              Your model
            </p>
            <LemonSelect
              value={selectedKey}
              onChange={(value) => { if (active) return; setSelectedKey(value); resetQuote(); }}
              options={options.map((option) => ({ value: option.key, label: option.label }))}
              placeholder={modelsState === "loading" ? "Checking saved models…" : "Choose a saved current model"}
              aria-label="Quick Ask model"
              fullWidth
            />
          </div>
          {modelsState !== "loading" && options.length === 0 && (
            <p className="font-serif text-sm text-shadow-1 dark:text-moonlight" role="status">
              {modelsState === "error" ? "Couldn’t check your saved models." : "No current saved model is ready for this route."}{" "}
              <Link className="underline text-ink dark:text-bright" to="/settings">Connect a model in Settings</Link>.
            </p>
          )}
          {phase.kind === "error" && <p role="alert" className="text-sm font-serif text-emperor">{phase.message}</p>}
          {phase.kind === "quoted" || phase.kind === "sending" ? (
            <div className="border-t border-rule dark:border-charcoal-1 pt-3 space-y-2">
              <p className="font-mono text-sm text-ink dark:text-bright">
                Estimated request cost: ${phase.quote.estimate_usd}. It may be exceeded.
              </p>
              <p className="font-mono text-xs text-shadow-1 dark:text-moonlight">
                {phase.quote.model_id} · up to {phase.quote.max_output_tokens} output tokens · {phase.quote.price_snapshot}
              </p>
              <p className="font-mono text-xxs text-shadow-1 dark:text-moonlight break-all">
                Price source: {phase.quote.price_source}
              </p>
              <p role="alert" className="font-serif text-sm text-emperor">
                {phase.quote.warning}
              </p>
              <LemonButton variant="primary" disabled={active} onClick={() => void send(phase.quote)}>
                {active ? "Sending…" : "Send one request"}
              </LemonButton>
            </div>
          ) : (
            <LemonButton variant="primary" disabled={active || !selected || question.trim().length < 3}
              onClick={() => void quote()}>
              {phase.kind === "quoting" ? "Estimating…" : "Review estimate"}
            </LemonButton>
          )}
        </div>
      )}
      <QuickAskRecent refreshSignal={recentRefresh} />
    </section>
  );
}

export default function QuickAsk({ onPaidRequestInFlight }: {
  onPaidRequestInFlight?: (pending: boolean) => void;
}) {
  const { state } = useAuth();
  if (state.status !== "authenticated") {
    return <p role="status">Sign in to use your saved model.</p>;
  }
  const ownerScope = state.identity.user_id === "__operator__"
    ? `${state.identity.user_id}:${state.identity.email?.trim().toLowerCase() ?? ""}`
    : state.identity.user_id;
  return <QuickAskOwner key={ownerScope} ownerId={ownerScope}
    onPaidRequestInFlight={onPaidRequestInFlight} />;
}
