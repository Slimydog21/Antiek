import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  launchParkedQuestion,
  listWatchForLater,
  type ParkedQuestionEntry,
} from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";
import ParkedQuestion from "./ParkedQuestion";
import WatchForLaterFolder from "./WatchForLaterFolder";

/**
 * Mode E — Brainstorming Workstation.
 *
 * Operator's stated preferred product direction (master-spec §4.5).
 * The surface where curiosity-capture-as-primitive lives (§2.6).
 *
 * Sprint 17 scope (per docs/sprints/sprint17-*.md §1.6):
 *   - Watch-for-later folder: parked unsharpened open questions
 *     across all investigations
 *   - Launch-investigation affordance per parked question
 *   - Voice-note input placeholder (full ship Sprint 18)
 *   - Thought-partner pane placeholder (full ship Sprint 18 with
 *     the new `thought_partner` role)
 *
 * Three columns:
 *   Left  — Watch-for-later folder (parked questions)
 *   Center — Selected parked question detail + launch button
 *   Right — Thought-partner pane (Sprint 18 placeholder)
 */
export default function BrainstormStation() {
  const [parked, setParked] = useState<ParkedQuestionEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ParkedQuestionEntry | null>(null);
  const [launching, setLaunching] = useState<boolean>(false);
  const navigate = useNavigate();

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listWatchForLater({ limit: 200 });
      setParked(resp.questions);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleLaunch = useCallback(
    async (q: ParkedQuestionEntry) => {
      setLaunching(true);
      try {
        const handle = await launchParkedQuestion(q.question_id);
        // The folder reloads to hide this question (now sharpened);
        // operator follows the launched investigation in Mode A.
        await reload();
        navigate(`/inv/${handle.investigation_id}`);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(`Launch failed: ${msg}`);
      } finally {
        setLaunching(false);
      }
    },
    [navigate, reload],
  );

  return (
    <div className="flex flex-col h-screen">
      <HeaderBar>
        <span className="text-xs text-stone-500">
          {loading
            ? "loading…"
            : `${parked.length} parked ${parked.length === 1 ? "question" : "questions"}`}
        </span>
      </HeaderBar>
      <div className="grid grid-cols-[340px_1fr_320px] flex-1 min-h-0">
        <aside className="border-r border-stone-200 bg-stone-50 overflow-y-auto">
          <WatchForLaterFolder
            questions={parked}
            loading={loading}
            error={error}
            selectedId={selected?.question_id ?? null}
            onSelect={setSelected}
          />
        </aside>
        <main className="flex flex-col min-h-0 bg-white overflow-y-auto">
          {selected ? (
            <ParkedQuestion
              question={selected}
              launching={launching}
              onLaunch={() => handleLaunch(selected)}
            />
          ) : (
            <EmptyState parkedCount={parked.length} />
          )}
        </main>
        <aside className="border-l border-stone-200 bg-stone-50 overflow-y-auto">
          <ThoughtPartnerPlaceholder />
        </aside>
      </div>
    </div>
  );
}

function EmptyState({ parkedCount }: { parkedCount: number }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md text-center space-y-3">
        <h2 className="text-lg font-serif text-stone-900">
          The watch-for-later folder
        </h2>
        <p className="text-sm text-stone-600 leading-relaxed">
          Research is gated by curiosity, not by tooling. Curiosity
          surfaces in fragments throughout the day. This folder is
          where unsharpened questions live until you decide to chase
          them.
        </p>
        {parkedCount === 0 ? (
          <p className="text-xs text-stone-500 italic">
            No parked questions yet. As you wrestle with documents
            and run investigations, the substrate identifies open
            questions and parks them here.
          </p>
        ) : (
          <p className="text-xs text-stone-500">
            Select a question on the left to see its context and
            launch an investigation.
          </p>
        )}
      </div>
    </div>
  );
}

function ThoughtPartnerPlaceholder() {
  return (
    <div className="p-4 space-y-3">
      <h3 className="text-sm font-semibold text-stone-900">
        Thought partner
      </h3>
      <p className="text-xs text-stone-500 leading-relaxed">
        Talk to your notes. Slot insights like Legos. Challenge them.
      </p>
      <div className="border border-dashed border-stone-300 rounded-md p-4 text-xs text-stone-400 italic">
        Sprint 18 — the `thought_partner` role and Lego-block
        insight slotting from your private graph ship here.
      </div>
      <div className="border border-dashed border-stone-300 rounded-md p-4 text-xs text-stone-400 italic">
        Sprint 18 — voice-note input: talk through a thought, the
        system transcribes, extracts insights + open questions,
        parks the questions in this folder by default.
      </div>
    </div>
  );
}
