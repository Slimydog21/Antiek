import { useEffect, useId, useMemo, useRef, useState } from "react";

import Thinking from "../../shared/Thinking";
import AIActionFailure from "../../shared/AIActionFailure";
import LemonButton from "../../components/lemon/LemonButton";
import type { InvestigationState } from "../../hooks/useInvestigation";
import { narrateEvent } from "./narrateEvent";
import type { Narration, NarrationTone } from "./narrateEvent";
import TrajectoryView from "./TrajectoryView";
import "./thinking-field-journal.css";

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

/** Map a tone to its CSS custom property accent colour for the responsive
 *  left-border rule. These are existing token values, not new colours. */
const TONE_ACCENT: Record<NarrationTone, string> = {
  step: "var(--rule)",
  finding: "var(--aurora)",
  caution: "var(--sun-deep)",
  milestone: "var(--shadow-1)",
};

/** Visible label text for each tone. */
const TONE_LABEL: Record<NarrationTone, string> = {
  step: "step",
  finding: "finding",
  caution: "caution",
  milestone: "milestone",
};

export default function ThinkingStream({ investigation, steer, onRetry }: ThinkingStreamProps) {
  const [showRaw, setShowRaw] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const rawPanelId = `thinking-stream-raw-panel-${useId().replace(/:/g, "")}`;

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

  // Preserve TrajectoryView's auto-scroll-to-tail so the live story stays in
  // view as it grows.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

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
  if (investigation.status === "not_found") {
    return (
      <section className="flex h-full min-h-0 flex-col" aria-label="Research field journal">
        <StreamHeader
          investigation={investigation}
          sealed
          showRaw={showRaw}
          rawPanelId={rawPanelId}
          onToggleRaw={() => setShowRaw((v) => !v)}
        />
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div role="alert" className="flex flex-col gap-2 font-mono text-xs text-emperor">
            <p className="leading-relaxed">
              Research not found — no research exists for this link. It may have been removed or the link may be incomplete.
            </p>
            <div>
              <LemonButton variant="secondary" size="sm" onClick={onRetry ?? (() => window.location.reload())}>
                Reload
              </LemonButton>
            </div>
          </div>
        </div>
        <div id={rawPanelId} hidden={!showRaw}>
          {showRaw ? <RawActivity investigation={investigation} /> : null}
        </div>
      </section>
    );
  }

  if (investigation.status === "failed") {
    const reason = failureReason(investigation);
    return (
      <section className="flex h-full min-h-0 flex-col" aria-label="Research field journal">
        <StreamHeader
          investigation={investigation}
          sealed
          showRaw={showRaw}
          rawPanelId={rawPanelId}
          onToggleRaw={() => setShowRaw((v) => !v)}
        />
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <AIActionFailure
            title="The research didn’t complete"
            reason={reason}
            onRetry={onRetry ?? (() => window.location.reload())}
          />
          <div
            id={rawPanelId}
            hidden={!showRaw}
            className="mt-4 border-t border-rule pt-3 dark:border-charcoal-1"
          >
            {showRaw ? <RawActivity investigation={investigation} /> : null}
          </div>
        </div>
      </section>
    );
  }

  const sealed = investigation.status === "completed";

  return (
    <section className="flex h-full min-h-0 flex-col" aria-label="Research field journal">
      <StreamHeader
        investigation={investigation}
        sealed={sealed}
        showRaw={showRaw}
        rawPanelId={rawPanelId}
        onToggleRaw={() => setShowRaw((v) => !v)}
        steer={!sealed ? steer : undefined}
      />

      <div id={rawPanelId} hidden={!showRaw} className="flex-1 min-h-0">
        {showRaw ? <RawActivity investigation={investigation} /> : null}
      </div>
      <div ref={scrollRef} hidden={showRaw} className="flex-1 overflow-y-auto px-4 py-4">
          {lines.length === 0 ? (
            <ConnectingBeat status={investigation.streamStatus} />
          ) : (
            <div className="thinking-field-journal__section">
              <p className="thinking-field-journal__header">Narration</p>
              <ol className="thinking-field-journal__list">
                {lines.map((l, i) => (
                  <li
                    key={l.eventId}
                    className="thinking-field-journal__item"
                    style={{ "--tfj-tone-accent": TONE_ACCENT[l.tone] } as React.CSSProperties}
                  >
                    <span
                      className="thinking-field-journal__index"
                      aria-hidden="true"
                    >
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span
                      className={`thinking-field-journal__tone-dot ${TONE_STYLE[l.tone].dot}`}
                      aria-hidden="true"
                    />
                    <span
                      className={`thinking-field-journal__tone-label thinking-field-journal__tone-label--${l.tone}`}
                    >
                      {TONE_LABEL[l.tone]}
                    </span>
                    <span className={`thinking-field-journal__prose ${TONE_STYLE[l.tone].text}`}>
                      {l.line}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
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

          {sealed && <ClosingFolio />}
      </div>
    </section>
  );
}

// ── Header: status word + live cost + steer + raw toggle ───────────────────

function StreamHeader({
  investigation,
  sealed,
  showRaw,
  rawPanelId,
  onToggleRaw,
  steer,
}: {
  investigation: InvestigationState;
  sealed: boolean;
  showRaw: boolean;
  rawPanelId: string;
  onToggleRaw: () => void;
  steer?: ThinkingStreamSteer;
}) {
  const statusWord = sealed
    ? investigation.status === "completed"
      ? "done"
      : investigation.status === "not_found"
        ? "not found"
      : "stopped"
    : investigation.status === "in_progress"
      ? "thinking"
      : investigation.status === "loading"
        ? "starting"
        : investigation.status;

  return (
    <header className="thinking-field-journal__folio flex items-center justify-between gap-3 border-b border-rule bg-ice-1 px-4 py-2 dark:border-charcoal-1 dark:bg-charcoal-2">
      <div className="flex items-center gap-3 text-xs">
        <span
          className={`font-mono uppercase tracking-wider ${
            investigation.status === "in_progress"
              ? "text-shadow-2 dark:text-starlight"
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
          aria-expanded={showRaw}
          aria-controls={rawPanelId}
          className="font-mono text-xs text-shadow-1 transition-colors hover:text-ink dark:text-moonlight dark:hover:text-bright"
        >
          {showRaw ? "hide raw activity" : "show raw activity"}
        </button>
      </div>
    </header>
  );
}

/** Closing folio — the terminal beat after a sealed research stream. */
function ClosingFolio() {
  return (
    <div className="thinking-field-journal__closing-folio" role="note" aria-label="Research complete">
      <hr className="thinking-field-journal__folio-rule" />
      <p className="thinking-field-journal__folio-text">the answer is below</p>
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
