import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { ListRestart, ListStart, RotateCcw, RotateCw } from "lucide-react";

import {
  getListeningProgress,
  prepareResearchIntent,
  putListeningProgress,
} from "../../api/multimedia";
import type {
  MultimediaListeningProgressResponse,
  MultimediaLocalAudiblePlayback,
} from "../../api/multimedia";
import { LemonButton, LemonTextarea } from "../../components/lemon";

const SPEEDS = [1, 1.25, 1.5, 2] as const;
const CHECKPOINT_INTERVAL_MS = 15_000;
let mediaSessionOwner: symbol | null = null;
let mediaSessionOwnerAudio: HTMLAudioElement | null = null;

function mintSessionId(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

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
  const [evidenceLineId, setEvidenceLineId] = useState<string | null>(null);
  const [researchLineId, setResearchLineId] = useState<string | null>(null);
  const [researchQuestion, setResearchQuestion] = useState("");
  const [researchStatus, setResearchStatus] = useState<"idle" | "submitting" | "prepared" | "error">("idle");
  const researchKeyRef = useRef<string | null>(null);
  const researchRequestRef = useRef(0);
  const researchSubmittingRef = useRef(false);

  // ── Listening progress state ──
  const sessionIdRef = useRef(mintSessionId());
  const sequenceRef = useRef(0);
  const applyingResumeRef = useRef(false);
  const progressLoadPendingRef = useRef(false);
  const metadataReadyRef = useRef(false);
  const pendingResumeRef = useRef<number | null>(null);
  const identityGenerationRef = useRef(0);
  const checkpointChainRef = useRef<Promise<void>>(Promise.resolve());
  const lastCheckpointTimeRef = useRef(0);
  const identityRef = useRef({ assetId: playback.asset_id, revisionId: playback.revision_id, audioUrl: playback.audio_url });
  const [resumedFrom, setResumedFrom] = useState<number | null>(null);
  const [previouslyCompleted, setPreviouslyCompleted] = useState(false);
  const [progressStatus, setProgressStatus] = useState<"idle" | "loading" | "saved" | "error">("idle");

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

  // ── Checkpoint serialization ──
  const enqueueCheckpoint = useCallback(
    (positionSeconds: number, force = false) => {
      const now = Date.now();
      if (!force && now - lastCheckpointTimeRef.current < CHECKPOINT_INTERVAL_MS) return;
      lastCheckpointTimeRef.current = now;
      const seq = ++sequenceRef.current;
      const positionMs = Math.min(
        Math.round(playback.duration_seconds * 1000),
        Math.max(0, Math.round(positionSeconds * 1000)),
      );
      const generation = identityGenerationRef.current;
      const sessionId = sessionIdRef.current;
      checkpointChainRef.current = checkpointChainRef.current.then(async () => {
        try {
          if (generation === identityGenerationRef.current) setProgressStatus("loading");
          await putListeningProgress(playback.asset_id, {
            revision_id: playback.revision_id,
            position_milliseconds: positionMs,
            session_id: sessionId,
            sequence: seq,
          }, playback.audio_sha256, playback.duration_seconds);
          if (generation === identityGenerationRef.current) setProgressStatus("saved");
        } catch {
          // Progress service failure never blocks verified playback.
          if (generation === identityGenerationRef.current) setProgressStatus("error");
        }
      });
    },
    [
      playback.asset_id,
      playback.audio_sha256,
      playback.duration_seconds,
      playback.revision_id,
    ],
  );

  // ── Load progress on identity change ──
  useEffect(() => {
    // Reset identity tracking.
    const generation = ++identityGenerationRef.current;
    identityRef.current = {
      assetId: playback.asset_id,
      revisionId: playback.revision_id,
      audioUrl: playback.audio_url,
    };
    checkpointChainRef.current = Promise.resolve();
    sessionIdRef.current = mintSessionId();
    sequenceRef.current = 0;
    applyingResumeRef.current = true;
    progressLoadPendingRef.current = true;
    metadataReadyRef.current = Boolean(audioRef.current && audioRef.current.readyState >= 1);
    pendingResumeRef.current = null;
    lastCheckpointTimeRef.current = 0;
    setResumedFrom(null);
    setPreviouslyCompleted(false);
    setProgressStatus("idle");
    setCurrentTime(0);
    setSpeed(1);
    setClaimsOpen(false);
    setEvidenceLineId(null);
    setResearchLineId(null);
    setResearchQuestion("");
    setResearchStatus("idle");
    researchKeyRef.current = null;
    researchRequestRef.current += 1;
    researchSubmittingRef.current = false;

    if (audioRef.current) {
      audioRef.current.currentTime = 0;
      audioRef.current.playbackRate = 1;
    }

    // Capture identity for stale-response guard.
    const capturedAssetId = playback.asset_id;
    const capturedRevisionId = playback.revision_id;
    const capturedAudioUrl = playback.audio_url;
    let cancelled = false;

    void getListeningProgress(
      playback.asset_id,
      playback.revision_id,
      playback.audio_sha256,
      playback.duration_seconds,
    )
      .then((response: MultimediaListeningProgressResponse) => {
        if (cancelled || generation !== identityGenerationRef.current) return;
        // Stale response guard: verify identity still matches.
        if (
          identityRef.current.assetId !== capturedAssetId ||
          identityRef.current.revisionId !== capturedRevisionId ||
          identityRef.current.audioUrl !== capturedAudioUrl
        ) return;
        if (!response.resume_available) {
          progressLoadPendingRef.current = false;
          applyingResumeRef.current = false;
          return;
        }
        if (response.completed) {
          setPreviouslyCompleted(true);
          // A complete lesson starts at zero and names it as previously completed.
          progressLoadPendingRef.current = false;
          applyingResumeRef.current = false;
          return;
        }
        const resumePosition = response.position_milliseconds / 1000;
        setResumedFrom(resumePosition);
        progressLoadPendingRef.current = false;
        const audio = audioRef.current;
        if (audio && (metadataReadyRef.current || audio.readyState >= 1)) {
          audio.currentTime = resumePosition;
          setCurrentTime(resumePosition);
          applyingResumeRef.current = false;
        } else {
          pendingResumeRef.current = resumePosition;
        }
      })
      .catch(() => {
        if (!cancelled && generation === identityGenerationRef.current) {
          progressLoadPendingRef.current = false;
          applyingResumeRef.current = false;
          setProgressStatus("error");
        }
      });

    return () => {
      cancelled = true;
      if (generation === identityGenerationRef.current) {
        progressLoadPendingRef.current = false;
        applyingResumeRef.current = false;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    playback.asset_id,
    playback.audio_sha256,
    playback.audio_url,
    playback.duration_seconds,
    playback.revision_id,
  ]);

  // ── Apply resume on loadedmetadata ──
  function handleLoadedMetadata() {
    const audio = audioRef.current;
    if (!audio) return;
    metadataReadyRef.current = true;
    if (pendingResumeRef.current !== null) {
      const resumePos = pendingResumeRef.current;
      pendingResumeRef.current = null;
      // Only apply if response still matches mounted identity.
      audio.currentTime = resumePos;
      setCurrentTime(resumePos);
    }
    if (!progressLoadPendingRef.current) applyingResumeRef.current = false;
    updateMediaState(audio.paused ? "paused" : "playing");
  }

  // ── Start over ──
  function handleStartOver() {
    seek(0);
    setResumedFrom(null);
    setPreviouslyCompleted(false);
    enqueueCheckpoint(0, true);
  }

  // ── Periodic + event-driven checkpoints ──
  function handleTimeUpdate(event: React.SyntheticEvent<HTMLAudioElement>) {
    const time = event.currentTarget.currentTime;
    setCurrentTime(time);
    updateMediaState(event.currentTarget.paused ? "paused" : "playing", time);
    if (!event.currentTarget.paused && !applyingResumeRef.current) {
      enqueueCheckpoint(time);
    }
  }

  function handlePause() {
    updateMediaState("paused");
    if (!applyingResumeRef.current) {
      enqueueCheckpoint(audioRef.current?.currentTime ?? currentTime, true);
    }
  }

  function handleEnded() {
    updateMediaState("paused");
    if (!applyingResumeRef.current) {
      enqueueCheckpoint(playback.duration_seconds, true);
    }
  }

  // ── Page hide checkpoint ──
  useEffect(() => {
    function handlePageHide() {
      if (applyingResumeRef.current) return;
      const audio = audioRef.current;
      if (!audio || audio.paused) return;
      const seq = ++sequenceRef.current;
      const positionMs = Math.round(audio.currentTime * 1000);
      void putListeningProgress(
        playback.asset_id,
        {
          revision_id: playback.revision_id,
          position_milliseconds: positionMs,
          session_id: sessionIdRef.current,
          sequence: seq,
        },
        playback.audio_sha256,
        playback.duration_seconds,
        true,
      ).catch(() => undefined);
    }
    window.addEventListener("pagehide", handlePageHide);
    return () => window.removeEventListener("pagehide", handlePageHide);
  }, [
    playback.asset_id,
    playback.audio_sha256,
    playback.duration_seconds,
    playback.revision_id,
  ]);

  // ── Media session teardown ──
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
      {/* Resume / completion banner */}
      {(resumedFrom !== null || previouslyCompleted) && (
        <div className="mb-3 rounded border border-sun/40 bg-sun/10 px-3 py-2 text-[12px]" role="status">
          {previouslyCompleted ? (
            <span>Previously completed — replaying from the beginning.</span>
          ) : (
            <span>Resumed from {formatTime(resumedFrom ?? 0)}.</span>
          )}
        </div>
      )}

      <audio
        ref={audioRef}
        controls
        crossOrigin="use-credentials"
        preload="metadata"
        src={playback.audio_url}
        className="w-full"
        aria-label={`Audio playback for ${title}`}
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={handleTimeUpdate}
        onPlay={() => {
          claimMediaSession();
          updateMediaState("playing");
        }}
        onPause={handlePause}
        onEnded={handleEnded}
        onDurationChange={() => updateMediaState(audioRef.current?.paused ? "paused" : "playing")}
      />

      {/* Progress status indicator */}
      {progressStatus === "error" && (
        <p className="mt-1 text-[10px] text-shadow-2" role="status">Progress sync unavailable</p>
      )}

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
        <div className="flex shrink-0 items-center gap-2">
          {resumedFrom !== null && !previouslyCompleted && (
            <LemonButton size="sm" variant="secondary" onClick={handleStartOver} aria-label="Start over">
              Start over
            </LemonButton>
          )}
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
            {claims.map((claim) => <div key={claim.line_id} className="mt-2 text-[12px]">
              <p>{claim.claim_text}</p>
              <p className="mt-1 text-shadow-1 dark:text-moonlight">{claim.follow_up_prompt} · {claim.source_count} {claim.source_count === 1 ? "source" : "sources"}</p>
              {claim.evidence_status === "verified_exact" ? <LemonButton
                className="mt-2"
                size="sm"
                variant="tertiary"
                aria-expanded={evidenceLineId === claim.line_id}
                onClick={() => setEvidenceLineId((current) => current === claim.line_id ? null : claim.line_id)}
              >
                {evidenceLineId === claim.line_id ? "Close evidence" : "Inspect evidence"}
              </LemonButton> : (
                <div className="mt-2 border-y border-rule py-2 dark:border-charcoal-1">
                  <p className="text-[11px] text-shadow-1 dark:text-moonlight">Legacy receipt · exact excerpt unavailable</p>
                  <p className="mt-1 font-mono text-[10px] text-shadow-2">Evidence records: {claim.source_chunk_ids.join(", ")}</p>
                </div>
              )}
              {claim.evidence_status === "verified_exact" && <LemonButton
                className="mt-2 ml-2"
                size="sm"
                variant="secondary"
                disabled={researchStatus === "submitting"}
                aria-expanded={researchLineId === claim.line_id}
                onClick={() => {
                  const opening = researchLineId !== claim.line_id;
                  setResearchLineId(opening ? claim.line_id : null);
                  setResearchQuestion(opening ? claim.follow_up_prompt : "");
                  setResearchStatus("idle");
                  researchKeyRef.current = null;
                  researchRequestRef.current += 1;
                  researchSubmittingRef.current = false;
                }}
              >Research this</LemonButton>}
              {researchLineId === claim.line_id && claim.evidence_status === "verified_exact" && (
                <div className="mt-2 border-y border-rule py-3 dark:border-charcoal-1" aria-label={`Prepare research for ${claim.claim_text}`}>
                  <p className="font-semibold">{claim.claim_text}</p>
                  {claim.evidence_sources.map((source) => (
                    <blockquote key={source.chunk_id} className="mt-2 border-l-2 border-sun pl-3 text-[12px]">{source.exact_text}</blockquote>
                  ))}
                  <label className="mt-3 block text-[11px] font-semibold" htmlFor={`research-${claim.line_id}`}>Research question</label>
                  <LemonTextarea
                    id={`research-${claim.line_id}`}
                    className="mt-1 text-[12px]"
                    minRows={3}
                    maxRows={8}
                    value={researchQuestion}
                    maxLength={2000}
                    disabled={researchStatus === "submitting"}
                    onChange={(event) => {
                      setResearchQuestion(event.target.value);
                      if (researchStatus !== "idle") setResearchStatus("idle");
                      researchKeyRef.current = null;
                      researchRequestRef.current += 1;
                      researchSubmittingRef.current = false;
                    }}
                  />
                  <LemonButton
                    className="mt-2"
                    size="sm"
                    disabled={researchStatus === "submitting" || researchStatus === "prepared" || researchQuestion.trim().length < 3}
                    onClick={() => {
                      const question = researchQuestion.trim();
                      if (question.length < 3 || researchSubmittingRef.current) return;
                      researchKeyRef.current ??= mintSessionId();
                      const generation = identityGenerationRef.current;
                      const requestGeneration = ++researchRequestRef.current;
                      researchSubmittingRef.current = true;
                      setResearchStatus("submitting");
                      void prepareResearchIntent(
                        playback.asset_id, playback.revision_id, playback.receipt_sha256,
                        playback.audio_sha256, claim, question, researchKeyRef.current,
                      ).then(() => {
                        if (generation === identityGenerationRef.current && requestGeneration === researchRequestRef.current) {
                          researchSubmittingRef.current = false;
                          setResearchStatus("prepared");
                        }
                      }).catch(() => {
                        if (generation === identityGenerationRef.current && requestGeneration === researchRequestRef.current) {
                          researchSubmittingRef.current = false;
                          setResearchStatus("error");
                        }
                      });
                    }}
                  >{researchStatus === "submitting" ? "Preparing…" : "Prepare research"}</LemonButton>
                  {researchStatus === "prepared" && <p className="mt-2 text-[11px]">Research prepared. Plan review is the next step and is currently unavailable.</p>}
                  {researchStatus === "error" && <p className="mt-2 text-[11px]" role="alert">Could not prepare research. Try again.</p>}
                </div>
              )}
              {evidenceLineId === claim.line_id && (
                <div className="mt-2 border-y border-rule dark:border-charcoal-1" aria-label={`Evidence for ${claim.claim_text}`}>
                  {claim.evidence_sources.map((source) => (
                    <article key={source.chunk_id} className="py-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="font-mono text-[10px] font-semibold uppercase text-shadow-1 dark:text-moonlight">
                          {source.authority_kind === "canonical_graph" ? "Canonical graph" : "Operator excerpt"}
                        </p>
                        <p className="font-mono text-[10px] text-shadow-2">{source.document_id}</p>
                      </div>
                      {source.locator && <p className="mt-1 font-mono text-[10px] text-shadow-2">{source.locator}</p>}
                      <blockquote className="mt-2 border-l-2 border-sun pl-3 text-[12px] leading-5">{source.exact_text}</blockquote>
                      <details className="mt-2 text-[10px] text-shadow-2">
                        <summary className="cursor-pointer font-mono">Authority details</summary>
                        <dl className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-1 font-mono">
                          <dt>Chunk</dt><dd className="truncate">{source.chunk_id}</dd>
                          <dt>Bytes</dt><dd>{source.start_utf8_byte}–{source.end_utf8_byte}</dd>
                          <dt>Chunk SHA</dt><dd className="truncate">{source.chunk_sha256}</dd>
                          <dt>Span SHA</dt><dd className="truncate">{source.span_sha256}</dd>
                        </dl>
                      </details>
                    </article>
                  ))}
                </div>
              )}
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
