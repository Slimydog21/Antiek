import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import Werner from "../../brand/Werner";
import { LemonButton } from "../../components/lemon";
import { createPerson, listPeople, type RememberedPerson } from "../../lib/speakApi";
import AIActionFailure from "../../shared/AIActionFailure";

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
 */
export default function SpeakIndex() {
  const navigate = useNavigate();
  const [people, setPeople] = useState<RememberedPerson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    void reload();
  }, [reload]);

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
          <Werner mood="idle" size={44} />
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

        {loading ? (
          <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
            Loading…
          </p>
        ) : people.length === 0 ? (
          <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
            No one yet — name the first person above.
          </p>
        ) : (
          <section>
            <h2 className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
              The people you're remembering
            </h2>
            <ul className="space-y-2">
              {people.map((p) => (
                <li key={p.id}>
                  <Link
                    to={`/speak/${p.id}`}
                    className="block rounded-md border-2 border-ink bg-ice-0 p-3 shadow-z1 transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-serif text-[16px] text-ink dark:text-bright">
                        {p.name}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] text-ink-mute dark:text-moonlight">
                        {p.voiceCount === 0
                          ? "no voices yet"
                          : `${p.voiceCount} voice${p.voiceCount === 1 ? "" : "s"}`}
                      </span>
                    </div>
                    <p className="mt-0.5 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                      {p.willBePublic ? "Will be shared publicly" : "Kept private"}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
