import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import { PanelHost } from "../../workspace/PanelHost";
import { track } from "../../lib/analytics";
import {
  launchParkedQuestion,
  listWatchForLater,
  type ParkedQuestionEntry,
} from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";
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
        track("brainstorm_question_launched");
        // Living-TV: launching a parked question starts deep research.
        emitWernerExperience("deep_research_start");
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

  // S10 row 10.8 — BrainstormStation wraps the main parked-question
  // view in PanelHost with the spec's two side panels as starters.
  // The watch-list panel self-fetches (mirrors the parent's `parked`
  // state independently); the thought-partner panel surfaces a CTA
  // to ⌘/ the AISidecar (the actual thought-partner pane).
  return (
    <PanelHost
      starters={[
        {
          kind: "BrainstormWatchList",
          mode: "docked-left",
          title: "Watch for later",
          id: "brainstorm:watchlist",
        },
        {
          kind: "BrainstormThoughtPartner",
          mode: "docked-right",
          title: "Thought partner",
          id: "brainstorm:thought-partner",
        },
      ]}
    >
      <main className="h-full overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        {selected ? (
          <ParkedQuestion
            question={selected}
            launching={launching}
            onLaunch={() => handleLaunch(selected)}
          />
        ) : (
          <EmptyState parkedCount={parked.length} />
        )}
        {/* Inline watch-for-later kept for operators on small screens
            where the dock auto-collapses. Empty rendering when the
            list is empty avoids a duplicate empty-state. */}
        {parked.length > 0 && (
          <div className="md:hidden border-t border-rule dark:border-charcoal-1">
            <WatchForLaterFolder
              questions={parked}
              loading={loading}
              error={error}
              selectedId={selected?.question_id ?? null}
              onSelect={setSelected}
            />
          </div>
        )}
      </main>
    </PanelHost>
  );
}

function EmptyState({ parkedCount }: { parkedCount: number }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md text-center space-y-3">
        <div className="flex flex-col items-center gap-2">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="brainstorm-empty-werner-brand"
            className="h-14 w-14 object-contain"
          />
          <img
            src={livingTvArt}
            alt=""
            aria-hidden="true"
            data-testid="brainstorm-empty-living-tv-art"
            className="h-14 w-full max-w-sm rounded-md object-cover object-center antiek-living-tv-invent"
            loading="lazy"
            decoding="async"
          />
        </div>
        <h2 className="text-lg font-serif text-ink dark:text-bright">
          The watch-for-later folder
        </h2>
        <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
          Research is gated by curiosity, not by tooling. Curiosity
          surfaces in fragments throughout the day. This folder is
          where unsharpened questions live until you decide to chase
          them.
        </p>
        {parkedCount === 0 ? (
          <p className="text-xs text-shadow-1 dark:text-moonlight italic">
            No parked questions yet. As you wrestle with documents
            and run investigations, the substrate identifies open
            questions and parks them here.
          </p>
        ) : (
          <p className="text-xs text-shadow-1 dark:text-moonlight">
            Select a question on the left to see its context and
            launch an investigation.
          </p>
        )}
      </div>
    </div>
  );
}

// ThoughtPartnerPlaceholder superseded by ThoughtPartnerPanel
// (registered as PanelKind="BrainstormThoughtPartner" + opened as a
// docked-right starter via PanelHost).
