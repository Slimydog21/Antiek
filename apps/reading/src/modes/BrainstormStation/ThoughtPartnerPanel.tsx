/**
 * BrainstormStation thought-partner pane (master-spec §4.5 Surface E).
 *
 * Replaces the Sprint-17 CTA placeholder: this panel is a real one-shot
 * round-trip to ``POST /thought-partner`` — the SAME role + endpoint the
 * AISidecar and FloatMenu Dialogue already use. Selected parked questions
 * seed the composer via ``antiek:thought-partner:seed`` (BrainstormStation
 * dispatches on select). No new product surface; completes the active
 * component of Surface E beside the watch-for-later parking lot.
 *
 * Cite: docs/master-product-spec.md §4.5; roles/thought_partner/program.md;
 * docs/anti-ek-vision-map-2026-09-17.md pillar 2 (daily loop).
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../../lib/api";
import { WernerThinking } from "../../brand/werner/animated";
import ContextPicker from "../../components/ai/ContextPicker";
import {
  parseAssistantReply,
  dispatchAiAction,
  workspaceContextPrompt,
} from "../../components/ai/aiActions";
import type { DispatchedAction } from "../../components/ai/aiActions";
import {
  THOUGHT_PARTNER_SEED_EVENT,
  type ThoughtPartnerSeedDetail,
} from "../../components/ai/thoughtPartnerSeed";

export { THOUGHT_PARTNER_SEED_EVENT, type ThoughtPartnerSeedDetail };

interface ThoughtPartnerReply {
  shape: "CHALLENGE" | "SYNTHESIS" | "EXTENSION";
  text: string;
}

function normalizeShape(raw: unknown): ThoughtPartnerReply["shape"] {
  const s = String(raw ?? "SYNTHESIS").toUpperCase();
  if (s === "CHALLENGE" || s === "EXTENSION") return s;
  return "SYNTHESIS";
}

export default function ThoughtPartnerPanel() {
  const [draft, setDraft] = useState("");
  const [composedContext, setComposedContext] = useState("");
  const [seedLabel, setSeedLabel] = useState<string | null>(null);
  const [reply, setReply] = useState<ThoughtPartnerReply | null>(null);
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
        setReply(null);
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
      // Focus after seed so Faisal can refine before Send.
      queueMicrotask(() => inputRef.current?.focus());
    };
    window.addEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
    return () => window.removeEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
  }, []);

  const send = useCallback(async () => {
    const prompt = draft.trim();
    if (!prompt || pending) return;
    setPending(true);
    setError(null);
    setReply(null);
    try {
      const resp = await apiFetch("/thought-partner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          system_context: composedContext.trim()
            ? composedContext
            : workspaceContextPrompt(),
        }),
      });
      if (!resp.ok) {
        setReply({
          shape: "CHALLENGE",
          text: `Thought-partner unavailable (HTTP ${resp.status}).`,
        });
        return;
      }
      const data = await resp.json();
      const rawText: string = data.text ?? "";
      const { prose, actions } = parseAssistantReply(rawText);
      setReply({
        shape: normalizeShape(data.shape),
        text: prose || rawText,
      });
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
    } finally {
      setPending(false);
    }
  }, [composedContext, draft, pending]);

  return (
    <div
      className="h-full overflow-y-auto bg-ice-1 dark:bg-charcoal-2 p-4 space-y-3"
      data-testid="thought-partner-panel"
    >
      <header className="space-y-1">
        <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Thought partner
        </h3>
        <p className="text-[11px] font-serif text-ink-mute dark:text-moonlight leading-relaxed">
          Challenge, synthesize, or extend notes and parked questions — same
          role as ⌘/ sidecar and in-book Dialogue.
        </p>
      </header>

      {seedLabel ? (
        <p
          className="text-[10px] font-mono text-shadow-1 dark:text-moonlight"
          data-testid="thought-partner-seed-label"
        >
          Seeded from {seedLabel}
        </p>
      ) : null}

      <ContextPicker onContextChange={setComposedContext} />

      <textarea
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="Talk to your notes — what should we challenge or extend?"
        rows={4}
        aria-label="Thought partner prompt"
        className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y bg-ice-0 dark:bg-charcoal-3"
      />

      <button
        type="button"
        onClick={() => void send()}
        disabled={pending || !draft.trim()}
        className="w-full px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {pending ? (
          <>
            <WernerThinking size={20} label="" />
            <span>Thinking…</span>
          </>
        ) : (
          "Send"
        )}
      </button>

      {error ? (
        <p className="text-[11px] text-red-700 dark:text-red-300" role="alert">
          {error}
        </p>
      ) : null}

      {reply ? (
        <div
          className="border border-rule dark:border-charcoal-1 rounded p-2 space-y-1.5 bg-ice-0 dark:bg-charcoal-3"
          data-testid="thought-partner-reply"
        >
          <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
            {reply.shape}
          </p>
          <p className="text-xs text-ink dark:text-bright whitespace-pre-wrap font-serif leading-relaxed">
            {reply.text}
          </p>
        </div>
      ) : null}

      {aiLog.length > 0 ? (
        <ul className="space-y-1" aria-label="AI actions">
          {aiLog.map((rec, idx) => (
            <li
              key={`${rec.at}-${idx}`}
              className="text-[11px] border border-rule dark:border-charcoal-1 rounded px-2 py-1"
            >
              {rec.label}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
