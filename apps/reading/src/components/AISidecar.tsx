import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../lib/api";
import { WernerThinking } from "../brand/werner/animated";
import { useReplyMode } from "../hooks/useReplyMode";
import { notifyThoughtPartnerReplyReceived } from "../werner";
import { AISIDECAR_PANEL_ID } from "../workspace/shortcuts";
import SpokenReply from "./SpokenReply";
import ContextPicker from "./ai/ContextPicker";
import {
  dispatchAiAction,
  parseAssistantReply,
  workspaceContextPrompt,
} from "./ai/aiActions";
import type { DispatchedAction } from "./ai/aiActions";

/**
 * Ubiquitous AI Sidecar (PostHog Wedge 4, master-spec §5.6 + §4.6).
 *
 * Always-available right-rail surface that follows the operator across
 * every mode. Per master-spec PostHog philosophy: 'transparent
 * intelligence, not magic' — the sidecar displays:
 *
 *   - The currently-selected substrate context (route + investigation_id
 *     where applicable)
 *   - Free-tier token usage vs the 5M cap (§13.5)
 *   - Recent dispatch decisions (which model was used + why)
 *   - A one-shot thought-partner input that posts to /thought-partner
 *
 * Collapses to a 32px rail when not in use; expands to 320px on
 * hover/focus. ESC closes; Cmd/Ctrl+J toggles (palette uses Cmd+K
 * to avoid collision).
 *
 * Per §13.3 privacy: the sidecar NEVER displays cross-user content;
 * everything shown is sourced from the user's own session.
 */

interface UsageSummary {
  free_tokens_consumed: number;
  free_tokens_remaining: number;
  record_count: number;
}

interface DispatchEvent {
  call_id: string;
  tier: string;
  provider: string;
  model: string;
  latency_ms: number;
  // The real DispatchCallPayload has no fallback_reason string — it carries
  // fallback_chain_index (0 = primary provider, >0 = a fallback rung was
  // used). Derive the warning marker from that so it actually fires on a
  // real fallback instead of being permanently dead.
  fell_back: boolean;
}

interface ThoughtPartnerReply {
  shape: "CHALLENGE" | "SYNTHESIS" | "EXTENSION";
  text: string;
}

export default function AISidecar() {
  // S8 refactor: when AISidecar is mounted as a PanelKind, the
  // workspace mounts/unmounts it directly — being mounted IS "open".
  // The legacy toggle paths (⌘J shortcut + custom event) now route
  // through workspace.open / workspace.close via the shortcut module
  // rather than flipping a local boolean. So no `open` state here.
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [recentCalls, setRecentCalls] = useState<DispatchEvent[]>([]);
  const [contextError, setContextError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");
  // CK-4: the operator's composed §9.0-aware context (from the @-context
  // picker). When non-empty it OVERRIDES the opaque workspaceContextPrompt()
  // so /thought-partner grounds on exactly what the operator @-selected.
  const [composedContext, setComposedContext] = useState<string>("");
  const [reply, setReply] = useState<ThoughtPartnerReply | null>(null);
  const [pending, setPending] = useState<boolean>(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const aliveRef = useRef(true);
  // Read SPR-07 — the rabbit hole answers in text OR audio per preference.
  const { mode: replyMode, setMode: setReplyMode } = useReplyMode();

  /**
   * Actions the AI has dispatched against this workspace. Each entry
   * is a side-effecting record with an `undo` handle; the operator
   * sees them as clickable pills + can reverse any action whose
   * reversal makes sense (close-what-was-opened, restore-mode, etc).
   *
   * The log is per-mount — closing + reopening the sidecar resets it.
   * Persisting the log would tempt undo on actions whose state has
   * already drifted; we keep it as a short transparency surface.
   */
  const [aiLog, setAiLog] = useState<DispatchedAction[]>([]);

  const period = useMemo_period();

  const reloadContext = useCallback(async () => {
    try {
      setContextError(null);
      const [u, t] = await Promise.all([
        apiFetch(`/billing/summary/__operator__/${period}`),
        apiFetch("/trajectory?limit=8"),
      ]);
      if (u?.ok) {
        const data = await u.json();
        setUsage({
          free_tokens_consumed: data.free_tokens_consumed ?? 0,
          free_tokens_remaining: data.free_tokens_remaining ?? 5_000_000,
          record_count: data.record_count ?? 0,
        });
      } else {
        setContextError(`Failed to load usage (HTTP ${u.status}).`);
      }
      if (t?.ok) {
        const data = await t.json();
        type RawDispatchEvent = {
          event_id?: string;
          action_type?: string;
          payload?: Record<string, unknown> & {
            call_id?: string;
            tier?: string;
            provider?: string;
            model?: string;
            latency_ms?: number;
            fallback_chain_index?: number;
          };
        };
        const events = (data.events ?? [])
          .filter((e: RawDispatchEvent) => e.action_type === "dispatch.call")
          .slice(0, 8)
          .map((e: RawDispatchEvent) => ({
            call_id: e.payload?.call_id ?? e.event_id ?? "",
            tier: e.payload?.tier ?? "?",
            provider: e.payload?.provider ?? "?",
            model: e.payload?.model ?? "?",
            latency_ms: e.payload?.latency_ms ?? 0,
            fell_back: (e.payload?.fallback_chain_index ?? 0) > 0,
          }));
        setRecentCalls(events);
      } else {
        setContextError(`Failed to load recent dispatch (HTTP ${t.status}).`);
      }
    } catch (e: unknown) {
      setContextError(e instanceof Error ? e.message : String(e));
    }
  }, [period]);

  // S8 refactor: ⌘J as a legacy shortcut now closes the panel (since
  // mounting === open, "toggling" while mounted means closing). The
  // workspace store handles open via the shortcut module's ⌘/ binding.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        // Defer to shortcuts.ts via the custom-event channel; the
        // shortcut module knows the panel id + routes through workspace.
        window.dispatchEvent(new CustomEvent("antiek:aisidecar:toggle"));
        return;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Mount-load: fetch usage + dispatch context immediately + focus the
  // textarea. Refresh on each mount (the panel system unmounts + remounts
  // when the operator closes + reopens, so this is fresh-on-open).
  useEffect(() => {
    aliveRef.current = true;
    void reloadContext();
    setTimeout(() => inputRef.current?.focus(), 0);
    return () => {
      aliveRef.current = false;
    };
  }, [reloadContext]);

  const sendThoughtPartner = async () => {
    if (!draft.trim() || pending) return;
    setPending(true);
    setReply(null);
    try {
      const promptSnapshot = draft;
      const contextSnapshot = composedContext.trim()
        ? composedContext
        : workspaceContextPrompt();
      // S8 WP-8.4 — ship workspace context as part of the request so
      // the assistant can reference what's currently visible to the
      // operator. The substrate's /thought-partner endpoint passes
      // `system_context` through to the underlying model as a
      // pre-prompt (substrate-side concern; we add to the request
      // optimistically — older deployments ignore the field).
      const resp = await apiFetch("/thought-partner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          investigation_id: "__sidecar__",
          prompt: promptSnapshot,
          system_context: contextSnapshot,
        }),
      });
      if (!aliveRef.current) return;
      if (!resp.ok) {
        setReply({
          shape: "CHALLENGE",
          text: `Thought-partner unavailable (HTTP ${resp.status}).`,
        });
        return;
      }
      const data = await resp.json();
      if (!aliveRef.current) return;
      const rawText: string = data.text ?? data.body ?? JSON.stringify(data);
      // S8 WP-8.4 acceptance: "When the AI asks 'open this PDF', it
      // dispatches a workspace open() action." Parse the structured
      // @@actions block out of the reply, dispatch each, and surface
      // the executed actions as a transparency log below the prose.
      const { prose, actions, parseErrors } = parseAssistantReply(rawText);
      setReply({
        shape: data.shape ?? "SYNTHESIS",
        text: prose,
      });
      notifyThoughtPartnerReplyReceived();
      if (actions.length > 0) {
        // Pass AiActionContext so each dispatched action emits a typed
        // ``ai.action.applied`` event to the substrate event log per
        // master-spec §5.5 + §13.8 + PostHog Wedge 4. The investigation
        // bucket is the sidecar's pseudo-id ``__sidecar__`` (same id
        // used in the /thought-partner request above), giving Wedge 5
        // trajectory replay a single scrubbable timeline for all
        // sidecar-driven UI actions. operator_prompt truncated to the
        // substrate's max_length=2000 to avoid validation rejection on
        // long pastes.
        const ctx = {
          operator_prompt: promptSnapshot.slice(0, 2000),
          investigation_id: "__sidecar__",
        };
        const dispatched: DispatchedAction[] = [];
        for (const action of actions) {
          // A reply may operate on the workspace, but it cannot erase its own
          // transparency surface before the operator can inspect what arrived.
          if (action.kind === "close_panel" && action.id === AISIDECAR_PANEL_ID) {
            continue;
          }
          try {
            dispatched.push(dispatchAiAction(action, ctx));
          } catch (error) {
            if (import.meta.env.DEV) {
              // eslint-disable-next-line no-console
              console.warn("[ai] action dispatch failed:", error);
            }
          }
        }
        if (dispatched.length > 0) {
          setAiLog((prev) => [...dispatched, ...prev].slice(0, 20));
        }
      }
      if (parseErrors.length > 0 && import.meta.env.DEV) {
        // eslint-disable-next-line no-console
        console.warn("[ai] action parse errors:", parseErrors);
      }
    } catch (e: unknown) {
      if (!aliveRef.current) return;
      setReply({
        shape: "CHALLENGE",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      if (aliveRef.current) setPending(false);
    }
  };

  const freePct = usage
    ? Math.min(
        100,
        Math.round((usage.free_tokens_consumed / 5_000_000) * 100),
      )
    : 0;

  // S8-full refactor: AISidecar renders as a panel body (no fixed
  // positioning, no own slide-over chrome). The workspace mounts it
  // via `PanelLayoutPanel` when ⌘/ opens the "AISidecar" PanelKind
  // docked-right; the panel chrome (handle + drag) is provided by
  // the panel system, not by this component.
  //
  // For backward-compat, the legacy ⌘J toggle still works — it
  // routes through the workspace store (open or focus). The
  // `antiek:aisidecar:toggle` event handler kept above also routes
  // through the workspace.
  return (
    <aside
      className="h-full overflow-hidden flex flex-col"
      aria-label="AI sidecar"
    >
      <div className="px-3 py-3 flex flex-col h-full gap-4 overflow-y-auto">
          <header className="space-y-1">
            <p className="text-sm font-serif text-ink dark:text-bright">AI sidecar</p>
            <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
              transparent · scoped to your session
            </p>
          </header>

          <section className="space-y-1">
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight uppercase">
              Free-tier usage ({period})
            </p>
            <div className="h-2 bg-ice-3 dark:bg-charcoal-1 rounded overflow-hidden">
              <div
                className="h-full bg-ink dark:bg-bright"
                style={{ width: `${freePct}%` }}
              />
            </div>
            <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
              {usage
                ? `${usage.free_tokens_consumed.toLocaleString()} / 5,000,000 tokens`
                : "–"}
            </p>
          </section>

          <section className="space-y-2">
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight uppercase">
              Thought partner
            </p>
            {/*
              CK-4 — the @-context picker. The operator composes a §9.0-aware
              system_context here (@doc @insight); on success onContextChange
              stores it, and sendThoughtPartner uses it INSTEAD of the opaque
              workspaceContextPrompt() so the model chats WITH the picked
              library context. personal_reading is withheld server-side on the
              non-owner path (the picker renders what reached the model).
            */}
            <ContextPicker onContextChange={setComposedContext} />
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="What's the question?"
              rows={3}
              className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y"
            />
            <button
              type="button"
              onClick={sendThoughtPartner}
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
            {reply && (
              <div className="border border-rule dark:border-charcoal-1 rounded p-2 space-y-1.5 bg-ice-1 dark:bg-charcoal-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                    {reply.shape}
                  </p>
                  {/* Reply mode: text (read) or audio (auto-spoken). The
                      text is always shown; this only governs auto-speak. */}
                  <div className="flex items-center gap-1" role="group" aria-label="Reply mode">
                    {(["text", "audio"] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        aria-pressed={replyMode === m}
                        onClick={() => setReplyMode(m)}
                        className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                          replyMode === m
                            ? "bg-ink text-white"
                            : "text-shadow-1 dark:text-moonlight hover:bg-ice-3 dark:hover:bg-charcoal-1"
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-ink dark:text-bright whitespace-pre-wrap">
                  {reply.text}
                </p>
                {reply.text.trim() && (
                  <SpokenReply text={reply.text} autoPlay={replyMode === "audio"} />
                )}
              </div>
            )}

            {/* S8 WP-8.4 — AI action transparency log. Every workspace
                action the assistant dispatched in this session shows up
                here as a pill the operator can read + undo. Empty
                until the assistant actually emits an @@actions block. */}
            {aiLog.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                  AI did
                </p>
                <ul className="space-y-1">
                  {aiLog.map((rec, idx) => (
                    <li
                      key={`${rec.at}-${idx}`}
                      className="flex items-center gap-2 border border-rule dark:border-charcoal-1 rounded px-2 py-1 bg-ice-0 dark:bg-charcoal-2"
                    >
                      <span className="flex-1 text-[11px] text-ink dark:text-bright truncate">
                        {rec.label}
                      </span>
                      {rec.undo && (
                        <button
                          type="button"
                          onClick={() => {
                            rec.undo?.();
                            setAiLog((prev) =>
                              prev.filter((r) => r !== rec),
                            );
                          }}
                          className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-rule dark:border-charcoal-1 text-ink-soft dark:text-starlight hover:bg-sun/15"
                        >
                          undo
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section className="space-y-2">
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight uppercase">
              Recent dispatch
            </p>
            {contextError ? (
              <p className="text-[11px] text-red-700 dark:text-red-300">
                {contextError}
              </p>
            ) : recentCalls.length === 0 ? (
              <p className="text-[11px] italic text-shadow-1 dark:text-moonlight">
                No recent calls in this session.
              </p>
            ) : (
              <ul className="space-y-1">
                {recentCalls.map((c) => (
                  <li
                    key={c.call_id}
                    className="text-[11px] font-mono text-ink dark:text-bright flex items-center justify-between gap-2"
                  >
                    <span className="truncate">
                      {c.tier} · {c.provider}/{c.model}
                    </span>
                    <span className="text-shadow-1 dark:text-moonlight shrink-0">
                      {c.latency_ms}ms
                      {c.fell_back ? " ⚠" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <footer className="mt-auto pt-3 border-t border-rule dark:border-charcoal-1 text-[10px] font-mono text-shadow-1 dark:text-moonlight">
            ⌘/ toggle · Esc close
          </footer>
      </div>
    </aside>
  );
}

function useMemo_period(): string {
  // Returns YYYY-MM for the current month — sidecar usage scopes
  // to the active billing month per master-spec §13.5.
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${yyyy}-${mm}`;
}
