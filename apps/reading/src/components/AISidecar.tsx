import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../lib/api";

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
  fallback_reason: string | null;
}

interface ThoughtPartnerReply {
  shape: "CHALLENGE" | "SYNTHESIS" | "EXTENSION";
  text: string;
}

export default function AISidecar() {
  const [open, setOpen] = useState(false);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [recentCalls, setRecentCalls] = useState<DispatchEvent[]>([]);
  const [draft, setDraft] = useState<string>("");
  const [reply, setReply] = useState<ThoughtPartnerReply | null>(null);
  const [pending, setPending] = useState<boolean>(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const period = useMemo_period();

  const reloadContext = useCallback(async () => {
    try {
      const [u, t] = await Promise.all([
        apiFetch(`/billing/summary/__operator__/${period}`).catch(() => null),
        apiFetch("/trajectory?limit=8").catch(() => null),
      ]);
      if (u?.ok) {
        const data = await u.json();
        setUsage({
          free_tokens_consumed: data.free_tokens_consumed ?? 0,
          free_tokens_remaining: data.free_tokens_remaining ?? 5_000_000,
          record_count: data.record_count ?? 0,
        });
      }
      if (t?.ok) {
        const data = await t.json();
        type RawDispatchEvent = {
          payload?: Record<string, unknown> & {
            call_id?: string;
            tier?: string;
            provider?: string;
            model?: string;
            latency_ms?: number;
            fallback_reason?: string | null;
          };
        };
        const events = (data.events ?? [])
          .filter((e: RawDispatchEvent) => e.payload?.call_id)
          .slice(-8)
          .map((e: RawDispatchEvent) => ({
            call_id: e.payload?.call_id ?? "",
            tier: e.payload?.tier ?? "?",
            provider: e.payload?.provider ?? "?",
            model: e.payload?.model ?? "?",
            latency_ms: e.payload?.latency_ms ?? 0,
            fallback_reason: e.payload?.fallback_reason ?? null,
          }));
        setRecentCalls(events);
      }
    } catch {
      // Sidecar is non-blocking; offline state shows last-loaded values.
    }
  }, [period]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const toggle =
        (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j";
      if (toggle) {
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (e.key === "Escape" && open) {
        e.preventDefault();
        setOpen(false);
      }
    };
    // S8: the workspace shortcuts module dispatches this when ⌘/ fires.
    // Until AISidecar is refactored into a real panel kind, we listen
    // for the event here and flip our own state.
    const onExternalToggle = () => setOpen((v) => !v);
    window.addEventListener("keydown", handler);
    window.addEventListener(
      "antiek:aisidecar:toggle" as keyof WindowEventMap,
      onExternalToggle as EventListener,
    );
    return () => {
      window.removeEventListener("keydown", handler);
      window.removeEventListener(
        "antiek:aisidecar:toggle" as keyof WindowEventMap,
        onExternalToggle as EventListener,
      );
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      void reloadContext();
      setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      setReply(null);
    }
  }, [open, reloadContext]);

  const sendThoughtPartner = async () => {
    if (!draft.trim() || pending) return;
    setPending(true);
    setReply(null);
    try {
      const resp = await apiFetch("/thought-partner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          investigation_id: "__sidecar__",
          prompt: draft,
        }),
      });
      if (!resp.ok) {
        // Endpoint may not exist yet in older deployments; surface the
        // status code instead of crashing.
        setReply({
          shape: "CHALLENGE",
          text: `Thought-partner unavailable (HTTP ${resp.status}).`,
        });
        return;
      }
      const data = await resp.json();
      setReply({
        shape: data.shape ?? "SYNTHESIS",
        text: data.text ?? data.body ?? JSON.stringify(data),
      });
    } catch (e: unknown) {
      setReply({
        shape: "CHALLENGE",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setPending(false);
    }
  };

  const freePct = usage
    ? Math.min(
        100,
        Math.round((usage.free_tokens_consumed / 5_000_000) * 100),
      )
    : 0;

  return (
    <aside
      className={`fixed top-14 right-0 h-[calc(100vh-3.5rem)] z-30 border-l border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 transition-all ${
        open ? "w-[320px]" : "w-8"
      } overflow-hidden`}
      aria-label="AI sidecar"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-8 h-12 flex items-center justify-center text-ink-soft dark:text-starlight hover:bg-ice-3 dark:bg-charcoal-1 absolute top-2 left-0"
        title="Toggle AI sidecar (⌘J)"
      >
        {open ? "›" : "‹"}
      </button>

      {open && (
        <div className="pl-8 pr-3 py-3 flex flex-col h-full gap-4 overflow-y-auto">
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
              className="w-full px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors disabled:opacity-50"
            >
              {pending ? "Thinking…" : "Send"}
            </button>
            {reply && (
              <div className="border border-rule dark:border-charcoal-1 rounded p-2 space-y-1 bg-ice-1 dark:bg-charcoal-2">
                <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                  {reply.shape}
                </p>
                <p className="text-xs text-ink dark:text-bright whitespace-pre-wrap">
                  {reply.text}
                </p>
              </div>
            )}
          </section>

          <section className="space-y-2">
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight uppercase">
              Recent dispatch
            </p>
            {recentCalls.length === 0 ? (
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
                      {c.fallback_reason ? " ⚠" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <footer className="mt-auto pt-3 border-t border-rule dark:border-charcoal-1 text-[10px] font-mono text-shadow-1 dark:text-moonlight">
            ⌘J toggle · Esc close
          </footer>
        </div>
      )}
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
