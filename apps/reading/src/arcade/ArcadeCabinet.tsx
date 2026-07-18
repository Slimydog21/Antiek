import { useMemo, useState } from "react";

import { ArcadeMount } from "./engine/ArcadeMount";
import {
  createArcadeCartridge,
  type ArcadeGameKind,
} from "./cartridgeFactory";
import { emitProductActivate } from "../components/hotkeys";
import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { emitLivingTvHostBeat } from "./host/livingTvHostEmit";
// Session brand PNGs — UI-consumed cabinet key art + chrome marks.
// Inventory: brand/werner/sessionAssets.ts (alpha integrity gated).
// Igloo ice-arcade invent — CRT + cursor-bait cabinet card (align LGH + wait-arcade).
import iceFishingArt from "../brand/werner/poses/session/werner_igloo_ice_arcade_cursor_session_v1.webp";
import zombiesArt from "../brand/werner/poses/session/werner_paperclip_zombies_arcade_session_v1.webp";
import thinkingArt from "../brand/werner/poses/session/werner_thinking_session_v1.png";
import celebrateArt from "../brand/werner/poses/session/werner_celebrate_session_v1.png";
// Clam Catcher: session Imagine refedit promoted via cut_session_fringe (2026-07-16).
// Authored webp remains for in-game station chrome / visual kit only.
import clamCatcherArt from "../brand/werner/poses/session/werner_clam_catcher_cursor_session_v1.webp";
// Igloo minigame trio invent — ice fishing + clam + paperclip zombies in one cabinet banner.
import iglooArcadeArt from "../brand/werner/poses/session/werner_igloo_minigame_trio_session_v1.webp";

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
        ? createArcadeCartridge(active, {
            reducedMotion: reduced,
            // Host injects living-TV without reactionBus import (arcade boundary).
            onWernerBeat: emitLivingTvHostBeat,
          })
        : null,
    [active, reduced],
  );

  function playGame(game: CabinetGame) {
    // Living-TV: per-game product door (ice-fishing / clam-catcher / zombies →
    // curious) so cabinet cards resolve as distinct living-TV geometry.
    emitProductActivate({ productId: game, source: "click" });
    emitLivingTvHostBeat("highlight");
    setActive(game);
  }

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
          Club Penguin–inspired Ice Fishing and Clam Catcher, plus a wholesome
          Paperclip Zombies easter egg for long deep-research waits. Opt-in only
          — never blocks work.
        </p>
      </header>

      <img
        src={iglooArcadeArt}
        alt=""
        aria-hidden="true"
        data-testid="cabinet-igloo-art"
        className="h-32 w-full max-w-2xl rounded-lg object-cover object-center antiek-living-tv-invent"
        loading="lazy"
        decoding="async"
      />

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

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <CabinetCard
          title="Ice Fishing"
          blurb="Drop the line. Catch fish. Avoid the boot."
          art={iceFishingArt}
          productId="ice-fishing"
          selected={active === "ice-fishing"}
          onPlay={() => playGame("ice-fishing")}
          testId="cabinet-ice-fishing"
        />
        <CabinetCard
          title="Clam Catcher"
          blurb="Scoop clams on the tide. Club Penguin energy."
          art={clamCatcherArt}
          productId="clam-catcher"
          selected={active === "clam-catcher"}
          onPlay={() => playGame("clam-catcher")}
          testId="cabinet-clam-catcher"
        />
        <CabinetCard
          title="Paperclip Zombies"
          blurb="Defend the fort while research runs."
          art={zombiesArt}
          productId="zombies"
          selected={active === "zombies"}
          onPlay={() => playGame("zombies")}
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
  productId,
  selected,
  onPlay,
  testId,
}: {
  title: string;
  blurb: string;
  art: string;
  productId: CabinetGame;
  selected: boolean;
  onPlay: () => void;
  testId: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      data-product-id={productId}
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
        data-testid={`${testId}-living-tv-art`}
        className="h-36 w-full object-cover object-top antiek-living-tv-invent"
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
