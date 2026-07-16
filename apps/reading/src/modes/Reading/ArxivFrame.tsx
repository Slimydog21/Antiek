import { useCallback, useEffect, useRef, useState } from "react";

import { LemonButton } from "../../components/lemon";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * ArxivFrame — the T2/T3 link-back surface (Read SPR-05 M2).
 *
 * For a gated (T2, CC-BY-NC) or unknown/default (T3) arXiv paper, Antiek hosts
 * NO body — the rights law (body-serving is {T1}-only) forbids it. The reader
 * does NOT show a hosted body or any ad slot here; it shows a prominent,
 * RELIABLE link back to the paper on arxiv.org (the canonical abstract page),
 * which is the source-of-record the reader can always reach.
 *
 * The primary, always-correct surface is the link CARD. We additionally make a
 * BEST-EFFORT attempt to embed arxiv.org in an <iframe> as a convenience — but
 * arxiv.org generally refuses framing (X-Frame-Options / frame-ancestors CSP),
 * so the iframe is treated as an enhancement that must fail GRACEFULLY:
 *
 *   • the link card is shown immediately and always;
 *   • the iframe is mounted hidden and only revealed if it loads in time;
 *   • a short timeout (no `load` within the budget) keeps the card as the
 *     surface — we never block the reader on a frame that won't come.
 *
 * RIGHTS / NETWORK INVARIANT: the iframe's `src` is the arxiv.org canonical URL
 * directly. The browser loads it browser→arXiv. Antiek NEVER fetches or proxies
 * arXiv bytes — there is no Antiek round-trip for this content, by construction.
 *
 * HONESTY NOTE: whether arxiv.org actually frames cannot be verified in a
 * sandbox (no network, jsdom has no real frame navigation). The component is
 * built so the WORST case (frame never loads) is the EXPECTED, fully-functional
 * case (the link card). Live framing behaviour is an operator live-check.
 */

export interface ArxivFrameProps {
  /** The arxiv.org/abs canonical URL (from the gate response's canonical_url). */
  canonicalUrl: string;
  title: string | null;
  author: string | null;
  /** Attribution label differs by tier; the surface is otherwise identical. */
  tier: "T2" | "T3";
  /** Frame-load grace period (ms) before we settle on the link card. Injectable
   *  for tests so they don't wait on a real timer. */
  frameTimeoutMs?: number;
}

type FrameState = "trying" | "loaded" | "fallback";

export default function ArxivFrame({
  canonicalUrl,
  title,
  author,
  tier,
  frameTimeoutMs = 4000,
}: ArxivFrameProps) {
  const [frame, setFrame] = useState<FrameState>("trying");
  const settledRef = useRef(false);

  // Best-effort frame: if arxiv.org hasn't framed within the grace period, we
  // settle on the link card. A real `load` (rare for arxiv) reveals the frame.
  useEffect(() => {
    settledRef.current = false;
    setFrame("trying");
    const t = setTimeout(() => {
      if (!settledRef.current) {
        settledRef.current = true;
        setFrame("fallback");
      }
    }, frameTimeoutMs);
    return () => clearTimeout(t);
  }, [canonicalUrl, frameTimeoutMs]);

  const onFrameLoad = useCallback(() => {
    if (settledRef.current) return;
    settledRef.current = true;
    setFrame("loaded");
  }, []);
  const onFrameError = useCallback(() => {
    if (settledRef.current) return;
    settledRef.current = true;
    setFrame("fallback");
  }, []);

  // Attach `load`/`error` as PLAIN DOM listeners via a callback ref rather than
  // React's synthetic onLoad/onError. For media/iframe elements React's
  // synthetic `error` handling is unreliable across browsers (and does not fire
  // in jsdom), so a frame that the browser refuses to load — exactly arxiv.org's
  // X-Frame-Options refusal — might never settle. A direct listener catches both
  // the rare real `load` and the common `error`, so the surface always settles.
  const attachFrame = useCallback(
    (el: HTMLIFrameElement | null) => {
      if (!el) return;
      el.addEventListener("load", onFrameLoad);
      el.addEventListener("error", onFrameError);
    },
    [onFrameLoad, onFrameError],
  );

  const noticeText =
    tier === "T2"
      ? "This paper is shared under a non-commercial license, so it’s read on arXiv rather than hosted here."
      : "This paper’s reuse rights aren’t established for hosting, so it’s read on arXiv — the authoritative source.";

  return (
    <section
      aria-label="Read on arXiv"
      data-arxiv-frame
      data-frame-state={frame}
      // The canonical arxiv.org target, DOM-inspectable for the rights/network
      // invariant (the link points browser→arXiv, never a proxied Antiek URL).
      // Carried as a data attr so the test can assert the target even though the
      // redundant bare-URL anchor was trimmed (the CTA + Attribution's link are
      // the two surfaced links; three to the same URL was noise).
      data-canonical-url={canonicalUrl}
      className="flex flex-col gap-3"
    >
      {/* The RELIABLE primary surface — always rendered, always correct. */}
      <div className="border-edge border-sun rounded-hog bg-ice-1 dark:bg-charcoal-1 shadow-z1 dark:shadow-z1-night px-4 py-4 flex flex-col gap-3">
        <h2 className="font-serif text-lg text-ink dark:text-bright">
          {title ?? "This paper"}
        </h2>
        {author && (
          <p className="text-[12px] font-mono text-shadow-1 dark:text-moonlight">{author}</p>
        )}
        <p className="text-[13px] text-ink dark:text-bright">{noticeText}</p>
        {/* The single surfaced link to arXiv from this frame: the "Read on
            arXiv" CTA (Attribution's "via arXiv" provenance link is the other —
            two, not three, links to the same URL; the redundant bare full-URL
            anchor was trimmed as noise). window.open carries the canonical URL;
            it is also on the section's data-canonical-url for DOM inspection. */}
        <div>
          <LemonButton
            type="button"
            onClick={() => {
              // Living-TV: arXiv link-back is a curious highlight glance.
              emitWernerExperience("highlight");
              window.open(canonicalUrl, "_blank", "noreferrer,noopener");
            }}
          >
            Read on arXiv ↗
          </LemonButton>
        </div>
      </div>

      {/* Best-effort embed: hidden unless it genuinely loads. arxiv.org usually
          refuses framing, so `fallback` (the default settle) is expected — the
          card above is the surface. NEVER proxied: src is arxiv.org directly. */}
      {frame !== "fallback" && (
        <iframe
          ref={attachFrame}
          src={canonicalUrl}
          title="arXiv paper (best-effort embed)"
          sandbox="allow-scripts allow-same-origin allow-popups"
          referrerPolicy="no-referrer"
          className={
            frame === "loaded"
              ? "w-full h-[70vh] border-edge border-rule dark:border-charcoal-1 rounded-md bg-ice-0 dark:bg-charcoal-2"
              : "hidden"
          }
        />
      )}
    </section>
  );
}
