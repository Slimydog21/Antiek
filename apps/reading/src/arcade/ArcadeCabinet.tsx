import { useMemo, useState } from "react";

import { ArcadeMount } from "./engine/ArcadeMount";
import {
  createArcadeCartridge,
  type ArcadeGameKind,
} from "./cartridgeFactory";
import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
// Session brand PNGs — UI-consumed cabinet key art + chrome marks.
// Inventory: brand/werner/sessionAssets.ts (alpha integrity gated).
import iceFishingArt from "../brand/werner/poses/session/werner_ice_fishing_session_v1.png";
import zombiesArt from "../brand/werner/poses/session/werner_zombies_session_v1.png";
import thinkingArt from "../brand/werner/poses/session/werner_thinking_session_v1.png";
import celebrateArt from "../brand/werner/poses/session/werner_celebrate_session_v1.png";

type CabinetGame = ArcadeGameKind;

/**
 * Club-Penguin-style arcade cabinet — page host for mini-games.
 * Opt-in only; never auto-launches over primary research/reading UI.
 */
export function ArcadeCabinet() {
  const reduced = usePrefersReducedMotion();
  const [active, setActive] = useState<CabinetGame | null>(null);

  const cartridge = useMemo(
    () =>
      active
        ? createArcadeCartridge(active, { reducedMotion: reduced })
        : null,
    [active, reduced],
  );

  return (
    <div
      data-testid="arcade-cabinet"
      className="flex h-full flex-col gap-4 overflow-auto p-6"
    >
      <header>
        <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1">
          Werner&apos;s igloo · arcade
        </p>
        <h1 className="text-xl font-bold text-ink dark:text-bright">
          Mini-games
        </h1>
        <p className="mt-1 max-w-xl text-sm text-ink-mute dark:text-moonlight">
          Club Penguin–inspired Ice Fishing and a wholesome Paperclip Zombies
          easter egg for long deep-research waits. Opt-in only — never blocks
          work.
        </p>
      </header>

      <div
        className="flex items-center gap-3"
        data-testid="cabinet-session-brand"
      >
        <img
          src={thinkingArt}
          alt="Werner thinking"
          data-testid="cabinet-brand-thinking"
          className="h-14 w-14 object-contain"
        />
        <img
          src={celebrateArt}
          alt="Werner celebrating"
          data-testid="cabinet-brand-celebrate"
          className="h-14 w-14 object-contain"
        />
        <span className="text-xs text-ink-mute dark:text-moonlight">
          Session brand marks (thinking + celebrate) + game key art drive the
          cabinet chrome — Imagine-refined, alpha-gated PNGs.
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <CabinetCard
          title="Ice Fishing"
          blurb="Drop the line. Catch fish. Avoid the boot."
          art={iceFishingArt}
          selected={active === "ice-fishing"}
          onPlay={() => setActive("ice-fishing")}
          testId="cabinet-ice-fishing"
        />
        <CabinetCard
          title="Paperclip Zombies"
          blurb="Defend the fort while research runs."
          art={zombiesArt}
          selected={active === "zombies"}
          onPlay={() => setActive("zombies")}
          testId="cabinet-zombies"
        />
      </div>

      {cartridge && (
        <section
          data-testid="cabinet-play-surface"
          className="rounded-lg border-2 border-sun bg-ice-0 p-3 dark:bg-charcoal-2"
        >
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{cartridge.meta.title}</h2>
            <button
              type="button"
              data-testid="cabinet-close"
              className="rounded border border-rule px-2 py-1 text-xs"
              onClick={() => setActive(null)}
            >
              Close game
            </button>
          </div>
          <ArcadeMount
            cartridge={cartridge}
            reducedMotion={reduced}
            width={480}
            height={300}
            testId="cabinet-arcade-mount"
          />
        </section>
      )}
    </div>
  );
}

function CabinetCard({
  title,
  blurb,
  art,
  selected,
  onPlay,
  testId,
}: {
  title: string;
  blurb: string;
  art: string;
  selected: boolean;
  onPlay: () => void;
  testId: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      data-werner-target="curious"
      onClick={onPlay}
      className={
        "flex flex-col overflow-hidden rounded-lg border-2 text-left transition " +
        (selected
          ? "border-sun bg-sun/10"
          : "border-rule bg-ice-0 hover:border-sun dark:bg-charcoal-2")
      }
    >
      <img
        src={art}
        alt=""
        className="h-36 w-full object-cover object-top"
        loading="lazy"
      />
      <div className="p-3">
        <div className="text-sm font-bold text-ink dark:text-bright">{title}</div>
        <div className="mt-1 text-xs text-ink-mute dark:text-moonlight">
          {blurb}
        </div>
        <div className="mt-2 text-[11px] font-mono uppercase tracking-wide text-sun-deep">
          {selected ? "Playing" : "Play"}
        </div>
      </div>
    </button>
  );
}

export default ArcadeCabinet;
