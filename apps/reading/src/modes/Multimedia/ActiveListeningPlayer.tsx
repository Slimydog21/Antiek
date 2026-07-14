import { useEffect, useMemo, useRef, useState } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { ListRestart, ListStart, RotateCcw, RotateCw } from "lucide-react";

import type { MultimediaLocalAudiblePlayback } from "../../api/multimedia";
import { LemonButton } from "../../components/lemon";

const SPEEDS = [1, 1.25, 1.5, 2] as const;
let mediaSessionOwner: symbol | null = null;
let mediaSessionOwnerAudio: HTMLAudioElement | null = null;

export function ActiveListeningPlayer({
  playback,
  title,
}: {
  playback: MultimediaLocalAudiblePlayback;
  title: string;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const mediaSessionToken = useRef(Symbol("active-listening-player"));
  const currentIndexRef = useRef(0);
  const speedRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [currentTime, setCurrentTime] = useState(0);
  const [speed, setSpeed] = useState<number>(1);
  const [claimsOpen, setClaimsOpen] = useState(false);
  const currentIndex = useMemo(() => {
    const index = playback.chapters.findIndex(
      (chapter) => currentTime >= chapter.start_offset_seconds && currentTime < chapter.end_offset_seconds,
    );
    return index < 0 ? playback.chapters.length - 1 : index;
  }, [currentTime, playback.chapters]);
  const currentChapter = playback.chapters[currentIndex];
  currentIndexRef.current = currentIndex;

  function seek(time: number) {
    const audio = audioRef.current;
    if (!audio) return;
    const bounded = Math.min(playback.duration_seconds, Math.max(0, time));
    audio.currentTime = bounded;
    setCurrentTime(bounded);
  }

  function seekChapter(index: number) {
    const chapter = playback.chapters[Math.min(playback.chapters.length - 1, Math.max(0, index))];
    seek(chapter.start_offset_seconds);
  }

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.currentTime = 0;
      audioRef.current.playbackRate = 1;
    }
    setCurrentTime(0);
    setSpeed(1);
    setClaimsOpen(false);
  }, [playback.asset_id, playback.revision_id, playback.audio_url]);

  useEffect(() => {
    const mediaSession = navigator.mediaSession;
    if (!mediaSession) return;
    return () => {
      if (mediaSessionOwner !== mediaSessionToken.current) return;
      for (const action of MEDIA_SESSION_ACTIONS) mediaSession.setActionHandler(action, null);
      mediaSession.metadata = null;
      mediaSession.playbackState = "none";
      mediaSessionOwner = null;
      mediaSessionOwnerAudio = null;
    };
  }, [playback.asset_id, playback.revision_id, playback.audio_url]);

  function claimMediaSession() {
    const mediaSession = navigator.mediaSession;
    const audio = audioRef.current;
    if (!mediaSession || !audio) return;
    if (mediaSessionOwner !== mediaSessionToken.current) mediaSessionOwnerAudio?.pause();
    const actions: Array<[MediaSessionAction, MediaSessionActionHandler]> = [
      ["play", () => { void audio.play().catch(() => undefined); }],
      ["pause", () => audio.pause()],
      ["seekbackward", (details) => seek(audio.currentTime - (details.seekOffset ?? 15))],
      ["seekforward", (details) => seek(audio.currentTime + (details.seekOffset ?? 15))],
      ["previoustrack", () => seekChapter(currentIndexRef.current - 1)],
      ["nexttrack", () => seekChapter(currentIndexRef.current + 1)],
    ];
    mediaSessionOwner = mediaSessionToken.current;
    mediaSessionOwnerAudio = audio;
    mediaSession.metadata = new MediaMetadata({ title, artist: "Antiek" });
    for (const [action, handler] of actions) mediaSession.setActionHandler(action, handler);
  }

  function updateMediaState(state: MediaSessionPlaybackState, position = currentTime) {
    if (!navigator.mediaSession || mediaSessionOwner !== mediaSessionToken.current) return;
    navigator.mediaSession.playbackState = state;
    try {
      navigator.mediaSession.setPositionState({
        duration: playback.duration_seconds,
        playbackRate: audioRef.current?.playbackRate ?? 1,
        position: Math.min(position, playback.duration_seconds),
      });
    } catch {
      // Some browsers reject otherwise valid verified position state.
    }
  }

  return (
    <section className="w-full rounded-md border border-rule bg-ice-0 p-3 text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright" aria-label={`Active listening for ${title}`}>
      <audio
        ref={audioRef}
        controls
        crossOrigin="use-credentials"
        preload="metadata"
        src={playback.audio_url}
        className="w-full"
        aria-label={`Audio playback for ${title}`}
        onTimeUpdate={(event) => {
          setCurrentTime(event.currentTarget.currentTime);
          updateMediaState(event.currentTarget.paused ? "paused" : "playing", event.currentTarget.currentTime);
        }}
        onPlay={() => {
          claimMediaSession();
          updateMediaState("playing");
        }}
        onPause={() => updateMediaState("paused")}
        onDurationChange={() => updateMediaState(audioRef.current?.paused ? "paused" : "playing")}
      />

      <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
        <Control label="Previous chapter" icon={<ListRestart size={18} />} onClick={() => seekChapter(currentIndex - 1)} disabled={currentIndex === 0} />
        <Control label="Back 15 seconds" icon={<RotateCcw size={18} />} onClick={() => seek(currentTime - 15)} />
        <span className="min-w-[92px] text-center font-mono text-[11px] tabular-nums text-shadow-1 dark:text-moonlight">
          {formatTime(currentTime)} / {formatTime(playback.duration_seconds)}
        </span>
        <Control label="Forward 15 seconds" icon={<RotateCw size={18} />} onClick={() => seek(currentTime + 15)} />
        <Control label="Next chapter" icon={<ListStart size={18} />} onClick={() => seekChapter(currentIndex + 1)} disabled={currentIndex === playback.chapters.length - 1} />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-y border-rule py-3 dark:border-charcoal-1">
        <p className="min-w-0 text-[13px] font-semibold" aria-live="polite">{currentChapter.title}</p>
        <div role="radiogroup" aria-label="Playback speed" className="flex shrink-0 gap-1">
          {SPEEDS.map((value, index) => (
            <button
              key={value}
              ref={(element) => { speedRefs.current[index] = element; }}
              type="button"
              role="radio"
              tabIndex={speed === value ? 0 : -1}
              aria-checked={speed === value}
              className={speedClass(speed === value)}
              onClick={() => setPlaybackSpeed(value)}
              onKeyDown={(event) => {
                const next = speedKeyTarget(event.key, index);
                if (next === null) return;
                event.preventDefault();
                setPlaybackSpeed(SPEEDS[next]);
                speedRefs.current[next]?.focus();
              }}
            >{value}x</button>
          ))}
        </div>
      </div>

      <div className="mt-2 divide-y divide-rule dark:divide-charcoal-1" aria-label="Chapters">
        {playback.chapters.map((chapter, index) => (
          <button
            key={chapter.chapter_id}
            type="button"
            aria-label={`${chapter.title}, ${formatTime(chapter.start_offset_seconds)} to ${formatTime(chapter.end_offset_seconds)}`}
            aria-current={index === currentIndex ? "true" : undefined}
            onClick={() => seekChapter(index)}
            className="grid w-full grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-2 px-1 py-2 text-left hover:bg-ice-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun dark:hover:bg-charcoal-1"
          >
            <span className="font-mono text-[10px] text-shadow-2">{String(index + 1).padStart(2, "0")}</span>
            <span className="truncate text-[12px] font-semibold">{chapter.title}</span>
            <span className="font-mono text-[10px] tabular-nums text-shadow-2 dark:text-moonlight">{formatTime(chapter.start_offset_seconds)}–{formatTime(chapter.end_offset_seconds)}</span>
          </button>
        ))}
      </div>

      <div className="mt-3">
        <LemonButton size="sm" variant="secondary" aria-expanded={claimsOpen} onClick={() => setClaimsOpen((open) => !open)}>
          {claimsOpen ? "Close learned claims" : "Review learned claims"}
        </LemonButton>
        {claimsOpen && playback.chapters.map((chapter) => {
          const claims = playback.learned_claims.filter((claim) => claim.chapter_id === chapter.chapter_id);
          if (!claims.length) return null;
          return <section key={chapter.chapter_id} className="mt-3 border-t border-rule pt-3 dark:border-charcoal-1">
            <h4 className="font-mono text-[11px] font-semibold">{chapter.title}</h4>
            {claims.map((claim, index) => <div key={`${chapter.chapter_id}-${index}`} className="mt-2 text-[12px]">
              <p>{claim.claim_text}</p>
              <p className="mt-1 text-shadow-1 dark:text-moonlight">{claim.follow_up_prompt} · {claim.source_count} {claim.source_count === 1 ? "source" : "sources"}</p>
            </div>)}
          </section>;
        })}
      </div>
    </section>
  );

  function setPlaybackSpeed(value: number) {
    if (audioRef.current) audioRef.current.playbackRate = value;
    setSpeed(value);
  }
}

const MEDIA_SESSION_ACTIONS: MediaSessionAction[] = [
  "play", "pause", "seekbackward", "seekforward", "previoustrack", "nexttrack",
];

function speedKeyTarget(key: string, current: number): number | null {
  if (key === "Home") return 0;
  if (key === "End") return SPEEDS.length - 1;
  if (key === "ArrowRight" || key === "ArrowDown") return (current + 1) % SPEEDS.length;
  if (key === "ArrowLeft" || key === "ArrowUp") return (current - 1 + SPEEDS.length) % SPEEDS.length;
  return null;
}

function Control({ label, icon, ...props }: { label: string; icon: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return <LemonButton size="sm" variant="tertiary" aria-label={label} title={label} className="h-9 w-9 px-0" {...props}>{icon}</LemonButton>;
}

function speedClass(active: boolean) {
  return `h-7 min-w-10 rounded-hog border px-2 font-mono text-[11px] font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun ${active ? "border-sun bg-sun text-ink" : "border-rule bg-transparent dark:border-charcoal-1"}`;
}

function formatTime(seconds: number) {
  const rounded = Math.max(0, Math.floor(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}
