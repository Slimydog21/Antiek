/**
 * Midnight Oil — unattended deep-research preflight panel.
 *
 * Operator sets goals + work window; system recommends a price ceiling;
 * explicit ack forms an approval *request* only (server still owns spend).
 */

import { useMemo, useState } from "react";

import midnightOilArt from "../../../brand/werner/poses/session/werner_midnight_oil_session_v1.webp";
import { emitWernerExperience } from "../../../werner/reactionBus";
import {
  buildMidnightOilPreflight,
  requestMidnightOilApproval,
} from "./midnightOilPolicy";

export function MidnightOilPanel() {
  const [goalText, setGoalText] = useState("");
  const [goals, setGoals] = useState<{ id: string; text: string }[]>([]);
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [ack, setAck] = useState(false);
  const [requestJson, setRequestJson] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const plan = useMemo(
    () =>
      buildMidnightOilPreflight({
        goals,
        durationMinutes,
      }),
    [goals, durationMinutes],
  );

  const addGoal = () => {
    const text = goalText.trim();
    if (!text) return;
    setGoals((g) => [...g, { id: `g${Date.now().toString(36)}`, text }]);
    setGoalText("");
    setRequestJson(null);
    // Living-TV: parking a midnight-oil goal is a curious glance.
    emitWernerExperience("highlight");
  };

  return (
    <section
      data-testid="midnight-oil-panel"
      className="space-y-3"
      aria-label="Midnight oil"
    >
      <header className="space-y-1">
        <h2 className="text-lg font-serif text-ink dark:text-bright">
          Midnight oil
        </h2>
        <p className="text-sm text-ink-soft dark:text-starlight font-serif italic">
          Unattended deep-research swarm — set goals and a work window, review
          the recommended price ceiling, then approve a request. Spend
          authority stays on the server; this panel never launches work.
        </p>
      </header>

      <img
        src={midnightOilArt}
        alt=""
        aria-hidden="true"
        data-testid="midnight-oil-living-tv-art"
        className="h-20 w-full max-w-xl rounded-md object-cover object-center"
        loading="lazy"
        decoding="async"
      />

      <div className="flex flex-wrap gap-2">
        <input
          data-testid="midnight-oil-goal-input"
          value={goalText}
          onChange={(e) => setGoalText(e.target.value)}
          placeholder="Research goal…"
          className="min-w-[200px] flex-1 rounded border border-rule bg-ice-1 px-2 py-1 text-[13px] text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addGoal();
            }
          }}
        />
        <button
          type="button"
          data-testid="midnight-oil-add-goal"
          onClick={addGoal}
          className="rounded border border-rule px-2 py-1 font-mono text-[10px] uppercase dark:border-charcoal-1"
        >
          Add goal
        </button>
      </div>

      <ul
        data-testid="midnight-oil-goals"
        className="space-y-1 font-mono text-[12px] text-ink dark:text-bright"
      >
        {goals.length === 0 ? (
          <li className="text-shadow-1 dark:text-moonlight">No goals yet.</li>
        ) : (
          goals.map((g) => (
            <li key={g.id} data-testid={`midnight-oil-goal-${g.id}`}>
              · {g.text}
            </li>
          ))
        )}
      </ul>

      <label className="flex flex-col gap-1 font-mono text-[11px] uppercase text-shadow-1 dark:text-moonlight">
        Work window (minutes)
        <input
          data-testid="midnight-oil-duration"
          type="number"
          min={15}
          max={720}
          step={15}
          value={durationMinutes}
          onChange={(e) => setDurationMinutes(Number(e.target.value) || 0)}
          className="w-28 rounded border border-rule bg-ice-1 px-2 py-1 text-[13px] normal-case text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
        />
      </label>

      {plan.ok ? (
        <div
          data-testid="midnight-oil-preflight"
          className="rounded border border-rule p-3 font-mono text-[12px] dark:border-charcoal-1"
        >
          <div>
            Recommended ceiling:{" "}
            <strong className="text-ink dark:text-bright">
              ${(plan.recommendedCeilingCents / 100).toFixed(2)}
            </strong>{" "}
            USD
          </div>
          <div className="text-[11px] text-shadow-1 dark:text-moonlight">
            {plan.rationale}
          </div>
          <div
            data-testid="midnight-oil-spend-auth"
            className="mt-1 text-[10px] uppercase text-shadow-1 dark:text-moonlight"
          >
            spend_authorized={String(plan.spend_authorized)} · {plan.authority}
          </div>
        </div>
      ) : (
        <div
          data-testid="midnight-oil-preflight-blocked"
          className="font-mono text-[11px] text-shadow-1 dark:text-moonlight"
        >
          Preflight blocked: {plan.reason}
        </div>
      )}

      <label className="flex items-start gap-2 text-[12px] text-ink dark:text-bright">
        <input
          type="checkbox"
          data-testid="midnight-oil-ack"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
          className="mt-0.5"
        />
        <span>
          I approve requesting this price ceiling for unattended research. The
          server may still reject or adjust; this is not a spend hold.
        </span>
      </label>

      <button
        type="button"
        data-testid="midnight-oil-request"
        disabled={!plan.ok || !ack}
        className={
          "rounded border px-3 py-1.5 font-mono text-[10px] uppercase " +
          (plan.ok && ack
            ? "border-sun bg-sun/15 text-ink dark:text-bright"
            : "cursor-not-allowed border-rule opacity-50 dark:border-charcoal-1")
        }
        onClick={() => {
          const req = requestMidnightOilApproval(plan, ack);
          if (!req.ok) {
            setError(req.reason);
            setRequestJson(null);
            return;
          }
          setError(null);
          setRequestJson(JSON.stringify(req, null, 2));
          // Living Werner: operator requested unattended swarm — thinking beat.
          // Spend still server-owned; this is intent, not launch authority.
          emitWernerExperience("deep_research_start");
        }}
      >
        Request approval
      </button>

      {error ? (
        <div
          data-testid="midnight-oil-error"
          className="font-mono text-[11px] text-emperor"
        >
          {error}
        </div>
      ) : null}
      {requestJson ? (
        <pre
          data-testid="midnight-oil-request-json"
          className="max-h-40 overflow-auto rounded bg-ice-1 p-2 font-mono text-[10px] text-ink dark:bg-charcoal-2 dark:text-bright"
        >
          {requestJson}
        </pre>
      ) : null}
    </section>
  );
}

export default MidnightOilPanel;
