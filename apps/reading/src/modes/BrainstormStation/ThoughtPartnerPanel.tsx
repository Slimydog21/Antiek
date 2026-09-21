/**
 * BrainstormStation thought-partner pane (master-spec §4.5 Surface E).
 *
 * Multi-turn ``POST /thought-partner`` (session thread) — same role +
 * endpoint as AISidecar / FloatMenu Dialogue. Parked questions seed via
 * ``antiek:thought-partner:seed``. Lego insight slotting: graph blocks
 * drag (or click-slot) from ``InsightLegoShelf`` into the focus tray;
 * send merges them through ``POST /compose-context`` (@insight) into
 * ``system_context`` — same CK-4 / §9.0 path as ContextPicker.
 *
 * Cite: docs/master-product-spec.md §4.5; roles/thought_partner/program.md;
 * docs/decisions/tp-surface-e-real-panel-2026-09-18.md residual Lego.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  historyPayload,
  normalizeThoughtPartnerShape,
  useThoughtPartnerThread,
} from "../../hooks/useThoughtPartnerThread";

import { apiFetch, composeContext } from "../../lib/api";
import { WernerThinking } from "../../brand/werner/animated";
import { LemonButton } from "../../components/lemon/LemonButton";
import ContextPicker from "../../components/ai/ContextPicker";
import {
  parseAssistantReply,
  dispatchAiAction,
} from "../../components/ai/aiActions";
import type { DispatchedAction } from "../../components/ai/aiActions";
import {
  THOUGHT_PARTNER_SEED_EVENT,
  type ThoughtPartnerSeedDetail,
  composeThoughtPartnerSystemContext,
} from "../../components/ai/thoughtPartnerSeed";
import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import InsightLegoShelf from "./InsightLegoShelf";
import {
  mergeSlottedSystemContext,
  parsePaletteDrag,
  slotInsight,
  slottedToContextItems,
  unslotInsight,
} from "./insightLegoSlot";

export { THOUGHT_PARTNER_SEED_EVENT, type ThoughtPartnerSeedDetail };

export default function ThoughtPartnerPanel() {
  const [draft, setDraft] = useState("");
  const [composedContext, setComposedContext] = useState("");
  const [seedLabel, setSeedLabel] = useState<string | null>(null);
  const [slotted, setSlotted] = useState<PaletteDragPayload[]>([]);
  const [dropActive, setDropActive] = useState(false);
  const thread = useThoughtPartnerThread();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiLog, setAiLog] = useState<DispatchedAction[]>([]);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const onSeed = (ev: Event) => {
      const detail = (ev as CustomEvent<ThoughtPartnerSeedDetail>).detail;
      if (!detail) return;
      if (typeof detail.prompt === "string" && detail.prompt.trim()) {
        setDraft(detail.prompt.trim());
        setError(null);
      }
      if (typeof detail.system_context === "string") {
        setComposedContext(detail.system_context);
      }
      setSeedLabel(
        typeof detail.source_label === "string" && detail.source_label.trim()
          ? detail.source_label.trim()
          : null,
      );
      queueMicrotask(() => inputRef.current?.focus());
    };
    window.addEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
    return () => window.removeEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
  }, []);

  const addSlot = useCallback((payload: PaletteDragPayload) => {
    setSlotted((prev) => slotInsight(prev, payload));
  }, []);

  const onDragOverFocus = useCallback((e: React.DragEvent) => {
    if (![...e.dataTransfer.types].includes("application/x-antiek-block")) {
      // Still allow — some browsers hide custom MIME until drop.
    }
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setDropActive(true);
  }, []);

  const onDragLeaveFocus = useCallback((e: React.DragEvent) => {
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDropActive(false);
  }, []);

  const onDropFocus = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDropActive(false);
      const payload = parsePaletteDrag(e.dataTransfer);
      if (payload) addSlot(payload);
    },
    [addSlot],
  );

  const send = useCallback(async () => {
    const prompt = draft.trim();
    if (!prompt || pending) return;
    setPending(true);
    setError(null);
    const history = historyPayload(thread.messages);
    const messageId = thread.startTurn(prompt);
    setDraft("");
    try {
      let insightCtx = "";
      const items = slottedToContextItems(slotted);
      if (items.length > 0) {
        try {
          const composed = await composeContext({ items });
          insightCtx = composed.system_context ?? "";
        } catch {
          insightCtx = slotted
            .map((s) => `@insight[${s.block_id}] ${s.label}`)
            .join("\n");
        }
      }
      const merged = mergeSlottedSystemContext(
        insightCtx,
        composedContext.trim() ? composedContext : null,
      );
      const resp = await apiFetch("/thought-partner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          history,
          system_context: composeThoughtPartnerSystemContext(
            merged.trim() ? merged : null,
          ),
        }),
      });
      if (!resp.ok) {
        thread.failTurn(
          messageId,
          `Thought-partner unavailable (HTTP ${resp.status}).`,
        );
        return;
      }
      const data = await resp.json();
      const rawText: string = data.text ?? "";
      const { prose, actions } = parseAssistantReply(rawText);
      thread.completeTurn(
        messageId,
        prose || rawText,
        normalizeThoughtPartnerShape(data.shape),
      );
      if (actions.length > 0) {
        const applied: DispatchedAction[] = [];
        for (const action of actions) {
          const rec = dispatchAiAction(action);
          if (rec) applied.push(rec);
        }
        if (applied.length) setAiLog((prev) => [...applied, ...prev]);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      thread.failTurn(messageId, msg);
    } finally {
      setPending(false);
    }
  }, [composedContext, draft, pending, slotted, thread]);

  return (
    <div
      className="h-full overflow-y-auto bg-ice-1 dark:bg-charcoal-2 p-4 space-y-3"
      data-testid="thought-partner-panel"
    >
      <header className="space-y-1">
        <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Thought partner
        </h3>
        <p className="text-xs font-serif text-ink-mute dark:text-moonlight leading-relaxed">
          Slot insights like Legos into focus, then challenge / synthesize /
          extend — same role as ⌘/ sidecar and in-book Dialogue.
        </p>
      </header>

      {seedLabel ? (
        <p
          className="text-xxs font-mono text-shadow-1 dark:text-moonlight"
          data-testid="thought-partner-seed-label"
        >
          Seeded from {seedLabel}
        </p>
      ) : null}

      <InsightLegoShelf onSlot={addSlot} />

      <div
        data-testid="thought-partner-focus-tray"
        onDragOver={onDragOverFocus}
        onDragLeave={onDragLeaveFocus}
        onDrop={onDropFocus}
        className={
          "min-h-[3.5rem] border border-dashed rounded p-2 space-y-1.5 transition-colors " +
          (dropActive
            ? "border-sun-deep bg-sun-deep/10"
            : "border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2")
        }
      >
        <p className="text-xxs font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
          Focus tray
          {slotted.length ? ` · ${slotted.length}` : ""}
        </p>
        {slotted.length === 0 ? (
          <p className="text-xs text-ink-mute dark:text-moonlight italic">
            Drop insight Legos here (or tap + on the shelf).
          </p>
        ) : (
          <ul className="flex flex-wrap gap-1" aria-label="Slotted insights">
            {slotted.map((s) => (
              <li
                key={s.block_id}
                className="inline-flex items-center gap-1 max-w-full px-1.5 py-0.5 rounded border border-sun-deep/40 bg-sun-deep/10 text-xxs font-serif text-ink dark:text-bright"
                data-testid="slotted-insight-chip"
              >
                <span className="truncate" title={s.label}>
                  {s.label}
                </span>
                <button
                  type="button"
                  aria-label={`Remove ${s.label}`}
                  className="font-mono text-ink-mute hover:text-emperor"
                  onClick={() =>
                    setSlotted((prev) => unslotInsight(prev, s.block_id))
                  }
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ContextPicker onContextChange={setComposedContext} />

      <textarea
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="Talk to your notes — what should we challenge or extend?"
        rows={4}
        aria-label="Thought partner prompt"
        className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y bg-ice-0 dark:bg-charcoal-2"
      />

      <LemonButton
        variant="primary"
        size="sm"
        fullWidth
        onClick={() => void send()}
        disabled={pending || !draft.trim()}
      >
        {pending ? (
          <>
            <WernerThinking size={20} label="" />
            <span>Thinking…</span>
          </>
        ) : (
          "Send"
        )}
      </LemonButton>

      {error ? (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}

      {thread.messages.length > 0 ? (
        <div className="space-y-2" data-testid="thought-partner-thread">
          <div className="flex items-center justify-between">
            <p className="text-xxs font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              Thread · {thread.messages.length}
            </p>
            <button
              type="button"
              className="text-xxs font-mono underline text-ink-mute"
              onClick={() => thread.clear()}
              data-testid="thought-partner-clear-thread"
            >
              Clear
            </button>
          </div>
          <ul className="space-y-2" aria-label="Thought partner thread">
            {thread.messages.map((m) => (
              <li
                key={m.id}
                className="border border-rule dark:border-charcoal-1 rounded p-2 space-y-1.5 bg-ice-0 dark:bg-charcoal-2"
                data-testid="thought-partner-turn"
              >
                <p className="text-xs font-serif text-ink-mute dark:text-moonlight">
                  You: {m.question}
                </p>
                {m.answer == null ? (
                  <p className="text-xs italic text-ink-mute" data-testid="thought-partner-pending">
                    Thinking…
                  </p>
                ) : (
                  <div data-testid="thought-partner-reply">
                    <p className="text-xxs font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                      {m.shape ?? "SYNTHESIS"}
                    </p>
                    <p className="text-xs text-ink dark:text-bright whitespace-pre-wrap font-serif leading-relaxed">
                      {m.answer}
                    </p>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {aiLog.length > 0 ? (
        <ul className="space-y-1" aria-label="AI actions">
          {aiLog.map((rec, idx) => (
            <li
              key={`${rec.at}-${idx}`}
              className="text-xs border border-rule dark:border-charcoal-1 rounded px-2 py-1"
            >
              {rec.label}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
