import { Link } from "react-router-dom";

import type { RememberedPerson } from "../../../lib/speakApi";

/**
 * YoursLane — the private "People you're remembering" tab body.
 *
 * SPR-01 M2 extracted this verbatim from SpeakIndex's `tab === "yours"`
 * branch so SPR-02 can own the private lane without re-editing the shell.
 * It is a PURE PRESENTATION component: it fetches nothing. The shell keeps
 * the data-fetching (`reload`/`listPeople`) and passes results down as
 * props. Behavior here is identical to what shipped in Product Depth
 * SPR-08 M1; this is a structural move, not a feature.
 *
 * SPR-02 owns this file.
 */
export interface YoursLaneProps {
  /** True while the private dashboard is loading from `listPeople`. */
  loading: boolean;
  /** The operator's invited/owned projects (humanized). */
  people: RememberedPerson[];
}

export default function YoursLane({ loading, people }: YoursLaneProps) {
  if (loading) {
    return (
      <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
        Loading…
      </p>
    );
  }

  if (people.length === 0) {
    return (
      <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
        No one yet — name the first person above.
      </p>
    );
  }

  return (
    <section>
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
              {/*
                SPR-04 M1 — private-lane gratitude / impact (no money).
                CONTRACT: split_applies == false here, so NO money/share/payout/
                earnings language ever. Gratitude is purely emotional — that
                their story is coming together as voices arrive. We have only
                voiceCount in props (no per-person corroboration data is passed
                to this lane), so the impact is grounded in it: stay honest when
                no one has shared yet, warm once a voice has.
              */}
              {p.voiceCount > 0 ? (
                <p className="mt-1 font-serif text-[12px] italic text-ink-soft dark:text-moonlight">
                  {`Their story is coming together — ${p.voiceCount} ${
                    p.voiceCount === 1 ? "voice has" : "voices have"
                  } added a memory.`}
                </p>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
