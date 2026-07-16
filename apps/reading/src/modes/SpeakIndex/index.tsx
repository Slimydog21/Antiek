import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import Werner from "../../brand/Werner";
import { LemonButton } from "../../components/lemon";
import { track } from "../../lib/analytics";
import {
  createPerson,
  listPeople,
  listPublicFeed,
  type FeedItem,
  type RememberedPerson,
} from "../../lib/speakApi";
import PublicLane from "../Speak/lanes/PublicLane";
import YoursLane from "../Speak/lanes/YoursLane";
import AIActionFailure from "../../shared/AIActionFailure";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * Speak home — the warm one-door entry (Product Depth SPR-08 M1).
 *
 * The operator's verdict on the old console was "no focus and looks ugly":
 * the create form was a wall of enums (subject status, publish intent) the
 * first-time user shouldn't have to reason about. This replaces it with one
 * warm question — "Who do you want to remember?" — type a name, get a
 * project, land on it. The status + publish details that used to live here
 * move BEHIND the project (one calm Settings tap, SPR-08 M4), with a safe
 * private default; they are never the first thing you see.
 *
 * This is also the ONE DOOR for interview-as-acquisition (SPR-08 M1): the
 * duplicate /interviews index now redirects here, and its substance — the
 * invitees, their recordings, corroboration — lives inside each project.
 *
 * No engineering string is shown: the substrate enums are translated at the
 * UI edge (lib/speakApi.ts); a person is named by their name, never an id.
 *
 * SPR-02 owns YoursLane; SPR-03 owns PublicLane; do not edit this shell.
 * (SPR-01 M2 froze the tab scaffold — the Tab type, the role="tablist" +
 * two buttons, the create header/form, the active-tab state, and the
 * data-fetching — and extracted each tab's body into its own lane file so
 * the two Wave-2 builders never collide on this file. The lanes receive
 * state as PROPS; they do not fetch.)
 */
type Tab = "yours" | "public";

export default function SpeakIndex() {
  const navigate = useNavigate();
  const [people, setPeople] = useState<RememberedPerson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // M1 — the public/private structure. "Yours" is the private dashboard of
  // the people you're remembering (your invited/owned projects). "Public" is
  // a browsable feed of public remembrances anyone can chime in on. They are
  // two views over the SAME shipped backend — /speak/projects (yours) and
  // /speak/feed (public) — no new store.
  const [tab, setTab] = useState<Tab>("yours");
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [feedLoading, setFeedLoading] = useState(false);

  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [createFailed, setCreateFailed] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPeople(await listPeople());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const reloadFeed = useCallback(async () => {
    setFeedLoading(true);
    try {
      setFeed(await listPublicFeed());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setFeedLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (tab === "public") void reloadFeed();
  }, [tab, reloadFeed]);

  // The one warm action: name a person → get a project → land on it. The
  // subject details + publish mode default safely (unknown / kept private)
  // and are adjustable behind the project's Settings (SPR-08 M4), never on
  // this first screen.
  const create = useCallback(async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    setCreateFailed(false);
    try {
      const id = await createPerson(name);
      track("speak_project_created");
      // Living-TV: starting a remembrance is a happy craft beat.
      emitWernerExperience("piece_started");
      navigate(`/speak/${id}`);
    } catch {
      setCreateFailed(true);
    } finally {
      setSubmitting(false);
    }
  }, [name, navigate]);

  return (
    <div className="h-full overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
      <div className="mx-auto max-w-2xl px-6 py-10">
        <header className="mb-7 flex items-start gap-3">
          {/* Session thinking mark — densify Speak door with the same living-TV
              brand chrome as Library / Research / Write (idle→thinking so the
              product path consumes session Imagine PNGs, not inventory-only). */}
          <span data-testid="speak-home-werner-brand">
            <Werner mood="thinking" size={44} label="Speak" />
          </span>
          <div>
            <h1 className="font-serif text-2xl font-semibold text-ink dark:text-bright">
              Who do you want to remember?
            </h1>
            <p className="mt-1 text-sm text-ink-soft dark:text-moonlight">
              Name someone, then invite the people who knew them. Each records
              their memories — in their own voice, on their own time — and
              their story comes together from what everyone shares.
            </p>
          </div>
        </header>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void create();
          }}
          className="mb-8 flex flex-wrap items-center gap-2 rounded-md border-2 border-ink bg-ice-0 p-3 shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night"
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="A name — e.g. my grandmother, Dad, Maria"
            aria-label="Who do you want to remember?"
            className="min-w-[220px] flex-1 rounded border border-rule bg-transparent px-3 py-2 font-serif text-[15px] text-ink focus:outline-none focus:ring-2 focus:ring-sun dark:border-charcoal-1 dark:text-bright"
          />
          <LemonButton
            type="submit"
            variant="primary"
            disabled={submitting || !name.trim()}
          >
            {submitting ? "Starting…" : "Start their story"}
          </LemonButton>
        </form>

        {createFailed && (
          <div className="mb-6">
            <AIActionFailure
              title="We couldn't start that story"
              onRetry={() => void create()}
              retryLabel="Try again"
            />
          </div>
        )}

        {error && (
          <p className="mb-3 font-mono text-[12px] text-emperor">{error}</p>
        )}

        {/* M1 — the public/private split: your dashboard vs the public feed. */}
        <div role="tablist" className="mb-4 flex gap-1 border-b border-rule dark:border-charcoal-1">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "yours"}
            onClick={() => setTab("yours")}
            className={`-mb-px border-b-2 px-3 py-2 font-mono text-[11px] uppercase tracking-wider ${
              tab === "yours"
                ? "border-sun text-ink dark:text-bright"
                : "border-transparent text-ink-mute hover:text-ink dark:text-moonlight dark:hover:text-bright"
            }`}
          >
            People you're remembering
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "public"}
            onClick={() => setTab("public")}
            className={`-mb-px border-b-2 px-3 py-2 font-mono text-[11px] uppercase tracking-wider ${
              tab === "public"
                ? "border-sun text-ink dark:text-bright"
                : "border-transparent text-ink-mute hover:text-ink dark:text-moonlight dark:hover:text-bright"
            }`}
          >
            Public remembrances
          </button>
        </div>

        {/* The tab BODIES are extracted into lane files (SPR-01 M2). The
            shell keeps the data-fetching above and passes state down as
            props; YoursLane is SPR-02's, PublicLane is SPR-03's. */}
        {tab === "yours" ? (
          <YoursLane loading={loading} people={people} />
        ) : (
          <PublicLane feedLoading={feedLoading} feed={feed} />
        )}
      </div>
    </div>
  );
}
