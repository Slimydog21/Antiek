/**
 * DRW SPR-09 M3 + M5 — one research's live panel + steer controls.
 *
 * Each research renders as a card in the monitor grid (the density strategy:
 * a responsive CSS grid of cards, not N floating workspace panels — 20
 * floating panels would be unmanageable; a grid gives overview + focus). The
 * card shows the sub-question, the live state (from SPR-06's status poll),
 * the per-research cost, and the steer controls (pause/resume/stop/redirect/
 * deepen), each disabled when the action is not valid for the current state.
 */

import { useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import {
  TERMINAL_STATES,
  type ResearchStatus,
  type SteerKind,
} from "../../api/research";
import { researchRunStateStyle } from "../../shared/researchState";

export interface ResearchPanelProps {
  research: ResearchStatus;
  costUsd: number;
  onSteer: (kind: SteerKind, payload?: Record<string, unknown>) => void;
  busy?: boolean;
}

export default function ResearchPanel({ research, costUsd, onSteer, busy }: ResearchPanelProps) {
  const [redirectOpen, setRedirectOpen] = useState(false);
  const [redirectText, setRedirectText] = useState("");
  const runStyle = researchRunStateStyle(research.state);
  const terminal = TERMINAL_STATES.has(research.state);
  const isPaused = research.state === "paused";
  const isRunning = runStyle.running;

  return (
    <section
      className="flex flex-col gap-2 rounded-md border-2 border-sun bg-ice-0 p-3 dark:bg-charcoal-2"
      aria-label={`research ${research.investigation_id}`}
    >
      <header className="flex items-start justify-between gap-2">
        <p className="line-clamp-3 text-sm text-ink dark:text-bright">{research.sub_question}</p>
        <span
          className={`shrink-0 text-xxs font-semibold uppercase tracking-[0.12em] ${runStyle.textClass}`}
          aria-label="research state"
        >
          {runStyle.label}
        </span>
      </header>

      <div className="flex items-center justify-between text-xs text-shadow-1 dark:text-moonlight">
        <span className="font-mono">${costUsd.toFixed(4)}</span>
        <span className="truncate font-mono opacity-60">{research.investigation_id.slice(-12)}</span>
      </div>

      {!terminal && (
        <div className="flex flex-wrap gap-1.5">
          {isPaused ? (
            <LemonButton size="sm" variant="secondary" disabled={busy}
              onClick={() => onSteer("resume")}>Resume</LemonButton>
          ) : (
            <LemonButton size="sm" variant="secondary" disabled={busy || !isRunning}
              onClick={() => onSteer("pause")}>Pause</LemonButton>
          )}
          <LemonButton size="sm" variant="danger" disabled={busy}
            onClick={() => onSteer("stop")}>Stop</LemonButton>
          <LemonButton size="sm" variant="tertiary" disabled={busy}
            onClick={() => setRedirectOpen((v) => !v)}>Redirect</LemonButton>
          <LemonButton size="sm" variant="tertiary" disabled={busy}
            onClick={() => onSteer("deepen", { extra_budget_usd: 0.25 })}>Deepen</LemonButton>
        </div>
      )}

      {redirectOpen && !terminal && (
        <form
          className="flex gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            const q = redirectText.trim();
            if (!q) return;
            onSteer("redirect", { sub_question: q });
            setRedirectText("");
            setRedirectOpen(false);
          }}
        >
          <input
            className="min-w-0 flex-1 rounded border border-ice-4 bg-ice-1 px-2 py-1 text-xs text-ink dark:border-slate-2 dark:bg-charcoal-1 dark:text-bright"
            placeholder="Revised sub-question…"
            value={redirectText}
            onChange={(e) => setRedirectText(e.target.value)}
            aria-label="redirect sub-question"
          />
          <LemonButton size="sm" variant="primary" type="submit">Send</LemonButton>
        </form>
      )}
    </section>
  );
}
