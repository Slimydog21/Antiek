/**
 * AgentThread.tsx — the pane's turns (SPR-07 M3). Model prose with a
 * streaming caret; one status row per turn (the Antiek status word, an
 * elapsed timer that counts visible time only — useElapsed — and the
 * TRANSPORT LABEL: when the transport returns the whole reply the row
 * visibly says "simulated stream: the reply arrives whole", fix 2); tool
 * rows collapsed by default (rendered only when a turn has tools); the
 * yielding auto-scroll with "Jump to latest" (threadScroll.ts).
 */
import { useEffect, useReducer, useRef, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import type { AgentTurn } from "./agentThreadStore";
import { statusLabel } from "./statusWords";
import { useFollowTail } from "./threadScroll";
import { statusRowFor, type LifecycleState } from "./turnLifecycle";

export const WHOLE_REPLY_LABEL = "simulated stream: the reply arrives whole";

export interface AgentThreadProps {
  turns: readonly AgentTurn[];
  transportKind: "whole" | "sse";
  lifecycle: LifecycleState;
  interview: boolean;
  reducedMotion: boolean;
  onRetry: () => void;
}

const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());
const docHidden = () => typeof document !== "undefined" && document.hidden;

/**
 * Seconds the turn has been running WHILE THE DOCUMENT WAS VISIBLE (repair
 * C4): the value is an accumulator of visible stretches, never a wall-clock
 * span, so a tab hidden for a minute comes back at the number it left and a
 * re-render while hidden (a streaming chunk) cannot advance it. Ticks once a
 * second only while the turn runs and the document is visible.
 *
 * A settled turn freezes at the visible time it had when `endedAt` was
 * stamped (second repair, finding 1): the open stretch is folded into the
 * accumulator at that moment, clamped to `endedAt`, and no stretch is open
 * while the turn is settled — so looking at a finished turn, then hiding and
 * showing the tab, never moves its number. A late reply that heals a failed
 * turn clears `endedAt`; the stretch reopens then, and the timer resumes
 * from the visible time the turn had, not from the time spent looking at
 * the failure.
 */
function useElapsed(startedAt: number, endedAt: number | undefined, running: boolean): number {
  const [, bump] = useReducer((n: number) => n + 1, 0);
  const [hidden, setHidden] = useState(docHidden);
  /** ms of visible time before the current visible stretch. */
  const acc = useRef(0);
  /** When the current visible stretch began; null while hidden or settled. */
  const since = useRef<number | null>(null);
  /** The `endedAt` the accumulator was last reconciled with. */
  const settledAt = useRef<number | undefined>(undefined);
  const seededFor = useRef<number | null>(null);
  if (seededFor.current !== startedAt) {
    seededFor.current = startedAt;
    acc.current = 0;
    settledAt.current = undefined;
    since.current = docHidden() ? null : startedAt;
  }
  if (endedAt !== undefined && settledAt.current === undefined) {
    // Settling: fold the open stretch up to endedAt (never past it) and close it.
    if (since.current !== null) {
      acc.current += Math.max(0, Math.min(now(), endedAt) - since.current);
      since.current = null;
    }
  } else if (endedAt === undefined && settledAt.current !== undefined && !docHidden()) {
    // Healed (a late reply after the fallback): a new visible stretch starts now.
    since.current = now();
  }
  settledAt.current = endedAt;
  useEffect(() => {
    const onVisibility = () => {
      if (docHidden()) {
        if (since.current !== null) { acc.current += now() - since.current; since.current = null; }
      } else if (since.current === null && settledAt.current === undefined) {
        since.current = now();
      }
      setHidden(docHidden());
      bump();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);
  useEffect(() => {
    if (!running || hidden) return;
    const timer = setInterval(bump, 1000);
    return () => clearInterval(timer);
  }, [running, hidden]);
  const ms = acc.current + (since.current === null ? 0 : Math.max(0, now() - since.current));
  return Math.max(0, Math.round(ms / 1000));
}

function Turn({ turn, index, transportKind, reducedMotion }: { turn: AgentTurn; index: number; transportKind: "whole" | "sse"; reducedMotion: boolean }) {
  const running = turn.status === "pending" || turn.status === "streaming";
  const elapsed = useElapsed(turn.startedAt, turn.endedAt, running);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  return (
    <article className="flex flex-col gap-1" data-agent-turn {...(turn.hidden ? { "data-hidden-question": "" } : {})}>
      {turn.hidden ? null : (
        <blockquote className="text-sm font-serif text-ink-soft dark:text-starlight italic border-l-edge border-sun pl-2 leading-relaxed">
          “{turn.question}”
        </blockquote>
      )}
      {turn.answer !== null ? (
        <div className="bg-shadow-2 rounded p-2">
          <span className="text-xxs uppercase tracking-wider text-moonlight block mb-0.5">AI reply</span>
          <p className="text-sm text-bright whitespace-pre-wrap leading-relaxed">
            {turn.answer}
            {turn.status === "streaming" ? (
              <span
                data-stream-caret
                aria-hidden="true"
                className="inline-block align-text-bottom w-[0.16em] h-[1em] ml-px bg-current motion-reduce:animate-none"
                style={{ animation: reducedMotion ? "none" : "antiek-agent-caret 1s steps(2) infinite" }}
              />
            ) : null}
          </p>
        </div>
      ) : null}
      <p className="text-xxs font-mono text-shadow-1 dark:text-moonlight" data-turn-status>
        {turn.status === "done" || turn.status === "failed" ? statusLabel(turn.status, index) : turn.statusWord} · {elapsed}s
        {transportKind === "whole" ? ` · ${WHOLE_REPLY_LABEL}` : ""}
        {turn.libraryRetrievalStatus ? ` · library: ${turn.libraryRetrievalStatus}` : ""}
      </p>
      {/* Tool rows: nothing is rendered when a turn has no tools. */}
      {turn.tools.length > 0 ? (
        <div className="flex flex-col gap-0.5" data-tool-rows>
          {turn.tools.map((tool) => {
            const open = expanded.has(tool.id);
            return (
              <div key={tool.id} className="text-xxs font-mono text-shadow-1 dark:text-moonlight">
                <button
                  type="button"
                  aria-expanded={open}
                  className="underline-offset-2 hover:underline"
                  onClick={() => setExpanded((s) => { const n = new Set(s); if (n.has(tool.id)) n.delete(tool.id); else n.add(tool.id); return n; })}
                >
                  {tool.status === "running" ? "running" : tool.status === "done" ? "ran" : "failed"} {tool.name}
                </button>
                {open && tool.detail ? <p className="pl-2">{tool.detail}</p> : null}
              </div>
            );
          })}
        </div>
      ) : null}
    </article>
  );
}

export function AgentThread({ turns, transportKind, lifecycle, interview, reducedMotion, onRetry }: AgentThreadProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentKey = turns.map((t) => `${t.id}:${t.status}:${t.answer?.length ?? 0}`).join("|");
  const { following, jump, handlers } = useFollowTail(scrollRef, contentKey);
  const notice = statusRowFor(lifecycle.phase, { interview });
  return (
    <div className="relative flex-1 min-h-0">
      <div ref={scrollRef} className="h-full overflow-y-auto overflow-x-hidden p-3 flex flex-col gap-3" data-agent-thread-scroll {...handlers}>
        {turns.map((turn, i) => (
          <Turn key={turn.id} turn={turn} index={i} transportKind={transportKind} reducedMotion={reducedMotion} />
        ))}
        {notice ? (
          <div className="flex items-center gap-2" role="status" data-lifecycle-notice>
            <p className={`text-xs ${lifecycle.phase === "failed" ? "text-emperor" : "text-shadow-1 dark:text-moonlight"}`}>{notice}</p>
            {lifecycle.phase === "failed" ? (
              <LemonButton variant="secondary" size="sm" onClick={onRetry}>Retry</LemonButton>
            ) : null}
          </div>
        ) : null}
      </div>
      {!following ? (
        // Keyboard-reachable (repair C8): a real button in the tab order,
        // named for assistive tech; it leaves with the follow state.
        <button
          type="button"
          data-jump-to-latest
          aria-label="Jump to latest reply"
          onClick={jump}
          className={`absolute bottom-2 right-3 h-9 px-3 rounded-full border border-hairline bg-ice-0 dark:bg-charcoal-2 text-xs text-ink dark:text-bright shadow-z2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun ${reducedMotion ? "" : "transition-[opacity,transform] duration-200"}`}
        >
          Jump to latest
        </button>
      ) : null}
    </div>
  );
}
