import { useState } from "react";

import { emitWernerExperience } from "../../../werner/reactionBus";
import { emitBrainstormBlocks, type BrainstormEmitResult } from "../writeApi";
import { canAskMore, initClarify, recordTurn, type ClarifyState } from "./clarifyLoop";

/**
 * Brainstorm idea-dump → lego blocks (specs/write/ SPR-05).
 *
 * Dump a raw idea (text; voice reuses the existing VoiceNoteCapture where
 * mounted). The agent identifies the insights / questions / data driving
 * it and asks clarifying questions, bounded by the turn cap
 * (``clarifyLoop`` — tested). The confirmed drivers become OutlineBlocks
 * marked **brainstorm-originated** (user-originated provenance; asserted
 * data flagged unverified — no fabricated citation), via
 * ``POST /write/brainstorm/emit-blocks``.
 *
 * Honesty (rigor #1): the live driver auto-identification is an LLM pass
 * that, like SPR-06 generation, needs the interviewer role wired into the
 * dispatch config. Until then the surface has the operator confirm/edit
 * the identified drivers — it never silently invents "data" the writer
 * didn't assert, and asserted data is flagged as a claim to verify.
 */
export interface IdeaDumpProps {
  sectionId: string;
  deliverableId?: string;
  className?: string;
}

function lines(text: string): string[] {
  return text.split("\n").map((l) => l.trim()).filter(Boolean);
}

export function IdeaDump({ sectionId, deliverableId, className }: IdeaDumpProps) {
  const [idea, setIdea] = useState("");
  const [insights, setInsights] = useState("");
  const [questions, setQuestions] = useState("");
  const [data, setData] = useState("");
  const [clarify, setClarify] = useState<ClarifyState>(initClarify());
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BrainstormEmitResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasDrivers = lines(insights).length + lines(questions).length + lines(data).length > 0;

  async function onEmit() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await emitBrainstormBlocks({
        section_id: sectionId,
        deliverable_id: deliverableId,
        insights: lines(insights),
        questions: lines(questions),
        data_points: lines(data),
      });
      setResult(r);
      // Living-TV: brainstorm drivers became lego blocks — happy craft.
      emitWernerExperience("piece_started");
    } catch (e) {
      setError(String(e));
      emitWernerExperience("fail");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={"flex flex-col gap-3 p-4 " + (className ?? "")} data-mode="write-idea-dump">
      <label className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
        Dump an idea
      </label>
      <textarea
        value={idea}
        onChange={(e) => setIdea(e.target.value)}
        rows={3}
        placeholder="Think aloud here (text or voice). The agent identifies what's driving it."
        className="px-3 py-2 border border-rule dark:border-charcoal-1 rounded font-serif focus:outline-none focus:ring-2 focus:ring-sun"
      />

      {/* Clarifying-question loop — bounded by the turn cap. */}
      <div className="flex items-center gap-2 text-xs text-ink-mute">
        <span>
          Clarification {clarify.turns}/{clarify.maxTurns}
          {clarify.done ? ` · ended (${clarify.endReason})` : ""}
        </span>
        <button
          type="button"
          disabled={!canAskMore(clarify)}
          onClick={() => setClarify((s) => recordTurn(s, { shouldEnd: false }))}
          className="px-2 py-0.5 rounded border border-rule disabled:opacity-40 hover:border-ocean"
        >
          Ask a clarifying question
        </button>
        <button
          type="button"
          disabled={clarify.done}
          onClick={() => setClarify((s) => recordTurn(s, { shouldEnd: true }))}
          className="px-2 py-0.5 rounded border border-rule disabled:opacity-40 hover:border-ocean"
        >
          Done clarifying
        </button>
      </div>

      {/* Driver review — confirm/edit what's driving the idea (one per line). */}
      <div className="grid grid-cols-3 gap-2">
        <DriverColumn label="Insights" value={insights} onChange={setInsights} />
        <DriverColumn label="Questions" value={questions} onChange={setQuestions} />
        <DriverColumn
          label="Data (to verify)"
          value={data}
          onChange={setData}
          hint="Asserted data is flagged unverified — a claim to verify, not established fact."
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onEmit}
          disabled={busy || !hasDrivers}
          className="px-3 py-1.5 bg-ink hover:bg-shadow-2 disabled:bg-glacial-1 text-white text-sm rounded"
        >
          {busy ? "Taking notes…" : "Emit lego blocks"}
        </button>
        {!hasDrivers && (
          <span className="text-xs text-ink-mute">Add at least one insight, question, or data point.</span>
        )}
      </div>

      {error && <p className="text-xs text-emperor">{error}</p>}
      {result && (
        <p className="text-xs text-shadow-1">
          Placed {result.block_ids.length} block(s): {result.insight_count} insight,{" "}
          {result.question_count} question, {result.data_count} data
          {result.flagged_unverified.length > 0
            ? ` (${result.flagged_unverified.length} flagged unverified)`
            : ""}
          {result.skipped_duplicates > 0 ? ` · ${result.skipped_duplicates} duplicate(s) skipped` : ""}.
        </p>
      )}
    </div>
  );
}

function DriverColumn({
  label, value, onChange, hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-semibold text-ink-soft">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={4}
        placeholder="one per line"
        className="px-2 py-1.5 text-sm border border-rule dark:border-charcoal-1 rounded font-serif focus:outline-none focus:ring-2 focus:ring-sun"
      />
      {hint && <span className="text-[10px] text-ink-mute leading-tight">{hint}</span>}
    </div>
  );
}

export default IdeaDump;
