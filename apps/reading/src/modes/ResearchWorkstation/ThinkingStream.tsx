import { useEffect, useMemo, useRef, useState } from "react";

import Thinking from "../../shared/Thinking";
import AIActionFailure from "../../shared/AIActionFailure";
import LemonButton from "../../components/lemon/LemonButton";
import type { InvestigationState } from "../../hooks/useInvestigation";
import { narrateEvent } from "./narrateEvent";
import type { Narration } from "./narrateEvent";
import TrajectoryView from "./TrajectoryView";

/**
 * ThinkingStream — the glass-box live view (SPR-02 M2/M3/M4).
 *
 * Replaces the raw TrajectoryView as the DEFAULT live surface of a running
 * research. Same event stream, different rendering: instead of one PhaseRow
 * per substrate event (action_type / phase numbers / dispatch internals), it
 * narrates the run in the user's terms via narrateEvent — "Breaking your
 * question into parts… Looking for evidence on X… Found supporting points…
 * Writing the answer." Werner thinks while it runs.
 *
 * What this component is and is NOT:
 *   - It is a READ/DISPLAY layer over `useInvestigation` (which already
 *     dedups events by event_id and exposes the live socket status). It
 *     introduces no second writer and no new event.
 *   - It is NOT the answer view (SPR-04 owns the completed synthesis) — on
 *     completion the parent swaps to MasterMdViewer; here a `done` beat
 *     just seals the stream.
 *
 * Reconnect idempotency (M2, the gate): narration is derived from
 * `investigation.events`, which `useInvestigation` has already deduped by
 * `event_id` (merging the trajectory seed with the live socket tail). A
 * dropped socket that reconnects re-delivers events the client saw, but the
 * dedupe upstream means each event narrates exactly once — the story is
 * continuous, never doubled. We dedupe again here by event_id as a local
 * belt-and-suspenders so the component is correct even if fed a raw
 * (non-deduped) event list directly.
 *
 * Steering (M3): the steer commands (Stop / pause / redirect / deepen) live
 * on the ResearchRunner and are routed through a CascadeSession — they exist
 * only when a *session* backs the research. The cascade monitor
 * (DeepResearchWorkspace / ResearchPanel) already wires them. The one-shot
 * `/inv/:id` path runs the detached Loop-1 orchestrator, which has no
 * steerable runner and no stop endpoint — so this component takes the steer
 * controls as an OPTIONAL `steer` prop and shows them only when wired. It
 * does NOT render a Stop button that silently does nothing (that would be a
 * happy-path lie). See the SPR-02 handoff for what closing the one-shot Stop
 * gap requires.
 */

export interface ThinkingStreamSteer {
  /** Stop the running research. Wired only when a session backs it; maps to
   *  the runner's STOP command. When omitted, no Stop control is shown. */
  onStop?: () => void;
  /** True while a steer command is in flight (disables the controls). */
  busy?: boolean;
  /** Plain-language reason the last steer was refused (e.g. budget already
   *  halted), shown beneath the controls. The caller derives it from the
   *  authoritative state — never an optimistic guess. */
  refusedReason?: string | null;
}

export interface ThinkingStreamProps {
  investigation: InvestigationState;
  /** Optional steer controls — present only where a session backs the
   *  research. Absent on the one-shot path (see the component doc). */
  steer?: ThinkingStreamSteer;
  /** Re-run the research after a failure (M4). Defaults to a no-op reload
   *  hint when the caller owns no retry path. */
  onRetry?: () => void;
}

interface NarratedLine extends Narration {
  eventId: string;
  /** ISO timestamp of the source event, for ordering + a relative-time hint. */
  at: string;
}

/** Map a narrated line's tone to its colour + glyph. Tones, not severities:
 *  `finding` is something learned, `caution` is a gap or self-correction. */
const TONE_STYLE: Record<Narration["tone"], { dot: string; text: string }> = {
  step: { dot: "bg-shadow-1 dark:bg-moonlight", text: "text-ink dark:text-bright" },
  finding: { dot: "bg-aurora", text: "text-ink dark:text-bright" },
  caution: { dot: "bg-sun-deep dark:bg-sun", text: "text-ink dark:text-bright" },
  milestone: { dot: "bg-emperor", text: "text-ink dark:text-bright font-semibold" },
};

export default function ThinkingStream({ investigation, steer, onRetry }: ThinkingStreamProps) {
  const [showRaw, setShowRaw] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Derive the narrated story from the (already-deduped) events. The local
  // event_id dedupe makes the derivation correct even if handed a raw list.
  const lines = useMemo<NarratedLine[]>(() => {
    const seen = new Set<string>();
    const out: NarratedLine[] = [];
    for (const e of investigation.events) {
      const id = e.event_id;
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const n = narrateEvent(e);
      if (!n) continue; // suppressed — engine mechanics no reader needs
      out.push({ ...n, eventId: id, at: e.emitted_at });
    }
    return out;
  }, [investigation.events]);

  // ── Copy-mode (herdr transfer P1): the transcript is a document you can
  //    read while the research runs — scrolling up DETACHES the live follow
  //    (never yank the reader to the bottom mid-read), a "↓ N new" pill
  //    re-pins, and `/` opens in-transcript search that never pauses the
  //    stream (herdr's copy-mode rule: the history stays live).
  const [followPinned, setFollowPinned] = useState(true);
  const [newSinceUnpin, setNewSinceUnpin] = useState(0);
  const pinnedAtCountRef = useRef(0);
  const [searchActive, setSearchActive] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeMatch, setActiveMatch] = useState(0);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    if (atBottom) {
      if (!followPinned) {
        setFollowPinned(true);
        setNewSinceUnpin(0);
      }
    } else if (followPinned) {
      // Reader detached: remember where the tail was so we can count the
      // lines that arrive while they read.
      pinnedAtCountRef.current = lines.length;
      setFollowPinned(false);
    }
  };

  // Count new lines since detach.
  useEffect(() => {
    if (!followPinned) {
      setNewSinceUnpin(lines.length - pinnedAtCountRef.current);
    }
  }, [lines.length, followPinned]);

  const jumpToLatest = () => {
    pinnedAtCountRef.current = lines.length;
    setNewSinceUnpin(0);
    setFollowPinned(true);
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  };

  // `/` opens search (ignored while typing in an editable); Esc closes it;
  // Enter/Shift+Enter step through matches.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el) {
        const tag = el.tagName.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") return;
        if (el.isContentEditable) return;
      }
      if (e.key === "/") {
        e.preventDefault();
        setSearchActive(true);
        setSearchQuery("");
        setActiveMatch(0);
        // Focus after render.
        requestAnimationFrame(() => searchInputRef.current?.focus());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Search matches: line indices whose narration contains the query.
  const matches = useMemo(
    () => findMatchIndices(lines.map((l) => l.line), searchQuery),
    [lines, searchQuery],
  );
  useEffect(() => {
    setActiveMatch(0);
  }, [searchQuery, matches.length]);
  // Keep the active index in range as matches shrink.
  useEffect(() => {
    if (matches.length === 0) setActiveMatch(0);
    else if (activeMatch >= matches.length) setActiveMatch(matches.length - 1);
  }, [matches.length, activeMatch]);

  // Jump the active match into view.
  useEffect(() => {
    if (!searchActive || matches.length === 0) return;
    const el = scrollRef.current?.querySelector(
      `[data-line-index="${matches[activeMatch]}"]`,
    );
    el?.scrollIntoView({ block: "center" });
  }, [searchActive, activeMatch, matches]);

  const stepMatch = (dir: 1 | -1) => {
    if (matches.length === 0) return;
    setActiveMatch((m) => (m + dir + matches.length) % matches.length);
  };

  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      stepMatch(e.shiftKey ? -1 : 1);
    } else if (e.key === "Escape") {
      setSearchActive(false);
      setSearchQuery("");
    }
  };

  // Preserve TrajectoryView's auto-scroll-to-tail so the live story stays in
  // view as it grows — but ONLY while the reader is pinned to the tail
  // (copy-mode: scroll up and the follow detaches; the "↓ N new" pill
  // re-pins).
  useEffect(() => {
    const el = scrollRef.current;
    if (el && followPinned) el.scrollTop = el.scrollHeight;
  }, [lines.length, followPinned]);

  const running = investigation.status === "in_progress";
  // The socket dropped mid-run and is re-establishing — show a reconnecting
  // beat, never a frozen feed (M2).
  const reconnecting =
    running && streamConnectingOrError(investigation.streamStatus) && lines.length > 0;

  // ── M4: honest no-result. A failed run (the no-key case: Loop 1 aborts
  //    with investigation.failed and nothing to narrate) shows the shared
  //    failure surface, never a perpetual "thinking…". `not_found` is the
  //    same shape (an id with no trajectory — also what a keyless start
  //    leaves behind). ──
  if (investigation.status === "failed" || investigation.status === "not_found") {
    const reason =
      investigation.status === "failed"
        ? failureReason(investigation)
        : null;
    return (
      <div className="flex h-full min-h-0 flex-col">
        <StreamHeader
          investigation={investigation}
          sealed
          showRaw={showRaw}
          onToggleRaw={() => setShowRaw((v) => !v)}
        />
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <AIActionFailure
            title="The research didn’t complete"
            reason={reason}
            onRetry={onRetry ?? (() => window.location.reload())}
          />
          {showRaw && (
            <div className="mt-4 border-t border-rule pt-3 dark:border-charcoal-1">
              <RawActivity investigation={investigation} />
            </div>
          )}
        </div>
      </div>
    );
  }

  const sealed = investigation.status === "completed";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <StreamHeader
        investigation={investigation}
        sealed={sealed}
        showRaw={showRaw}
        onToggleRaw={() => setShowRaw((v) => !v)}
        steer={!sealed ? steer : undefined}
      />

      {showRaw ? (
        <div className="flex-1 min-h-0">
          <RawActivity investigation={investigation} />
        </div>
      ) : (
        <>
          {/* Copy-mode search bar (herdr transfer P1) — `/` to open. The
              stream keeps flowing while you search. */}
          {searchActive && (
            <div className="flex items-center gap-2 border-b border-rule bg-ice-1 px-3 py-1.5 dark:border-charcoal-1">
              <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">/</span>
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={onSearchKeyDown}
                placeholder="Search the transcript…"
                aria-label="Search the transcript"
                className="flex-1 bg-transparent font-serif text-[13px] text-ink dark:text-bright placeholder:text-ink-mute dark:text-moonlight outline-none"
              />
              <span
                className="font-mono text-[11px] text-shadow-1 dark:text-moonlight tabular-nums"
                aria-live="polite"
              >
                {matches.length === 0 && searchQuery.trim()
                  ? "0/0"
                  : matches.length > 0
                    ? `${activeMatch + 1}/${matches.length}`
                    : ""}
              </span>
              {searchQuery.trim() && matches.length > 0 && (
                <button
                  type="button"
                  onClick={() => stepMatch(1)}
                  aria-label="Next match"
                  className="px-1 font-mono text-[12px] text-shadow-1 hover:text-ink dark:hover:text-bright"
                >
                  ↓
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setSearchActive(false);
                  setSearchQuery("");
                }}
                aria-label="Close search"
                className="px-1 font-mono text-[12px] text-shadow-1 hover:text-ink dark:hover:text-bright"
              >
                ✕
              </button>
            </div>
          )}
          <div ref={scrollRef} onScroll={onScroll} className="relative flex-1 overflow-y-auto px-4 py-4">
          {lines.length === 0 ? (
            <ConnectingBeat status={investigation.streamStatus} />
          ) : (
            <ol className="space-y-2.5">
              {lines.map((l, i) => {
                const isActiveMatch = matches.includes(i) && i === matches[activeMatch];
                return (
                  <li
                    key={l.eventId}
                    data-line-index={i}
                    className={`flex items-start gap-2.5 ${isActiveMatch ? "rounded bg-sun/10 px-1 -mx-1" : ""}`}
                  >
                    <span
                      className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${TONE_STYLE[l.tone].dot}`}
                      aria-hidden="true"
                    />
                    <span className={`font-serif text-[14px] leading-relaxed ${TONE_STYLE[l.tone].text}`}>
                      {searchQuery.trim()
                        ? splitMatches(l.line, searchQuery).map((seg, k) =>
                            seg.match ? (
                              <mark
                                key={k}
                                className="rounded-sm bg-sun/40 px-0.5 text-inherit dark:bg-sun/30"
                              >
                                {seg.text}
                              </mark>
                            ) : (
                              <span key={k}>{seg.text}</span>
                            ),
                          )
                        : l.line}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}

          {/* While running, Werner thinks under the last line — the ongoing
              "it's still working" signal. Sealed runs drop it. */}
          {running && lines.length > 0 && (
            <div className="mt-4 flex items-center gap-2" role="status" aria-live="polite">
              <Thinking
                size={28}
                label={reconnecting ? "Reconnecting to the research" : "The research is working"}
                status={reconnecting ? "reconnecting…" : "thinking…"}
              />
            </div>
          )}

          {sealed && (
            <p className="mt-4 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
              the answer is below
            </p>
          )}

          {/* Copy-mode jump pill — appears only after the reader detached
              AND new lines arrived; click re-pins to the live tail. */}
          {!followPinned && newSinceUnpin > 0 && (
            <button
              type="button"
              onClick={jumpToLatest}
              className="sticky bottom-3 mx-auto block rounded-full border border-aurora bg-ice-1 px-3 py-1 font-mono text-[11px] text-aurora shadow-z2 dark:bg-charcoal-2 dark:shadow-z2-night hover:bg-ice-3"
              data-testid="copy-mode-jump-pill"
            >
              ↓ {newSinceUnpin} new · jump to latest
            </button>
          )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Header: status word + live cost + steer + raw toggle ───────────────────

function StreamHeader({
  investigation,
  sealed,
  showRaw,
  onToggleRaw,
  steer,
}: {
  investigation: InvestigationState;
  sealed: boolean;
  showRaw: boolean;
  onToggleRaw: () => void;
  steer?: ThinkingStreamSteer;
}) {
  const statusWord = sealed
    ? investigation.status === "completed"
      ? "done"
      : "stopped"
    : investigation.status === "in_progress"
      ? "thinking"
      : investigation.status === "loading"
        ? "starting"
        : investigation.status;

  return (
    <div className="flex items-center justify-between gap-3 border-b border-rule bg-ice-1 px-4 py-2 dark:border-charcoal-1 dark:bg-charcoal-2">
      <div className="flex items-center gap-3 text-xs">
        <span
          className={`font-mono uppercase tracking-wider ${
            investigation.status === "in_progress"
              ? "text-aurora"
              : investigation.status === "completed"
                ? "text-emerald-700"
                : "text-shadow-1 dark:text-moonlight"
          }`}
        >
          {statusWord}
        </span>
        <span className="text-ink-mute dark:text-moonlight">·</span>
        {/* M3: real accumulated cost in dollars, no token jargon. */}
        <span className="font-mono text-ink-soft dark:text-starlight" aria-label="cost so far">
          ${investigation.costTotal.toFixed(4)}
        </span>
      </div>

      <div className="flex items-center gap-3">
        {steer?.onStop && (
          <LemonButton
            size="sm"
            variant="danger"
            disabled={steer.busy}
            onClick={steer.onStop}
          >
            Stop
          </LemonButton>
        )}
        <button
          type="button"
          onClick={onToggleRaw}
          className="font-mono text-xs text-shadow-1 transition-colors hover:text-ink dark:text-moonlight dark:hover:text-bright"
        >
          {showRaw ? "hide raw activity" : "show raw activity"}
        </button>
      </div>
    </div>
  );
}

/** A steer that was refused (e.g. the research already halted on budget) —
 *  shown in plain language beneath the controls. Rendered by the caller's
 *  surface, exposed here so the message lives next to the controls it
 *  explains. (Kept separate from the header so the header stays a pure
 *  layout of always-visible controls.) */
export function SteerRefusal({ reason }: { reason: string | null | undefined }) {
  if (!reason) return null;
  return (
    <p className="px-4 py-1 font-mono text-[11px] text-sun-deep dark:text-sun" role="status">
      {reason}
    </p>
  );
}

/** The stream is connecting or errored — one source of truth so the main feed
 *  and the connecting beat can't drift on what counts as re-establishing. */
function streamConnectingOrError(status: InvestigationState["streamStatus"]): boolean {
  return status === "connecting" || status === "error";
}

function ConnectingBeat({ status }: { status: InvestigationState["streamStatus"] }) {
  const reconnecting = streamConnectingOrError(status);
  return (
    <div className="flex flex-col items-center gap-2 py-10" role="status" aria-live="polite">
      <Thinking
        size={40}
        label={reconnecting ? "Connecting to the research" : "The research is starting"}
      />
      <p className="font-serif text-sm text-ink dark:text-bright">
        {reconnecting ? "Connecting…" : "Getting started…"}
      </p>
      <p className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
        the first step will appear here
      </p>
    </div>
  );
}

/** The power-user escape hatch (M2): the raw event log, unchanged. Reusing
 *  TrajectoryView preserves auditability + cost-debugging — it is the same
 *  surface, demoted from default to opt-in, not deleted. */
function RawActivity({ investigation }: { investigation: InvestigationState }) {
  return <TrajectoryView investigation={investigation} />;
}

/** Read the failure reason from the terminal investigation.failed event, if
 *  it carried one. Absent → null, which AIActionFailure renders as the
 *  honest no-provider sentence (the common keyless case). */
function failureReason(investigation: InvestigationState): string | null {
  const p = investigation.terminalPayload as { reason?: unknown } | null;
  return p && typeof p.reason === "string" && p.reason.trim() ? p.reason.trim() : null;
}


// ── Copy-mode pure helpers (herdr transfer P1) — extracted for unit tests.
//    The search is substring over narrated lines; matches are case-
//    insensitive, and splitting keeps the <mark> rendering trivial. ───────

/** Line indices whose narration contains the query (case-insensitive). */
export function findMatchIndices(lines: string[], query: string): number[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const out: number[] = [];
  lines.forEach((line, i) => {
    if (line.toLowerCase().includes(q)) out.push(i);
  });
  return out;
}

/** Split text around case-insensitive query matches for <mark> rendering.
 *  Empty query returns the whole text as one non-match segment. */
export function splitMatches(
  text: string,
  query: string,
): { text: string; match: boolean }[] {
  const q = query.trim().toLowerCase();
  if (!q) return [{ text, match: false }];
  const lower = text.toLowerCase();
  const out: { text: string; match: boolean }[] = [];
  let i = 0;
  for (;;) {
    const idx = lower.indexOf(q, i);
    if (idx === -1) {
      if (i < text.length) out.push({ text: text.slice(i), match: false });
      break;
    }
    if (idx > i) out.push({ text: text.slice(i, idx), match: false });
    out.push({ text: text.slice(idx, idx + q.length), match: true });
    i = idx + q.length;
  }
  if (out.length === 0) out.push({ text, match: false });
  return out;
}
