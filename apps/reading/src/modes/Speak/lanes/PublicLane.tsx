import { Link } from "react-router-dom";

import { LemonButton } from "../../../components/lemon";
import type { FeedItem } from "../../../lib/speakApi";

/**
 * PublicLane — the browsable "Public remembrances" tab body.
 *
 * SPR-01 M2 extracted this verbatim from SpeakIndex's public-feed branch
 * (the `tab === "public"` else-branch) so SPR-03 can own the public lane
 * without re-editing the shell. Each feed item carries its "Add your
 * memory" chime-in entry, and the empty state is honest — no placeholder
 * cards. It is a PURE PRESENTATION component: it fetches nothing; the shell
 * keeps the data-fetching (`reloadFeed`/`listPublicFeed`) and passes
 * results down as props. Behavior here is identical to what shipped in
 * Product Depth SPR-08 M1.
 *
 * SPR-03 owns this file.
 */
export interface PublicLaneProps {
  /** True while the public feed is loading from `listPublicFeed`. */
  feedLoading: boolean;
  /** The feed of public-intent remembrances (humanized). */
  feed: FeedItem[];
}

export default function PublicLane({ feedLoading, feed }: PublicLaneProps) {
  return (
    <section>
      {feedLoading ? (
        <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
          Loading…
        </p>
      ) : feed.length === 0 ? (
        <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
          No public remembrances yet. When someone shares a story publicly,
          it'll appear here — and you'll be able to add what you remember.
        </p>
      ) : (
        <ul className="space-y-2">
          {feed.map((f) => (
            <li
              key={f.id}
              className="rounded-md border-2 border-ink bg-ice-0 p-3 shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night"
            >
              <div className="flex items-center justify-between gap-3">
                <Link
                  to={`/speak/${f.id}`}
                  className="font-serif text-[16px] text-ink hover:underline dark:text-bright"
                >
                  {f.name}
                </Link>
                <span className="shrink-0 font-mono text-[10px] text-ink-mute dark:text-moonlight">
                  {f.voiceCount === 0
                    ? "no voices yet"
                    : `${f.voiceCount} voice${f.voiceCount === 1 ? "" : "s"}`}
                </span>
              </div>
              <div className="mt-2">
                <Link to={`/speak/${f.id}`}>
                  <LemonButton variant="secondary" size="sm">
                    Add your memory
                  </LemonButton>
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
