import { useEffect, useMemo, useState } from "react";

import { ArcadeMount } from "../engine/ArcadeMount";
import {
  createArcadeCartridge,
  type ArcadeGameKind,
} from "../cartridgeFactory";
import livingTvArt from "../../brand/werner/poses/session/werner_crt_living_tv_session_v1.webp";
import iceFishingArt from "../../brand/werner/poses/session/werner_ice_fishing_session_v1.png";
import zombiesArt from "../../brand/werner/poses/session/werner_zombies_session_v1.png";
import clamCatcherArt from "../../brand/werner/poses/session/werner_clam_catcher_session_v1.png";
import { wernerArcade } from "../../werner/iceFishingFlags";
import { emitWernerExperience } from "../../werner/reactionBus";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import {
  DEFAULT_OFFER_AFTER_MS,
  decideWaitHostMode,
  type WaitHostMode,
} from "./waitHostLogic";

export type WaitGameKind = ArcadeGameKind;

/** Session brand key art for the wait-host strip — game-specific when known. */
export function waitHostBrandArt(game: WaitGameKind): string {
  switch (game) {
    case "ice-fishing":
      return iceFishingArt;
    case "zombies":
      return zombiesArt;
    case "clam-catcher":
      return clamCatcherArt;
    default:
      return livingTvArt;
  }
}

/**
 * Living-TV offer blurb — Club Penguin–style ice/clam vs BO1 zombies egg.
 * Pure copy helper so wait UX stays honest about opt-in easter eggs.
 */
export function waitHostOfferBlurb(game: WaitGameKind): string {
  switch (game) {
    case "zombies":
      return "Easter egg: Paperclip Zombies (arcade-wave wait mode). Optional — never blocks research.";
    case "ice-fishing":
      return "Club Penguin–style ice fishing while you wait. Optional — never blocks research.";
    case "clam-catcher":
      return "Catch clams on the ice shelf. Optional — never blocks research.";
    default:
      return "Optional — never blocks research";
  }
}

export interface LoadingGameHostProps {
  /** Parent-driven: work still in flight. */
  waiting: boolean;
  /** Parent-driven: work finished — host must hide same render. */
  ready: boolean;
  /** Which cartridge to offer during wait (zombies is the DR easter egg). */
  game?: WaitGameKind;
  /** Override flag for tests. */
  arcadeEnabled?: boolean;
  offerAfterMs?: number;
  /** Visible label for the primary control that must stay unblocked. */
  primaryControlLabel?: string;
  onPrimaryContinue?: () => void;
  className?: string;
}

/**
 * Opt-in wait-state game host. Never mounts a game without explicit opt-in
 * (I4). When `ready` becomes true, game unmounts immediately.
 */
export function LoadingGameHost({
  waiting,
  ready,
  game = "zombies",
  arcadeEnabled = wernerArcade,
  offerAfterMs = DEFAULT_OFFER_AFTER_MS,
  primaryControlLabel = "Back to work",
  onPrimaryContinue,
  className,
}: LoadingGameHostProps) {
  const reduced = usePrefersReducedMotion();
  const [optedIn, setOptedIn] = useState(false);
  const [waitedMs, setWaitedMs] = useState(0);

  useEffect(() => {
    if (!waiting || ready) {
      setWaitedMs(0);
      setOptedIn(false);
      return;
    }
    const started = performance.now();
    const id = window.setInterval(() => {
      setWaitedMs(performance.now() - started);
    }, 200);
    return () => window.clearInterval(id);
  }, [waiting, ready]);

  const mode: WaitHostMode = decideWaitHostMode({
    waiting,
    ready,
    arcadeEnabled,
    reducedOrCalm: reduced,
    optedIn,
    waitedMs,
    offerAfterMs,
  });

  // Shared factory with ArcadeCabinet — host-entry tests progress score/wave
  // via createArcadeCartridge + progressCartridge on this same path.
  const cartridge = useMemo(
    () => createArcadeCartridge(game, { reducedMotion: reduced }),
    [game, reduced],
  );

  if (mode === "hidden") return null;

  return (
    <div
      className={className}
      data-testid="loading-game-host"
      data-host-mode={mode}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: 12,
        borderRadius: 10,
        background: "rgba(255,255,255,0.82)",
        border: "1px solid rgba(21,21,21,0.12)",
        maxWidth: 400,
        pointerEvents: "auto",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          {mode === "playing"
            ? cartridge.meta.title
            : "Deep research running…"}
        </span>
        <button
          type="button"
          data-testid="loading-game-primary"
          onClick={onPrimaryContinue}
          style={{
            fontSize: 12,
            padding: "4px 10px",
            borderRadius: 6,
            border: "1px solid #151515",
            background: "#f5df24",
            cursor: "pointer",
          }}
        >
          {primaryControlLabel}
        </button>
      </div>

      {/* Living-TV brand strip — session key art for the offered game (or the
          living-TV desk invent as default). Decorative only. */}
      <img
        src={waitHostBrandArt(game)}
        alt=""
        aria-hidden="true"
        data-testid="loading-game-living-tv-brand"
        data-wait-game={game}
        style={{
          width: "100%",
          height: 64,
          objectFit: "cover",
          objectPosition: "center top",
          borderRadius: 8,
          display: "block",
        }}
        loading="lazy"
        decoding="async"
      />

      {mode === "plain-loader" && (
        <p data-testid="plain-loader" style={{ margin: 0, fontSize: 12 }}>
          Working — games stay off until you opt in
          {arcadeEnabled && !reduced ? " (offer soon)" : ""}.
        </p>
      )}

      {mode === "offer" && (
        <div data-testid="game-offer" style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            data-testid="game-offer-play"
            onClick={() => {
              // Living-TV: opting into wait-game is a curious glance from Werner.
              emitWernerExperience("highlight");
              setOptedIn(true);
            }}
            style={{
              fontSize: 12,
              padding: "6px 12px",
              borderRadius: 6,
              border: "2px solid #151515",
              background: "#f5df24",
              cursor: "pointer",
              fontWeight: 700,
            }}
          >
            Play {cartridge.meta.title}
          </button>
          <span
            data-testid="game-offer-blurb"
            style={{ fontSize: 11, opacity: 0.7, lineHeight: 1.35 }}
          >
            {waitHostOfferBlurb(game)}
          </span>
        </div>
      )}

      {mode === "playing" && (
        <ArcadeMount
          cartridge={cartridge}
          reducedMotion={reduced}
          testId="wait-arcade-mount"
          width={360}
          height={220}
        />
      )}
    </div>
  );
}
