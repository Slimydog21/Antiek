import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import Werner from "../../brand/Werner";
import observatoryEnvironment from "../../brand/werner/brainstorm/curiosity_observatory_environment_v1.webp";
import { track } from "../../lib/analytics";
import {
  launchParkedQuestion,
  listWatchForLater,
  type ParkedQuestionEntry,
} from "../../lib/api";
import { PanelHost } from "../../workspace/PanelHost";
import ParkedQuestion from "./ParkedQuestion";
import WatchForLaterFolder from "./WatchForLaterFolder";
import "./curiosity-observatory.css";

export interface BrainstormStationProps {
  loadQuestions?: typeof listWatchForLater;
  launchQuestion?: typeof launchParkedQuestion;
  /** Deterministic central-surface stories omit self-fetching workspace panels. */
  withWorkspacePanels?: boolean;
  /** Story fixtures freeze local ambience; production remains animated. */
  animateAmbience?: boolean;
}

const STARTER_PANELS = [
  {
    kind: "BrainstormWatchList" as const,
    mode: "docked-left" as const,
    title: "Watch for later",
    id: "brainstorm:watchlist",
  },
  {
    kind: "BrainstormThoughtPartner" as const,
    mode: "docked-right" as const,
    title: "Thought partner",
    id: "brainstorm:thought-partner",
  },
];

/**
 * The Curiosity Observatory is the central desk of the brainstorming
 * workstation. PanelHost continues to own the watch list and thought-partner
 * wings; this component owns only the honest central question lifecycle.
 */
export default function BrainstormStation({
  loadQuestions = listWatchForLater,
  launchQuestion = launchParkedQuestion,
  withWorkspacePanels = true,
  animateAmbience = true,
}: BrainstormStationProps = {}) {
  const [parked, setParked] = useState<ParkedQuestionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [launchError, setLaunchError] = useState(false);
  const [selected, setSelected] = useState<ParkedQuestionEntry | null>(null);
  const [launching, setLaunching] = useState(false);
  const mounted = useRef(true);
  const loadGeneration = useRef(0);
  const launchGeneration = useRef(0);
  const launchInFlight = useRef(false);
  const navigate = useNavigate();

  useEffect(() => {
    // React StrictMode replays setup → cleanup → setup in development.
    mounted.current = true;
    return () => {
      mounted.current = false;
      loadGeneration.current += 1;
      launchGeneration.current += 1;
      launchInFlight.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    const generation = ++loadGeneration.current;
    setLoading(true);
    setLoadError(false);
    try {
      const response = await loadQuestions({ limit: 200 });
      if (!mounted.current || generation !== loadGeneration.current) return;
      setParked(response.questions);
      setSelected((current) =>
        response.questions.find((question) => question.question_id === current?.question_id) ??
        response.questions[0] ??
        null,
      );
    } catch {
      if (!mounted.current || generation !== loadGeneration.current) return;
      setLoadError(true);
    } finally {
      if (mounted.current && generation === loadGeneration.current) setLoading(false);
    }
  }, [loadQuestions]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleLaunch = useCallback(
    async (question: ParkedQuestionEntry) => {
      if (launchInFlight.current) return;
      launchInFlight.current = true;
      const generation = ++launchGeneration.current;
      setLaunching(true);
      setLaunchError(false);
      try {
        const handle = await launchQuestion(question.question_id);
        if (!mounted.current || generation !== launchGeneration.current) return;
        track("brainstorm_question_launched");
        // Refresh is best-effort presentation cleanup. The successful launch
        // handle remains authoritative even if that refresh cannot complete.
        await reload();
        if (!mounted.current || generation !== launchGeneration.current) return;
        navigate(`/inv/${handle.investigation_id}`);
      } catch {
        if (!mounted.current || generation !== launchGeneration.current) return;
        setLaunchError(true);
      } finally {
        if (mounted.current && generation === launchGeneration.current) {
          launchInFlight.current = false;
          setLaunching(false);
        }
      }
    },
    [launchQuestion, navigate, reload],
  );

  const centralSurface = (
    <main
      className={`curiosity-observatory relative isolate h-full overflow-y-auto ${animateAmbience ? "" : "curiosity-observatory--still"}`}
      aria-busy={loading || launching || undefined}
    >
      <img
        src={observatoryEnvironment}
        alt=""
        aria-hidden="true"
        data-testid="curiosity-observatory-environment"
        decoding="sync"
        draggable={false}
        className="pointer-events-none absolute inset-0 -z-20 h-full w-full select-none object-cover object-center"
      />
      <div className="curiosity-observatory__veil pointer-events-none absolute inset-0 -z-10" />

      <header className="curiosity-observatory__masthead">
        <div>
          <p className="curiosity-observatory__eyebrow">Antiek · curiosity desk</p>
          <h1>Curiosity observatory</h1>
          <p>Questions wait here without losing where they came from.</p>
        </div>
        <div className="curiosity-observatory__count" aria-label={`${parked.length} parked ${parked.length === 1 ? "question" : "questions"}`}>
          <strong>{parked.length}</strong>
          <span>parked</span>
        </div>
      </header>

      <div className="curiosity-observatory__stage">
        <aside className="curiosity-observatory__werner" aria-label="Werner's fixed thought station">
          <Werner
            mood={loadError || launchError ? "empty" : loading || selected ? "thinking" : "idle"}
            size={104}
            label={loading ? "Werner checking the observatory" : "Werner at the thought station"}
          />
          <span aria-hidden="true" className="curiosity-observatory__lamp" />
        </aside>

        <section className="curiosity-observatory__desk" aria-label="Question desk">
          {loadError && (
            <div role="alert" className="curiosity-observatory__notice curiosity-observatory__notice--error">
              <div>
                <strong>The observatory could not refresh.</strong>
                <p>{parked.length > 0 ? "Showing the last questions received." : "No question list is available yet."}</p>
              </div>
              <button type="button" onClick={() => void reload()}>Try again</button>
            </div>
          )}

          {launchError && (
            <div role="alert" className="curiosity-observatory__notice curiosity-observatory__notice--error">
              <div>
                <strong>That question stayed parked.</strong>
                <p>No investigation was opened. You can try again when ready.</p>
              </div>
            </div>
          )}

          {loading && parked.length === 0 && !loadError ? (
            <div role="status" aria-live="polite" className="curiosity-observatory__state">
              <span className="curiosity-observatory__orbit motion-safe:animate-spin" aria-hidden="true" />
              <h2>Listening for unfinished questions…</h2>
              <p>Reopening their source trails before placing anything on the desk.</p>
            </div>
          ) : selected ? (
            <div className="curiosity-observatory__question">
              <ParkedQuestion
                question={selected}
                launching={launching}
                onLaunch={() => void handleLaunch(selected)}
              />
            </div>
          ) : !loadError ? (
            <EmptyState />
          ) : null}
        </section>
      </div>

      {parked.length > 0 && (
        <div className="curiosity-observatory__mobile-list md:hidden">
          <WatchForLaterFolder
            questions={parked}
            loading={false}
            error={null}
            selectedId={selected?.question_id ?? null}
            onSelect={(question) => {
              setLaunchError(false);
              setSelected(question);
            }}
          />
        </div>
      )}
    </main>
  );

  return withWorkspacePanels ? (
    <PanelHost starters={STARTER_PANELS}>{centralSurface}</PanelHost>
  ) : centralSurface;
}

function EmptyState() {
  return (
    <div className="curiosity-observatory__state" data-testid="curiosity-observatory-empty">
      <p className="curiosity-observatory__state-kicker">The desk is clear</p>
      <h2>Nothing is waiting to be chased.</h2>
      <p>
        As you read and research, unfinished questions can be parked here with
        their source intact. Werner will keep the station warm until one arrives.
      </p>
    </div>
  );
}
